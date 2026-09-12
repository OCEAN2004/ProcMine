"""Analysis module for dataset reconnaissance and ground truth profiling.

Produces dataset-level statistics for Dataset A and Dataset B,
as well as a comprehensive process inventory from Dataset A ground truth.
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List
import pandas as pd
import numpy as np

# Ensure UTF-8 output on Windows terminal
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from src.data_loader import DataLoader, GroundTruthExecution
from src.preprocessing import Preprocessor


class DatasetAnalyzer:
    """Performs statistical reconnaissance and ground truth analysis."""

    def __init__(self, base_dir: str = "."):
        self.loader = DataLoader(base_dir)
        self.preprocessor = Preprocessor(filter_agent_noise=True)

    def analyze_dataset_overview(self, dataset_name: str) -> Dict[str, Any]:
        """Compute high-level dataset metrics (sessions, chunks, events, durations)."""
        sessions = self.loader.list_sessions(dataset_name)
        total_chunks = 0
        total_events = 0
        session_stats = []
        event_types = Counter()
        layers = Counter()
        apps = Counter()
        machines = Counter()
        domains = Counter()

        for s_id in sessions:
            s_path = self.loader.get_dataset_dir(dataset_name) / s_id
            chunks = self.loader.find_chunk_dirs(s_path)
            total_chunks += len(chunks)

            events = self.loader.load_session_events(dataset_name, s_id, sort_by_time=True)
            n_events = len(events)
            total_events += n_events

            if not events:
                continue

            start_ms = events[0].get("timestamp_ms", 0)
            end_ms = events[-1].get("timestamp_ms", 0)
            dur_s = max(0.0, (end_ms - start_ms) / 1000.0)

            machine = (events[0].get("source") or {}).get("machine_id", "unknown")
            machines[machine] += 1

            norm_events = self.preprocessor.normalize_events(events)

            for ne in norm_events:
                event_types[ne.event_type] += 1
                layers[ne.layer] += 1
                if ne.app:
                    apps[ne.app] += 1
                if ne.browser_domain:
                    domains[ne.browser_domain] += 1

            session_stats.append({
                "session_id": s_id,
                "chunks_count": len(chunks),
                "events_count": n_events,
                "duration_seconds": dur_s,
                "machine_id": machine,
            })

        df_sessions = pd.DataFrame(session_stats)

        overview = {
            "dataset_name": dataset_name,
            "n_sessions": len(sessions),
            "total_chunks": total_chunks,
            "total_events": total_events,
            "mean_events_per_session": float(df_sessions["events_count"].mean()) if not df_sessions.empty else 0,
            "median_events_per_session": float(df_sessions["events_count"].median()) if not df_sessions.empty else 0,
            "total_duration_hours": float(df_sessions["duration_seconds"].sum() / 3600.0) if not df_sessions.empty else 0,
            "mean_session_duration_min": float(df_sessions["duration_seconds"].mean() / 60.0) if not df_sessions.empty else 0,
            "event_types_top": dict(event_types.most_common(15)),
            "layers_distribution": dict(layers),
            "top_apps": dict(apps.most_common(10)),
            "top_domains": dict(domains.most_common(10)),
            "machines": dict(machines),
            "sessions_df": df_sessions,
        }
        return overview

    def analyze_ground_truth_inventory(self) -> pd.DataFrame:
        """Build a complete process catalog and inventory from Dataset A ground truth."""
        all_execs = self.loader.load_all_ground_truth("dataset_a")
        
        proc_groups = defaultdict(list)
        for ex in all_execs:
            key = (ex.code, ex.family_name, ex.domain)
            proc_groups[key].append(ex)

        inventory_rows = []
        for (code, name, domain), exec_list in sorted(proc_groups.items(), key=lambda x: x[0][0]):
            durations = [e.duration_seconds for e in exec_list if e.duration_seconds > 0]
            if not durations:
                durations = [0.0]

            variants = set(str(e.variant) for e in exec_list if e.variant is not None)
            sessions = set(e.session_id for e in exec_list)
            apps = set()
            for e in exec_list:
                if e.apps:
                    apps.update(str(a) for a in e.apps if a)

            inventory_rows.append({
                "process_code": code,
                "process_name": name,
                "domain": domain,
                "execution_count": len(exec_list),
                "total_duration_sec": sum(durations),
                "avg_duration_sec": float(np.mean(durations)),
                "median_duration_sec": float(np.median(durations)),
                "min_duration_sec": float(np.min(durations)),
                "max_duration_sec": float(np.max(durations)),
                "p25_duration_sec": float(np.percentile(durations, 25)),
                "p75_duration_sec": float(np.percentile(durations, 75)),
                "variants": ", ".join(sorted(variants)) if variants else "none",
                "num_variants": len(variants),
                "sessions_count": len(sessions),
                "apps_involved": ", ".join(sorted(apps)) if apps else "none",
            })

        df_inventory = pd.DataFrame(inventory_rows)
        return df_inventory


def run_reconnaissance() -> None:
    """Run full Phase 1 and Phase 2 reconnaissance and print clean summaries."""
    Path("outputs").mkdir(parents=True, exist_ok=True)
    analyzer = DatasetAnalyzer()
    print("=" * 60)
    print("PHASE 1: DATA RECONNAISSANCE")
    print("=" * 60)

    overviews = {}
    for ds in ["dataset_a", "dataset_b"]:
        info = analyzer.analyze_dataset_overview(ds)
        sessions_df = info.pop("sessions_df")
        overviews[ds] = info
        sessions_df.to_csv(f"outputs/{ds}_sessions.csv", index=False)

        print(f"\n--- {ds.upper()} OVERVIEW ---")
        print(f"Sessions: {info['n_sessions']}")
        print(f"Total Chunks: {info['total_chunks']}")
        print(f"Total Raw Events: {info['total_events']}")
        print(f"Total Recorded Time: {info['total_duration_hours']:.2f} hours")
        print(f"Mean Events / Session: {info['mean_events_per_session']:.1f}")
        print(f"Mean Session Duration: {info['mean_session_duration_min']:.2f} minutes")
        print(f"Machines ({len(info['machines'])}): {list(info['machines'].keys())}")
        print(f"Top Apps: {info['top_apps']}")
        print(f"Top Web Domains/Ports: {info['top_domains']}")
        print(f"Layer Distribution: {info['layers_distribution']}")

    with open("outputs/dataset_overviews.json", "w", encoding="utf-8") as f:
        json.dump(overviews, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 60)
    print("PHASE 2: DATASET A GROUND TRUTH INVENTORY")
    print("=" * 60)
    gt_inventory = analyzer.analyze_ground_truth_inventory()
    gt_inventory.to_csv("outputs/gt_inventory_a.csv", index=False, encoding="utf-8")
    
    # Print with safe ASCII or formatted repr
    for _, row in gt_inventory.iterrows():
        print(f"[{row['process_code']}] {row['domain']:8s} | {row['process_name']:18s} | count: {row['execution_count']:3d} | med_dur: {row['median_duration_sec']:5.1f}s | apps: {row['apps_involved']}")


if __name__ == "__main__":
    run_reconnaissance()

