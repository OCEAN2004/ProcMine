"""Data models for the ProcMine AutoReconcile automation system."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional


class ReconciliationStatus(str, Enum):
    """Reconciliation decision status."""
    AUTO_APPROVED = "AUTO_APPROVED"
    WARNING_APPROVED = "WARNING_APPROVED"
    REQUIRES_HUMAN_REVIEW = "REQUIRES_HUMAN_REVIEW"
    MANUALLY_APPROVED = "MANUALLY_APPROVED"
    REJECTED = "REJECTED"
    VALIDATION_ERROR = "VALIDATION_ERROR"


@dataclass
class ClaimRecord:
    """Incoming payroll or vendor claim record to be verified."""
    case_id: str
    entity_name: str
    department: str
    claim_category: str
    base_amount: float
    overtime_hours: float
    reported_deduction: float
    claimed_total: float
    notes: str = ""

    def validate(self) -> Optional[str]:
        """Validate record fields for basic correctness."""
        if not self.case_id or not self.case_id.strip():
            return "Missing case_id"
        if not self.entity_name or not self.entity_name.strip():
            return "Missing entity_name"
        if self.base_amount < 0 or self.overtime_hours < 0 or self.reported_deduction < 0 or self.claimed_total < 0:
            return "Monetary and hour values must be non-negative"
        return None


@dataclass
class PolicyRate:
    """Contracted partner or employee master rate record."""
    entity_name: str
    contract_type: str
    hourly_rate: float
    standard_deduction: float
    allowance_rate: float = 0.0
    is_active: bool = True


@dataclass
class ReconciliationResult:
    """The result of automated computation and reconciliation."""
    claim: ClaimRecord
    computed_total: float
    variance_amount: float
    variance_percent: float
    status: ReconciliationStatus
    reconciliation_notes: str
    timestamp_utc: str = field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")[:-4] + "Z"
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.claim.case_id,
            "entity_name": self.claim.entity_name,
            "department": self.claim.department,
            "claim_category": self.claim.claim_category,
            "base_amount": self.claim.base_amount,
            "overtime_hours": self.claim.overtime_hours,
            "claimed_total": self.claim.claimed_total,
            "computed_total": round(self.computed_total, 2),
            "variance_amount": round(self.variance_amount, 2),
            "variance_percent": round(self.variance_percent, 2),
            "status": self.status.value,
            "notes": self.reconciliation_notes,
            "timestamp_utc": self.timestamp_utc,
        }

