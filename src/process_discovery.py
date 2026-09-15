"""Process Discovery and Dataset B Analysis module.

Applies the frozen segmentation pipeline to Dataset B, generates outputs/segments.jsonl,
discovers process execution inventories, analyzes variants, and produces summary CSVs and charts.
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from src.data_loader import DataLoader, format_iso_utc
from src.preprocessing import Preprocessor
from src.segmentation import ProcessSegment, ProcessSegmenter


class ProcessDiscoverer:
    """Performs process mining, variant discovery, and artifact generation on Dataset B."""

    def __init__(self, base_dir: str = "."):
        self.loader = DataLoader(base_dir)
        self.preprocessor = Preprocessor(filter_agent_noise=True)
        self.segmenter = ProcessSegmenter()

    def process_dataset_b(self) -> Tuple[List[ProcessSegment], pd.DataFrame, pd.DataFrame]:
        """Run segmentation and process discovery over all sessions in Dataset B."""
        sessions = self.loader.list_sessions("dataset_b")
        all_segments: List[ProcessSegment] = []
        detailed_records: List[Dict[str, Any]] = []

        Path("outputs").mkdir(parents=True, exist_ok=True)
        Path("outputs/charts").mkdir(parents=True, exist_ok=True)

        for s_id in sessions:
            events = self.loader.load_session_events("dataset_b", s_id)
            norm_events = self.preprocessor.normalize_events(events)

            # Get machine / worker
            machine = "unknown"
            if events:
                machine = (events[0].get("source") or {}).get("machine_id", "unknown")

            segments = self.segmenter.segment_session(s_id, events, norm_events)
            all_segments.extend(segments)

            # Collect detailed sequence and variant information
            for seg in segments:
                seg_events = [
                    ne for ne in norm_events
                    if seg.start_ts <= ne.timestamp_dt <= seg.end_ts
                ]

                # Application transition sequence (collapsed repeats)
                app_seq: List[str] = []
                last_app = None
                for ne in seg_events:
                    if ne.app and ne.app != "procmine_agent" and ne.app != last_app:
                        app_seq.append(ne.app)
                        last_app = ne.app
                app_seq_str = " -> ".join(app_seq) if app_seq else "browser_only"

                # Interaction statistics
                n_clicks = sum(1 for ne in seg_events if "click" in ne.event_type)
                n_keystrokes = sum(1 for ne in seg_events if ne.event_type in {"keystroke", "shortcut"})
                n_clipboards = sum(1 for ne in seg_events if ne.is_clipboard)
                domains = list(set(ne.browser_domain for ne in seg_events if ne.browser_domain))

                detailed_records.append({
                    "session_id": s_id,
                    "machine_id": machine,
                    "case_id": seg.case_id or "",
                    "label": seg.label,
                    "start_ts": format_iso_utc(seg.start_ts),
                    "end_ts": format_iso_utc(seg.end_ts),
                    "duration_s": seg.duration_seconds,
                    "event_count": seg.event_count,
                    "app_sequence": app_seq_str,
                    "apps_involved": ", ".join(sorted(seg.apps)) if seg.apps else "none",
                    "domains": ", ".join(sorted(domains)),
                    "click_count": n_clicks,
                    "keystroke_count": n_keystrokes,
                    "clipboard_count": n_clipboards,
                })

        # Deliverable 1: Write outputs/segments.jsonl strictly formatted
        segments_jsonl_path = Path("outputs/segments.jsonl")
        with open(segments_jsonl_path, "w", encoding="utf-8") as f:
            for seg in all_segments:
                f.write(json.dumps(seg.to_dict(), ensure_ascii=False) + "\n")

        df_details = pd.DataFrame(detailed_records)

        # Process Summary Aggregation
        summary_rows = []
        for label, group in df_details.groupby("label"):
            durations = group["duration_s"].values
            sessions_count = group["session_id"].nunique()
            machines_count = group["machine_id"].nunique()
            all_apps = set()
            for apps_str in group["apps_involved"]:
                if apps_str != "none":
                    all_apps.update([a.strip() for a in apps_str.split(",")])

            all_domains = set()
            for dom_str in group["domains"]:
                if dom_str:
                    all_domains.update([d.strip() for d in dom_str.split(",")])

            # Most common sequence
            seq_counts = Counter(group["app_sequence"])
            common_seq = seq_counts.most_common(1)[0][0] if seq_counts else ""
            num_variants = group["app_sequence"].nunique()

            summary_rows.append({
                "process_label": label,
                "execution_count": len(group),
                "total_duration_sec": float(np.sum(durations)),
                "total_duration_min": float(np.sum(durations) / 60.0),
                "avg_duration_sec": float(np.mean(durations)),
                "median_duration_sec": float(np.median(durations)),
                "p25_duration_sec": float(np.percentile(durations, 25)),
                "p75_duration_sec": float(np.percentile(durations, 75)),
                "min_duration_sec": float(np.min(durations)),
                "max_duration_sec": float(np.max(durations)),
                "sessions_count": sessions_count,
                "machines_count": machines_count,
                "num_variants": num_variants,
                "common_sequence": common_seq,
                "apps_involved": ", ".join(sorted(all_apps)),
                "domains_involved": ", ".join(sorted(all_domains)),
                "avg_clicks": float(group["click_count"].mean()),
                "avg_keystrokes": float(group["keystroke_count"].mean()),
                "avg_clipboard_ops": float(group["clipboard_count"].mean()),
            })

        df_summary = pd.DataFrame(summary_rows)
        df_summary.sort_values(by="execution_count", ascending=False, inplace=True)
        df_summary.to_csv("outputs/process_summary.csv", index=False, encoding="utf-8")

        # Process Variants Aggregation
        variant_rows = []
        for (label, seq), var_group in df_details.groupby(["label", "app_sequence"]):
            durations = var_group["duration_s"].values
            total_proc_count = len(df_details[df_details["label"] == label])
            var_share = len(var_group) / total_proc_count if total_proc_count > 0 else 0.0

            variant_rows.append({
                "process_label": label,
                "variant_sequence": seq,
                "variant_count": len(var_group),
                "share_of_process": f"{var_share * 100:.1f}%",
                "avg_duration_sec": float(np.mean(durations)),
                "median_duration_sec": float(np.median(durations)),
                "p25_duration_sec": float(np.percentile(durations, 25)),
                "p75_duration_sec": float(np.percentile(durations, 75)),
            })

        df_variants = pd.DataFrame(variant_rows)
        df_variants.sort_values(by=["process_label", "variant_count"], ascending=[True, False], inplace=True)
        df_variants.to_csv("outputs/process_variants.csv", index=False, encoding="utf-8")

        # Generate Visualizations
        self.generate_charts(df_summary, df_details)

        return all_segments, df_summary, df_variants

    def generate_charts(self, df_summary: pd.DataFrame, df_details: pd.DataFrame) -> None:
        """Generate high-quality charts for report and analysis."""
        plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")

        # Chart 1: Process Execution Count & Total Duration
        fig, ax1 = plt.subplots(figsize=(12, 6))
        color = "tab:blue"
        ax1.set_xlabel("Business Process", fontsize=11, fontweight="bold")
        ax1.set_ylabel("Execution Count", color=color, fontsize=11, fontweight="bold")
        bars = ax1.bar(df_summary["process_label"], df_summary["execution_count"], color=color, alpha=0.75, width=0.5)
        ax1.tick_params(axis="y", labelcolor=color)
        ax1.tick_params(axis="x", rotation=45)

        ax2 = ax1.twinx()
        color = "tab:red"
        ax2.set_ylabel("Total Recorded Time (minutes)", color=color, fontsize=11, fontweight="bold")
        line = ax2.plot(df_summary["process_label"], df_summary["total_duration_min"], color=color, marker="o", linewidth=2.5)
        ax2.tick_params(axis="y", labelcolor=color)

        plt.title("Dataset B: Process Frequency and Total Recorded Duration", fontsize=13, fontweight="bold", pad=15)
        fig.tight_layout()
        plt.savefig("outputs/charts/process_frequency_duration.png", dpi=200)
        plt.close()

        # Chart 2: Median Duration per Process with IQR Errorbars
        fig, ax = plt.subplots(figsize=(12, 5))
        y_pos = np.arange(len(df_summary))
        med = df_summary["median_duration_sec"].values
        p25 = df_summary["p25_duration_sec"].values
        p75 = df_summary["p75_duration_sec"].values
        xerr = [med - p25, p75 - med]

        ax.barh(y_pos, med, xerr=xerr, align="center", alpha=0.8, color="#2b5c8f", capsize=5)
        ax.set_yticks(y_pos)
        ax.set_yticklabels(df_summary["process_label"])
        ax.invert_yaxis()
        ax.set_xlabel("Median Duration (seconds) [with P25-P75 IQR]", fontsize=11, fontweight="bold")
        ax.set_title("Dataset B: Execution Duration Distribution by Process", fontsize=13, fontweight="bold", pad=15)
        fig.tight_layout()
        plt.savefig("outputs/charts/process_duration_distributions.png", dpi=200)
        plt.close()

        # Chart 3: Manual Operations (Clicks, Keystrokes, Clipboard) Breakdown
        fig, ax = plt.subplots(figsize=(12, 6))
        width = 0.25
        x = np.arange(len(df_summary))

        ax.bar(x - width, df_summary["avg_clicks"], width, label="Avg Clicks / Exec", color="#4e79a7")
        ax.bar(x, df_summary["avg_keystrokes"], width, label="Avg Keystrokes / Exec", color="#f28e2b")
        ax.bar(x + width, df_summary["avg_clipboard_ops"], width, label="Avg Clipboard Ops / Exec", color="#e15759")

        ax.set_ylabel("Average Count per Execution", fontsize=11, fontweight="bold")
        ax.set_title("Dataset B: Operational Intensity & Manual Data Transfer by Process", fontsize=13, fontweight="bold", pad=15)
        ax.set_xticks(x)
        ax.set_xticklabels(df_summary["process_label"], rotation=45, ha="right")
        ax.legend()
        fig.tight_layout()
        plt.savefig("outputs/charts/process_app_breakdown.png", dpi=200)
        plt.close()


def run_process_discovery_cli() -> None:
    """CLI runner for Phase 10, 11, 12."""
    print("=" * 70)
    print("PHASE 10-12: APPLYING SEGMENTATION & DISCOVERING PROCESSES IN DATASET B")
    print("=" * 70)

    discoverer = ProcessDiscoverer()
    segments, df_summary, df_variants = discoverer.process_dataset_b()

    print(f"Successfully generated outputs/segments.jsonl ({len(segments)} segments)")
    print(f"Successfully generated outputs/process_summary.csv ({len(df_summary)} processes)")
    print(f"Successfully generated outputs/process_variants.csv ({len(df_variants)} variants)")
    print(f"Successfully generated 3 visualization charts in outputs/charts/")
    print("-" * 70)
    print("DATASET B PROCESS INVENTORY SUMMARY:")
    print("-" * 70)
    print(df_summary[["process_label", "execution_count", "total_duration_min", "median_duration_sec", "num_variants", "apps_involved"]].to_string(index=False))


if __name__ == "__main__":
    run_process_discovery_cli()

