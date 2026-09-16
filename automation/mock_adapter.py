"""Mock system adapter and representative test data generator for Dataset B operations.

NOTE ON SIMULATION:
In accordance with Master Development Instructions (Phase 17), this adapter provides
a realistic simulation of the client's internal Web Portal (ports 5132/5133/5134)
and Excel/Word inputs. It demonstrates the complete end-to-end integration without
relying on live production network credentials.
"""

from __future__ import annotations

from typing import Any, Dict, List
from automation.models import ClaimRecord, ReconciliationResult, ReconciliationStatus


def generate_representative_batch() -> List[ClaimRecord]:
    """Generate representative test claims matching Dataset B entities and edge cases."""
    return [
        # 1. Standard verified claim (Fukuoka System Design - IT Outsourcing)
        # Base: 450,000, Overtime: 20 hrs * 3,500 = 70,000, Deduction: 15,000 => Total = 505,000
        ClaimRecord(
            case_id="P6-07010448-001",
            entity_name="福岡システム設計",
            department="Finance",
            claim_category="Outsourced_IT_Services",
            base_amount=450000.0,
            overtime_hours=20.0,
            reported_deduction=15000.0,
            claimed_total=505000.0,
            notes="Monthly IT infrastructure maintenance & sprint support"
        ),
        # 2. Standard verified claim (Kansai Logistics Service - Freight dispatch)
        # Base: 280,000, Overtime: 15 hrs * 2,400 = 36,000, Deduction: 8,000 => Total = 308,000
        ClaimRecord(
            case_id="P6-07010448-002",
            entity_name="関西物流サービス",
            department="Finance",
            claim_category="Logistics_Transport",
            base_amount=280000.0,
            overtime_hours=15.0,
            reported_deduction=8000.0,
            claimed_total=308000.0,
            notes="Cross-dock logistics and regional freight delivery"
        ),
        # 3. Minor rounding variance (Hokuriku Parts Industry - acceptable within 0.2%)
        # Base: 600,000, Overtime: 10 hrs * 2,800 = 28,000, Deduction: 12,000 => Computed = 616,000
        # Claimed: 617,000 (diff: +1,000 yen, 0.16% variance)
        ClaimRecord(
            case_id="P6-07010448-003",
            entity_name="北陸部品工業株式会社",
            department="Finance",
            claim_category="Parts_Manufacturing",
            base_amount=600000.0,
            overtime_hours=10.0,
            reported_deduction=12000.0,
            claimed_total=617000.0,
            notes="Fabrication components batch delivery (includes minor packaging fee)"
        ),
        # 4. Material discrepancy case (Unapproved overtime surge - 6.5% variance)
        # Base: 350,000, Overtime: 8 hrs * 2,600 = 20,800, Deduction: 10,000 => Computed = 360,800
        # Claimed: 385,000 (diff: +24,200 yen, 6.7% variance) -> MUST BE ESCALATED
        ClaimRecord(
            case_id="P6-07010448-004",
            entity_name="千葉金属工業",
            department="Finance",
            claim_category="Hardware_Supply",
            base_amount=350000.0,
            overtime_hours=8.0,
            reported_deduction=10000.0,
            claimed_total=385000.0,
            notes="Invoice with unaccounted emergency courier surcharge"
        ),
        # 5. HR Payroll item claim (Naoki Kawaguchi - standard employee)
        # Base: 320,000, Overtime: 12 hrs * 1,850 = 22,200, Deduction: 24,500 => Computed = 317,700
        ClaimRecord(
            case_id="P4-07010448-005",
            entity_name="川口 直樹",
            department="HR",
            claim_category="Employee_Payroll_Deduction",
            base_amount=320000.0,
            overtime_hours=12.0,
            reported_deduction=24500.0,
            claimed_total=317700.0,
            notes="Monthly salary deduction for resident tax & employee meal plan"
        ),
        # 6. Unregistered Vendor (Missing in Master Policy Registry -> Escalation)
        ClaimRecord(
            case_id="P6-07010448-006",
            entity_name="新日本テクノロジーズ株式会社",
            department="Finance",
            claim_category="Consulting_Services",
            base_amount=500000.0,
            overtime_hours=0.0,
            reported_deduction=0.0,
            claimed_total=500000.0,
            notes="First-time vendor invoice without contracted master rate"
        ),
        # 7. Validation Error (Negative amount edge case)
        ClaimRecord(
            case_id="P6-07010448-007",
            entity_name="福岡システム設計",
            department="Finance",
            claim_category="Outsourced_IT_Services",
            base_amount=-10000.0,
            overtime_hours=0.0,
            reported_deduction=0.0,
            claimed_total=10000.0,
            notes="Erroneous negative base amount record"
        ),
    ]


class MockPortalAdapter:
    """Simulates API interactions with internal business portal."""

    def __init__(self, portal_url: str = "http://127.0.0.1:5133"):
        self.portal_url = portal_url
        self.submitted_transactions: List[Dict[str, Any]] = []

    def submit_transactions(self, results: List[ReconciliationResult]) -> Dict[str, Any]:
        """Simulate posting approved reconciliation actions to the internal portal."""
        posted = 0
        held_for_review = 0
        rejected = 0

        for r in results:
            if r.status in {ReconciliationStatus.AUTO_APPROVED, ReconciliationStatus.WARNING_APPROVED, ReconciliationStatus.MANUALLY_APPROVED}:
                self.submitted_transactions.append({
                    "case_id": r.claim.case_id,
                    "action": "APPROVED",
                    "amount_approved": r.computed_total,
                    "comment": r.reconciliation_notes,
                    "endpoint": f"{self.portal_url}/api/v1/claims/{r.claim.case_id}/approve",
                })
                posted += 1
            elif r.status == ReconciliationStatus.REQUIRES_HUMAN_REVIEW:
                held_for_review += 1
            else:
                rejected += 1

        return {
            "status": "SUCCESS",
            "total_processed": len(results),
            "posted_to_portal": posted,
            "held_for_human_review": held_for_review,
            "validation_errors": rejected,
            "portal_endpoint": self.portal_url,
            "is_simulation": True,
            "simulation_note": "Simulated mock adapter adhering to Master Development Instructions Phase 17.",
        }

