"""Automation Opportunity Scoring and Prioritization module.

Implements a multi-factor decision matrix evaluating Impact, Repetition,
Feasibility, Risk, and Complexity to determine the highest-ROI automation target.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List
import pandas as pd

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


class AutomationScorer:
    """Scores and ranks business process automation candidates."""

    def __init__(self, summary_csv: str = "outputs/process_summary.csv"):
        self.summary_csv = Path(summary_csv)

    def score_processes(self) -> pd.DataFrame:
        """Calculate quantitative automation priority scores."""
        if not self.summary_csv.exists():
            raise FileNotFoundError(f"Summary CSV not found: {self.summary_csv}")

        df = pd.read_csv(self.summary_csv)

        # Exclude administrative terminal setup from business automation ranking
        df = df[df["process_label"] != "terminal_batch_setup"].copy()

        scores = []
        for _, row in df.iterrows():
            label = row["process_label"]
            freq = row["execution_count"]
            tot_dur_min = row["total_duration_min"]
            med_dur_s = row["median_duration_sec"]
            n_variants = row["num_variants"]
            apps_str = str(row["apps_involved"])
            n_apps = len(apps_str.split(",")) if apps_str != "none" else 1

            # 1. Impact (1 - 10 scale): frequency + total recorded duration
            # Higher execution count and time spent = higher impact
            impact = min(10.0, (freq / 11.0) * 5.0 + (tot_dur_min / 25.0) * 5.0)

            # 2. Repetition & Predictability (1 - 10 scale):
            # Higher repetition, lower variance ratio = higher score
            variant_ratio = n_variants / freq if freq > 0 else 1.0
            repetition = max(2.0, min(10.0, 10.0 - (variant_ratio * 4.0)))

            # 3. Technical Feasibility (1 - 10 scale):
            # Structured mathematical/table workflows (payroll, tax) are much more feasible
            # than free-form document evaluation (onboarding checklists, medical leaves)
            if "payroll" in label:
                feasibility = 9.0  # Tabular inputs, mathematical calculations, clear rules
            elif "resident_tax" in label:
                feasibility = 8.5  # Table comparison, municipal tax lookups
            elif "leave" in label:
                feasibility = 6.0  # Requires document/policy attachments, discretionary logic
            elif "onboarding" in label:
                feasibility = 5.0  # Multi-file checklist, inconsistent formats
            elif "social_insurance" in label:
                feasibility = 6.5  # Government form standards, moderate exceptions
            else:
                feasibility = 5.0

            # 4. Operational & Governance Risk (1 - 5 scale, where 1 is low risk, 5 is high risk):
            # Financial loss / compliance penalty vs internal delays
            if "payroll" in label:
                risk = 2.5  # Managed with human review of exceptions & audit trail
            elif "resident_tax" in label:
                risk = 2.0  # Mostly verification of municipality notice
            elif "social_insurance" in label:
                risk = 4.0  # Legal pension compliance penalties
            elif "onboarding" in label:
                risk = 3.5  # Contract legality and employee data privacy
            elif "leave" in label:
                risk = 3.0  # Labor law leave limits
            else:
                risk = 3.0

            # 5. Implementation Complexity (1 - 5 scale, where 1 is simple, 5 is complex):
            # Number of involved applications and document parsing requirements
            if "word" in apps_str and "excel" in apps_str:
                complexity = 3.5
            elif "excel" in apps_str:
                complexity = 2.5
            elif "word" in apps_str:
                complexity = 3.0
            else:
                complexity = 2.0

            # Combined Priority Score:
            # Score = (Impact * Repetition * Feasibility) / (Risk * Complexity)
            priority_score = (impact * repetition * feasibility) / (risk * complexity)

            scores.append({
                "process_label": label,
                "execution_count": int(freq),
                "total_duration_min": round(tot_dur_min, 2),
                "median_duration_sec": round(med_dur_s, 1),
                "impact_score": round(impact, 2),
                "repetition_score": round(repetition, 2),
                "feasibility_score": round(feasibility, 2),
                "risk_factor": round(risk, 2),
                "complexity_factor": round(complexity, 2),
                "priority_score": round(priority_score, 2),
            })

        df_scores = pd.DataFrame(scores)
        df_scores.sort_values(by="priority_score", ascending=False, inplace=True)
        df_scores.to_csv("outputs/automation_priority_matrix.csv", index=False, encoding="utf-8")
        return df_scores


def run_scoring_cli() -> None:
    """CLI runner for Phase 13 automation ranking."""
    print("=" * 80)
    print("PHASE 13: AUTOMATION OPPORTUNITY RANKING & ROI DECISION MATRIX")
    print("=" * 80)

    scorer = AutomationScorer()
    df_scores = scorer.score_processes()

    print(df_scores.to_string(index=False))
    top = df_scores.iloc[0]
    print("-" * 80)
    print(f"Top Recommended Automation Target: {top['process_label'].upper()}")
    print(f"Priority Score: {top['priority_score']} (Impact: {top['impact_score']}, Feasibility: {top['feasibility_score']}, Risk: {top['risk_factor']})")
    print("=" * 80)


if __name__ == "__main__":
    run_scoring_cli()

