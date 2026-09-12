"""Data loader module for operation logs and ground truth.

Handles multi-chunk session reconstruction, UTC timestamp parsing,
schema validation, and ground truth loading for Dataset A and Dataset B.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Union


def parse_iso_utc(ts_str: Optional[str]) -> Optional[datetime]:
    """Parse ISO-8601 UTC timestamp safely to a UTC-aware datetime object."""
    if not ts_str:
        return None
    try:
        clean_str = ts_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt
    except Exception:
        return None


def format_iso_utc(dt: Optional[datetime]) -> str:
    """Format datetime as strict ISO-8601 UTC ending in Z."""
    if dt is None:
        return ""
    dt_utc = dt.astimezone(timezone.utc)
    return dt_utc.strftime("%Y-%m-%dT%H:%M:%S.%fZ")[:-4] + "Z"


@dataclass
class GroundTruthExecution:
    """Represents a single business process execution from ground truth."""
    session_id: str
    code: str
    family_name: str
    domain: str
    variant: str
    case_id: Optional[str]
    start_ts: datetime
    end_ts: Optional[datetime]
    apps: List[str]
    continues_from_prev: bool
    continues_to_next: bool
    split_id: Optional[str] = None
    phase: Optional[int] = None
    exec_id: Optional[str] = None
    seq: Optional[int] = None

    @property
    def duration_seconds(self) -> float:
        if self.end_ts is None or self.start_ts is None:
            return 0.0
        return max(0.0, (self.end_ts - self.start_ts).total_seconds())


class DataLoader:
    """Loads and reconstructs session events and ground truth data."""

    def __init__(self, base_dir: Union[str, Path] = "."):
        self.base_dir = Path(base_dir)

    def get_dataset_dir(self, dataset_name: str) -> Path:
        """Resolve dataset directory path."""
        path = self.base_dir / dataset_name
        if not path.exists():
            raise FileNotFoundError(f"Dataset directory not found: {path}")
        return path

    def list_sessions(self, dataset_name: str) -> List[str]:
        """List all session directory names for a dataset, sorted chronologically."""
        dataset_path = self.get_dataset_dir(dataset_name)
        sessions = [
            d.name for d in dataset_path.iterdir()
            if d.is_dir() and d.name.startswith("ses_")
        ]
        return sorted(sessions)

    def find_chunk_dirs(self, session_path: Path) -> List[Path]:
        """Find all chunk directories inside a session path."""
        chunks = [
            d for d in session_path.iterdir()
            if d.is_dir() and d.name.startswith("chunk_")
        ]
        return sorted(chunks, key=lambda p: p.name)

    def load_session_events(
        self,
        dataset_name: str,
        session_id: str,
        sort_by_time: bool = True
    ) -> List[Dict[str, Any]]:
        """Load all events across all chunks for a specific session.
        
        Reconstructs the unified session timeline and ensures strict UTC ordering.
        """
        session_path = self.get_dataset_dir(dataset_name) / session_id
        chunk_dirs = self.find_chunk_dirs(session_path)

        all_events: List[Dict[str, Any]] = []
        seen_event_ids = set()

        for chunk_dir in chunk_dirs:
            events_file = chunk_dir / "events.jsonl"
            if not events_file.exists():
                continue

            with open(events_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    evt_id = event.get("event_id")
                    if evt_id and evt_id in seen_event_ids:
                        continue
                    if evt_id:
                        seen_event_ids.add(evt_id)

                    event["session_id"] = session_id
                    if "correlation" in event and not event["correlation"].get("chunk_id"):
                        event["correlation"]["chunk_id"] = chunk_dir.name

                    all_events.append(event)

        if sort_by_time:
            all_events.sort(key=lambda x: x.get("timestamp_ms", 0))

        return all_events

    def stream_session_events(
        self,
        dataset_name: str,
        session_id: str
    ) -> Iterator[Dict[str, Any]]:
        """Stream events generator for memory-efficient iteration."""
        events = self.load_session_events(dataset_name, session_id, sort_by_time=True)
        for evt in events:
            yield evt

    def load_ground_truth_manifest(
        self,
        session_path: Path
    ) -> Optional[Dict[str, Any]]:
        """Load gt_manifest.json if present."""
        manifest_path = session_path / "gt_manifest.json"
        if not manifest_path.exists():
            return None
        with open(manifest_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def load_ground_truth_executions(
        self,
        dataset_name: str,
        session_id: str
    ) -> List[GroundTruthExecution]:
        """Parse structured process executions from gt_manifest.json."""
        session_path = self.get_dataset_dir(dataset_name) / session_id
        manifest = self.load_ground_truth_manifest(session_path)
        if not manifest or "processes" not in manifest:
            return []

        session_info = manifest.get("session") or {}
        session_end_str = session_info.get("end_ts")
        session_end_dt = parse_iso_utc(session_end_str)

        executions: List[GroundTruthExecution] = []
        for proc in manifest.get("processes", []):
            code = proc.get("code", "")
            family_name = proc.get("family_name", "")
            domain = proc.get("domain", "")

            for ex in proc.get("executions", []):
                start_dt = parse_iso_utc(ex.get("start_ts"))
                if start_dt is None:
                    continue
                end_dt = parse_iso_utc(ex.get("end_ts"))
                if end_dt is None:
                    # Fallback if execution ended at session end
                    end_dt = session_end_dt or start_dt

                executions.append(
                    GroundTruthExecution(
                        session_id=session_id,
                        code=code,
                        family_name=family_name,
                        domain=domain,
                        variant=ex.get("variant", "std"),
                        case_id=ex.get("case_id"),
                        start_ts=start_dt,
                        end_ts=end_dt,
                        apps=ex.get("apps", []),
                        continues_from_prev=ex.get("continues_from_prev", False),
                        continues_to_next=ex.get("continues_to_next", False),
                        split_id=ex.get("split_id"),
                        phase=ex.get("phase"),
                        exec_id=ex.get("exec_id"),
                        seq=ex.get("seq"),
                    )
                )

        executions.sort(key=lambda x: x.start_ts)
        return executions

    def load_all_ground_truth(self, dataset_name: str = "dataset_a") -> List[GroundTruthExecution]:
        """Load all ground truth executions across all sessions in a dataset."""
        all_execs: List[GroundTruthExecution] = []
        sessions = self.list_sessions(dataset_name)
        for s_id in sessions:
            execs = self.load_ground_truth_executions(dataset_name, s_id)
            all_execs.extend(execs)
        return all_execs

    def load_gt_jsonl(self, dataset_name: str, session_id: str) -> List[Dict[str, Any]]:
        """Load raw gt.jsonl events (start, switch, task, clipboard) if available."""
        session_path = self.get_dataset_dir(dataset_name) / session_id
        gt_file = session_path / "gt.jsonl"
        if not gt_file.exists():
            return []

        gt_records = []
        with open(gt_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    gt_records.append(json.loads(line))
        return gt_records

