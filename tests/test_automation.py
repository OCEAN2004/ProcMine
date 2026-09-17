"""Unit tests for the ProcMine AutoReconcile automation tool."""

from pathlib import Path
import pytest

from automation.models import ClaimRecord, PolicyRate, ReconciliationStatus
from automation.reconcile_engine import MasterPolicyRegistry, ReconciliationEngine
from automation.mock_adapter import generate_representative_batch, MockPortalAdapter


@pytest.fixture
def engine():
    registry = MasterPolicyRegistry()
    return ReconciliationEngine(registry=registry)


def test_auto_approve_standard_case(engine):
    """Compliant claim within 0.5% variance must auto-approve."""
    # Fukuoka: base 450,000 + (20 * 3,500 = 70,000) - 15,000 = 505,000
    claim = ClaimRecord(
        case_id="P6-TEST-001",
        entity_name="福岡システム設計",
        department="Finance",
        claim_category="IT",
        base_amount=450000.0,
        overtime_hours=20.0,
        reported_deduction=15000.0,
        claimed_total=505000.0
    )
    result = engine.reconcile_claim(claim)
    assert result.status == ReconciliationStatus.AUTO_APPROVED
    assert result.computed_total == 505000.0
    assert result.variance_amount == 0.0


def test_warning_approve_minor_rounding(engine):
    """Claim with 0.16% variance should be warning-approved."""
    # Hokuriku: base 600,000 + (10 * 2,800 = 28,000) - 12,000 = 616,000
    # Claimed: 622,000 (+6,000 yen, 0.97% variance: falls in 0.5% - 2.0% warning zone)
    claim = ClaimRecord(
        case_id="P6-TEST-002",
        entity_name="北陸部品工業株式会社",
        department="Finance",
        claim_category="Parts",
        base_amount=600000.0,
        overtime_hours=10.0,
        reported_deduction=12000.0,
        claimed_total=622000.0
    )
    result = engine.reconcile_claim(claim)
    assert result.status == ReconciliationStatus.WARNING_APPROVED


def test_material_discrepancy_escalation(engine):
    """Claim with > 2% variance must be escalated to human review."""
    # Chiba Metal: computed is 360,800, claimed is 385,000 (+6.7%)
    claim = ClaimRecord(
        case_id="P6-TEST-003",
        entity_name="千葉金属工業",
        department="Finance",
        claim_category="Hardware",
        base_amount=350000.0,
        overtime_hours=8.0,
        reported_deduction=10000.0,
        claimed_total=385000.0
    )
    result = engine.reconcile_claim(claim)
    assert result.status == ReconciliationStatus.REQUIRES_HUMAN_REVIEW
    assert "Material variance" in result.reconciliation_notes


def test_unregistered_entity_handling(engine):
    """Unknown entity must escalate for human lookup rather than fail silently."""
    claim = ClaimRecord(
        case_id="P6-TEST-004",
        entity_name="未知の株式会社",
        department="Finance",
        claim_category="Unknown",
        base_amount=100000.0,
        overtime_hours=0.0,
        reported_deduction=0.0,
        claimed_total=100000.0
    )
    result = engine.reconcile_claim(claim)
    assert result.status == ReconciliationStatus.REQUIRES_HUMAN_REVIEW
    assert "Unregistered entity" in result.reconciliation_notes


def test_validation_error_negative_values(engine):
    """Negative values should trigger validation error without unhandled exception."""
    claim = ClaimRecord(
        case_id="P6-TEST-005",
        entity_name="福岡システム設計",
        department="Finance",
        claim_category="IT",
        base_amount=-50000.0,
        overtime_hours=0.0,
        reported_deduction=0.0,
        claimed_total=50000.0
    )
    result = engine.reconcile_claim(claim)
    assert result.status == ReconciliationStatus.VALIDATION_ERROR


def test_portal_adapter_simulation(engine, tmp_path):
    """Test full batch submission and audit journal output."""
    claims = generate_representative_batch()
    results = engine.reconcile_batch(claims)
    assert len(results) == len(claims)

    csv_path = tmp_path / "test_journal.csv"
    json_path = tmp_path / "test_journal.json"
    engine.export_audit_journal(results, csv_path, json_path)
    assert csv_path.exists()
    assert json_path.exists()

    adapter = MockPortalAdapter()
    resp = adapter.submit_transactions(results)
    assert resp["status"] == "SUCCESS"
    assert resp["is_simulation"] is True
