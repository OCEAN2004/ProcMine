"""Evaluation module for measuring segmentation accuracy against ground truth.

Computes boundary accuracy, IoU overlap, precision/recall/F1, over-segmentation,
and under-segmentation metrics on Dataset A.
"""

from __future__ import annotations

import sys
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

from src.data_loader import DataLoader, GroundTruthExecution
from src.preprocessing import Preprocessor
from src.segmentation import ProcessSegment, ProcessSegmenter


@dataclass
class EvaluationMetrics:
    """Consolidated segmentation performance metrics."""
    total_gt_executions: int
    total_pred_segments: int
    matched_executions: int
    mean_start_error_s: float
    median_start_error_s: float
    p90_start_error_s: float
    mean_end_error_s: float
    median_end_error_s: float
    p90_end_error_s: float
    mean_iou: float
    median_iou: float
    precision: float
    recall: float
    f1_score: float
    boundary_acc_5s: float
    boundary_acc_10s: float
    boundary_acc_30s: float
    over_segmentation_rate: float
    under_segmentation_rate: float


def compute_iou(s1_start: datetime, s1_end: datetime, s2_start: datetime, s2_end: datetime) -> float:
    """Calculate temporal Intersection over Union (IoU) between two time intervals."""
    inter_start = max(s1_start, s2_start)
    inter_end = min(s1_end, s2_end)
    inter_dur = max(0.0, (inter_end - inter_start).total_seconds())

    union_start = min(s1_start, s2_start)
    union_end = max(s1_end, s2_end)
    union_dur = max(0.0, (union_end - union_start).total_seconds())

    if union_dur <= 0.0:
        return 0.0
    return inter_dur / union_dur


class SegmentationEvaluator:
    """Evaluates segmentation performance against ground truth."""

    def __init__(self, base_dir: str = "."):
        self.loader = DataLoader(base_dir)
        self.preprocessor = Preprocessor(filter_agent_noise=True)
        self.segmenter = ProcessSegmenter()

    def evaluate_session(
        self,
        session_id: str,
        pred_segments: List[ProcessSegment],
        gt_executions: List[GroundTruthExecution]
    ) -> Dict[str, Any]:
        """Evaluate predicted segments against ground truth for a single session."""
        if not gt_executions:
            return {
                "session_id": session_id,
                "n_gt": 0,
                "n_pred": len(pred_segments),
                "matches": [],
                "start_errors": [],
                "end_errors": [],
                "ious": [],
            }

        start_errors = []
        end_errors = []
        ious = []
        matched_gt_indices = set()
        matched_pred_indices = set()

        # Match each GT execution with best overlapping predicted segment
        for g_idx, gt in enumerate(gt_executions):
            best_iou = 0.0
            best_p_idx = -1
            for p_idx, pred in enumerate(pred_segments):
                iou = compute_iou(gt.start_ts, gt.end_ts, pred.start_ts, pred.end_ts)
                if iou > best_iou:
                    best_iou = iou
                    best_p_idx = p_idx

            if best_p_idx >= 0 and best_iou > 0.1:
                pred = pred_segments[best_p_idx]
                s_err = abs((pred.start_ts - gt.start_ts).total_seconds())
                e_err = abs((pred.end_ts - gt.end_ts).total_seconds())
                start_errors.append(s_err)
                end_errors.append(e_err)
                ious.append(best_iou)
                matched_gt_indices.add(g_idx)
                matched_pred_indices.add(best_p_idx)
            else:
                # Unmatched GT execution
                ious.append(0.0)

        # Measure over-segmentation: GT execution overlapping > 1 predicted segments
        over_seg_count = 0
        for gt in gt_executions:
            overlaps = sum(
                1 for pred in pred_segments
                if compute_iou(gt.start_ts, gt.end_ts, pred.start_ts, pred.end_ts) > 0.2
            )
            if overlaps > 1:
                over_seg_count += 1

        # Measure under-segmentation: Predicted segment overlapping > 1 GT executions
        under_seg_count = 0
        for pred in pred_segments:
            overlaps = sum(
                1 for gt in gt_executions
                if compute_iou(gt.start_ts, gt.end_ts, pred.start_ts, pred.end_ts) > 0.2
            )
            if overlaps > 1:
                under_seg_count += 1

        return {
            "session_id": session_id,
            "n_gt": len(gt_executions),
            "n_pred": len(pred_segments),
            "n_matched": len(matched_gt_indices),
            "start_errors": start_errors,
            "end_errors": end_errors,
            "ious": ious,
            "over_seg_count": over_seg_count,
            "under_seg_count": under_seg_count,
        }

    def run_evaluation(
        self,
        dataset_name: str = "dataset_a",
        max_sessions: Optional[int] = None
    ) -> Tuple[EvaluationMetrics, pd.DataFrame]:
        """Run full evaluation across sessions and compute summary metrics."""
        sessions = self.loader.list_sessions(dataset_name)
        if max_sessions:
            sessions = sessions[:max_sessions]

        all_start_errors = []
        all_end_errors = []
        all_ious = []
        total_gt = 0
        total_pred = 0
        total_matched = 0
        total_over_seg = 0
        total_under_seg = 0

        session_results = []

        for s_id in sessions:
            events = self.loader.load_session_events(dataset_name, s_id)
            norm_events = self.preprocessor.normalize_events(events)
            gt_execs = self.loader.load_ground_truth_executions(dataset_name, s_id)

            pred_segs = self.segmenter.segment_session(s_id, events, norm_events)
            res = self.evaluate_session(s_id, pred_segs, gt_execs)

            total_gt += res["n_gt"]
            total_pred += res["n_pred"]
            total_matched += res["n_matched"]
            total_over_seg += res["over_seg_count"]
            total_under_seg += res["under_seg_count"]

            all_start_errors.extend(res["start_errors"])
            all_end_errors.extend(res["end_errors"])
            all_ious.extend(res["ious"])

            session_results.append({
                "session_id": s_id,
                "gt_count": res["n_gt"],
                "pred_count": res["n_pred"],
                "matched_count": res["n_matched"],
                "mean_iou": float(np.mean(res["ious"])) if res["ious"] else 0.0,
                "median_iou": float(np.median(res["ious"])) if res["ious"] else 0.0,
                "over_seg_count": res["over_seg_count"],
                "under_seg_count": res["under_seg_count"],
            })

        # Summary statistics
        precision = total_matched / total_pred if total_pred > 0 else 0.0
        recall = total_matched / total_gt if total_gt > 0 else 0.0
        f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

        b_5s = np.mean([max(s, e) <= 5.0 for s, e in zip(all_start_errors, all_end_errors)]) if all_start_errors else 0.0
        b_10s = np.mean([max(s, e) <= 10.0 for s, e in zip(all_start_errors, all_end_errors)]) if all_start_errors else 0.0
        b_30s = np.mean([max(s, e) <= 30.0 for s, e in zip(all_start_errors, all_end_errors)]) if all_start_errors else 0.0

        metrics = EvaluationMetrics(
            total_gt_executions=total_gt,
            total_pred_segments=total_pred,
            matched_executions=total_matched,
            mean_start_error_s=float(np.mean(all_start_errors)) if all_start_errors else 0.0,
            median_start_error_s=float(np.median(all_start_errors)) if all_start_errors else 0.0,
            p90_start_error_s=float(np.percentile(all_start_errors, 90)) if all_start_errors else 0.0,
            mean_end_error_s=float(np.mean(all_end_errors)) if all_end_errors else 0.0,
            median_end_error_s=float(np.median(all_end_errors)) if all_end_errors else 0.0,
            p90_end_error_s=float(np.percentile(all_end_errors, 90)) if all_end_errors else 0.0,
            mean_iou=float(np.mean(all_ious)) if all_ious else 0.0,
            median_iou=float(np.median(all_ious)) if all_ious else 0.0,
            precision=precision,
            recall=recall,
            f1_score=f1,
            boundary_acc_5s=float(b_5s),
            boundary_acc_10s=float(b_10s),
            boundary_acc_30s=float(b_30s),
            over_segmentation_rate=total_over_seg / total_gt if total_gt > 0 else 0.0,
            under_segmentation_rate=total_under_seg / total_pred if total_pred > 0 else 0.0,
        )

        df_sessions = pd.DataFrame(session_results)
        return metrics, df_sessions


def run_evaluation_cli() -> None:
    """CLI runner for Phase 7 segmentation evaluation."""
    print("=" * 65)
    print("PHASE 7: EVALUATING SEGMENTATION ENGINE ON DATASET A")
    print("=" * 65)

    evaluator = SegmentationEvaluator()
    # Run across all 63 sessions of Dataset A
    metrics, df_sessions = evaluator.run_evaluation("dataset_a")

    df_sessions.to_csv("outputs/dataset_a_eval_sessions.csv", index=False)

    print(f"Total Ground Truth Executions: {metrics.total_gt_executions}")
    print(f"Total Predicted Segments:      {metrics.total_pred_segments}")
    print(f"Matched Executions:            {metrics.matched_executions}")
    print("-" * 65)
    print(f"Precision:                     {metrics.precision * 100:.2f}%")
    print(f"Recall:                        {metrics.recall * 100:.2f}%")
    print(f"F1 Score:                      {metrics.f1_score * 100:.2f}%")
    print("-" * 65)
    print(f"Mean IoU Overlap:              {metrics.mean_iou * 100:.2f}%")
    print(f"Median IoU Overlap:            {metrics.median_iou * 100:.2f}%")
    print("-" * 65)
    print(f"Start Error (Mean / Med / P90): {metrics.mean_start_error_s:.2f}s / {metrics.median_start_error_s:.2f}s / {metrics.p90_start_error_s:.2f}s")
    print(f"End Error (Mean / Med / P90):   {metrics.mean_end_error_s:.2f}s / {metrics.median_end_error_s:.2f}s / {metrics.p90_end_error_s:.2f}s")
    print("-" * 65)
    print(f"Boundary Accuracy (<= 5s):     {metrics.boundary_acc_5s * 100:.2f}%")
    print(f"Boundary Accuracy (<= 10s):    {metrics.boundary_acc_10s * 100:.2f}%")
    print(f"Boundary Accuracy (<= 30s):    {metrics.boundary_acc_30s * 100:.2f}%")
    print("-" * 65)
    print(f"Over-segmentation Rate:        {metrics.over_segmentation_rate * 100:.2f}%")
    print(f"Under-segmentation Rate:       {metrics.under_segmentation_rate * 100:.2f}%")
    print("=" * 65)


if __name__ == "__main__":
    run_evaluation_cli()

