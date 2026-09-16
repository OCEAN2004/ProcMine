"""Core reconciliation engine implementing deterministic business rules and policy evaluation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import pandas as pd

from automation.models import ClaimRecord, PolicyRate, ReconciliationResult, ReconciliationStatus


class MasterPolicyRegistry:
    """Stores contracted partner tariffs and employee master policy rates."""

    def __init__(self):
        self.registry: Dict[str, PolicyRate] = {}
        self._load_default_rates()

    def _load_default_rates(self) -> None:
        """Seed master rates matching real entities found in Dataset B logs."""
        seed_data = [
            PolicyRate("福岡システム設計", "IT_Outsourcing", 3500.0, 15000.0),
            PolicyRate("関西物流サービス", "Logistics_Service", 2400.0, 8000.0),
            PolicyRate("北陸部品工業株式会社", "Manufacturing_Parts", 2800.0, 12000.0),
            PolicyRate("千葉金属工業", "Hardware_Supply", 2600.0, 10000.0),
            PolicyRate("東海電子計測", "Electronics_Testing", 3200.0, 14000.0),
            PolicyRate("京都精密機械", "Precision_Machinery", 3800.0, 18000.0),
            PolicyRate("横浜港湾運輸", "Port_Transport", 2500.0, 9500.0),
            PolicyRate("川口 直樹", "Employee_Payroll", 1850.0, 24500.0),
            PolicyRate("藤田 実", "Employee_Payroll", 1950.0, 28000.0),
            PolicyRate("橋本 清", "Employee_Payroll", 2100.0, 31000.0),
        ]
        for item in seed_data:
            self.registry[item.entity_name] = item

    def get_rate(self, entity_name: str) -> Optional[PolicyRate]:
        """Retrieve rate by exact or normalized name."""
        clean = entity_name.strip()
        if clean in self.registry:
            return self.registry[clean]
        for name, rate in self.registry.items():
            if clean in name or name in clean:
                return rate
        return None

    def register_rate(self, rate: PolicyRate) -> None:
        self.registry[rate.entity_name] = rate


class ReconciliationEngine:
    """Automates claim recalculation, policy validation, and approval gating."""

    def __init__(
        self,
        registry: Optional[MasterPolicyRegistry] = None,
        auto_approve_threshold_pct: float = 0.5,
        warning_threshold_pct: float = 2.0
    ):
        self.registry = registry or MasterPolicyRegistry()
        self.auto_approve_threshold_pct = auto_approve_threshold_pct
        self.warning_threshold_pct = warning_threshold_pct

    def reconcile_claim(self, claim: ClaimRecord) -> ReconciliationResult:
        """Process a single claim record deterministically."""
        # 1. Structural validation
        err = claim.validate()
        if err:
            return ReconciliationResult(
                claim=claim,
                computed_total=0.0,
                variance_amount=claim.claimed_total,
                variance_percent=100.0,
                status=ReconciliationStatus.VALIDATION_ERROR,
                reconciliation_notes=f"Validation failed: {err}"
            )

        # 2. Master policy lookup
        policy = self.registry.get_rate(claim.entity_name)
        if not policy:
            return ReconciliationResult(
                claim=claim,
                computed_total=claim.base_amount,
                variance_amount=claim.claimed_total - claim.base_amount,
                variance_percent=100.0,
                status=ReconciliationStatus.REQUIRES_HUMAN_REVIEW,
                reconciliation_notes=f"Unregistered entity '{claim.entity_name}'. Master rate lookup missing."
            )

        # 3. Deterministic calculation
        # Gross = Base + (Overtime * Hourly Rate) - Deductions
        ot_pay = claim.overtime_hours * policy.hourly_rate
        computed = claim.base_amount + ot_pay - claim.reported_deduction
        computed = max(0.0, computed)

        # Variance calculation
        variance_amt = claim.claimed_total - computed
        if computed > 0:
            variance_pct = (abs(variance_amt) / computed) * 100.0
        else:
            variance_pct = 0.0 if claim.claimed_total == 0 else 100.0

        # 4. Gating decision rules
        if variance_pct <= self.auto_approve_threshold_pct:
            status = ReconciliationStatus.AUTO_APPROVED
            notes = f"Verified: Computed {computed:,.0f} matches claimed within {variance_pct:.2f}%."
        elif variance_pct <= self.warning_threshold_pct:
            status = ReconciliationStatus.WARNING_APPROVED
            notes = f"Minor rounding variance: Delta {variance_amt:+,.0f} ({variance_pct:.2f}%). Approved with caution."
        else:
            status = ReconciliationStatus.REQUIRES_HUMAN_REVIEW
            notes = f"Material variance detected: Claimed {claim.claimed_total:,.0f} vs Computed {computed:,.0f} (Diff: {variance_amt:+,.0f}, {variance_pct:.2f}%). Escalated for human review."

        return ReconciliationResult(
            claim=claim,
            computed_total=computed,
            variance_amount=variance_amt,
            variance_percent=variance_pct,
            status=status,
            reconciliation_notes=notes
        )

    def reconcile_batch(self, claims: List[ClaimRecord]) -> List[ReconciliationResult]:
        """Process an entire batch of claim records."""
        return [self.reconcile_claim(c) for c in claims]

    def export_audit_journal(
        self,
        results: List[ReconciliationResult],
        out_csv: Path,
        out_json: Path
    ) -> None:
        """Write complete immutable audit journal to CSV and JSON."""
        records = [r.to_dict() for r in results]
        df = pd.DataFrame(records)
        df.to_csv(out_csv, index=False, encoding="utf-8")

        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2, ensure_ascii=False)

