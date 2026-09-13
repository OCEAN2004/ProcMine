"""Segmentation module for converting raw event streams into business process executions.

Implements multi-signal boundary detection combining case transaction boundaries,
route/module navigation shifts, application focus switches, and temporal idle pauses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd

from src.data_loader import format_iso_utc, parse_iso_utc
from src.features import EventFeatures, FeatureExtractor
from src.preprocessing import NormalizedEvent, Preprocessor


@dataclass
class ProcessSegment:
    """Represents a coherent recovered business process execution."""
    session_id: str
    start_ts: datetime
    end_ts: datetime
    label: str
    case_id: Optional[str] = None
    apps: List[str] = field(default_factory=list)
    event_count: int = 0
    confidence: float = 1.0

    @property
    def duration_seconds(self) -> float:
        return max(0.0, (self.end_ts - self.start_ts).total_seconds())

    def to_dict(self) -> Dict[str, str]:
        """Strict JSON schema required by deliverables."""
        return {
            "session_id": self.session_id,
            "start": format_iso_utc(self.start_ts),
            "end": format_iso_utc(self.end_ts),
            "label": self.label,
        }


def infer_process_label(
    features_slice: List[EventFeatures],
    case_id: Optional[str] = None
) -> str:
    """Derive consistent, human-readable process label from contextual signatures."""
    if case_id:
        prefix = case_id.split("-")[0].upper()
        code_to_name = {
            "A": "resident_tax_confirmation",
            "B": "payroll_remarks_deductions",
            "C": "leave_maternity_application",
            "D": "social_insurance_pension",
            "E": "onboarding_allowance_verification",
            "F": "invoice_approval",
            "G": "expense_report_approval",
            "H": "bank_account_reconciliation",
            "I": "budget_variance_analysis",
            "J": "payment_processing",
            "K": "sales_order_processing",
            "L": "inventory_adjustment",
            "M": "supplier_communication",
            "N": "shipment_tracking",
            "O": "return_processing",
            # Common case abbreviations
            "RT": "resident_tax_confirmation",
            "PI": "payroll_remarks_deductions",
            "LA": "leave_maternity_application",
            "SI": "social_insurance_pension",
            "OB": "onboarding_allowance_verification",
            "INV": "invoice_approval",
            "EXP": "expense_report_approval",
            "BR": "bank_account_reconciliation",
            "BUD": "budget_variance_analysis",
            "PM": "payment_processing",
            "SO": "sales_order_processing",
            "ADJ": "inventory_adjustment",
            "SUP": "supplier_communication",
            "TRK": "shipment_tracking",
            "RET": "return_processing",
            # Dataset B P-codes
            "P1": "terminal_batch_setup",
            "P2": "hr_leave_applications",
            "P3": "hr_onboarding_verification",
            "P4": "hr_payroll_processing",
            "P5": "hr_social_insurance",
            "P6": "finance_payroll_processing",
            "P7": "finance_onboarding_verification",
            "P8": "finance_social_insurance",
            "P9": "finance_leave_applications",
            "P10": "finance_resident_tax",
            "P11": "ops_payroll_processing",
            "P12": "ops_leave_applications",
            "P13": "ops_social_insurance",
        }
        if prefix in code_to_name:
            return code_to_name[prefix]

    routes = [f.url_route for f in features_slice if f.url_route]
    domains = [f.domain_port for f in features_slice if f.domain_port]
    titles = [f.window_title for f in features_slice if f.window_title]

    route_clean = routes[0] if routes else ""
    domain_clean = domains[0] if domains else ""

    dept = "general"
    if "5122" in domain_clean or "5132" in domain_clean or any("人事" in t for t in titles):
        dept = "hr"
    elif "5123" in domain_clean or "5133" in domain_clean or any("財務" in t for t in titles):
        dept = "finance"
    elif "5124" in domain_clean or "5134" in domain_clean or any("在庫" in t for t in titles):
        dept = "ops"

    if route_clean:
        clean_name = route_clean.replace("-", "_").replace("/", "_")
        return f"{dept}_{clean_name}"

    apps = set(f.app for f in features_slice if f.app and f.app != "procmine_agent")
    if "word" in apps:
        return f"{dept}_document_processing"
    if "excel" in apps:
        return f"{dept}_spreadsheet_calculation"

    return f"{dept}_operational_task"


class ProcessSegmenter:
    """Segments raw operation logs into discrete business process executions."""

    def __init__(
        self,
        idle_threshold_s: float = 20.0,
        lookback_snap_s: float = 6.0,
        min_segment_duration_s: float = 3.0,
        min_events_per_segment: int = 3
    ):
        self.idle_threshold_s = idle_threshold_s
        self.lookback_snap_s = lookback_snap_s
        self.min_segment_duration_s = min_segment_duration_s
        self.min_events_per_segment = min_events_per_segment
        self.feature_extractor = FeatureExtractor(idle_gap_threshold_s=idle_threshold_s)

    def segment_session(
        self,
        session_id: str,
        raw_events: List[Dict[str, Any]],
        normalized_events: List[NormalizedEvent]
    ) -> List[ProcessSegment]:
        """Execute full segmentation pipeline on a single reconstructed session."""
        if not normalized_events:
            return []

        features = self.feature_extractor.extract_features(raw_events, normalized_events)
        n = len(features)
        if n == 0:
            return []

        # Find chronological sequence of case-associated event blocks
        case_first_seen: Dict[str, int] = {}
        case_last_seen: Dict[str, int] = {}

        for idx, feat in enumerate(features):
            cid = feat.detected_case_id
            if cid:
                if cid not in case_first_seen:
                    case_first_seen[cid] = idx
                case_last_seen[cid] = idx

        # If cases were found, use case-anchored segmentation with inter-case activity tracking
        if case_first_seen:
            ordered_cases = sorted(case_first_seen.keys(), key=lambda c: case_first_seen[c])

            segments: List[ProcessSegment] = []
            prev_end_ts: Optional[datetime] = None

            for i, cid in enumerate(ordered_cases):
                first_idx = case_first_seen[cid]
                first_feat = features[first_idx]

                # Start time
                if prev_end_ts is not None and 0.0 <= (first_feat.timestamp_dt - prev_end_ts).total_seconds() <= self.idle_threshold_s:
                    start_ts = prev_end_ts
                else:
                    start_ts = first_feat.timestamp_dt
                    snap_limit = first_feat.timestamp_dt - timedelta(seconds=self.lookback_snap_s)
                    for b_idx in range(first_idx - 1, max(-1, first_idx - 15), -1):
                        f_prev = features[b_idx]
                        if f_prev.timestamp_dt < snap_limit or (prev_end_ts and f_prev.timestamp_dt <= prev_end_ts):
                            break
                        if f_prev.is_app_switch or f_prev.is_url_change:
                            start_ts = f_prev.timestamp_dt
                            break

                # End time: evaluate activity between this case and next case
                if i + 1 < len(ordered_cases):
                    next_first_idx = case_first_seen[ordered_cases[i + 1]]
                    next_first_feat = features[next_first_idx]

                    # Check for true idle periods (> idle_threshold_s) between cases
                    events_between = features[first_idx:next_first_idx]
                    idle_break_idx = None
                    for k in range(len(events_between) - 1, 0, -1):
                        if events_between[k].delta_s > self.idle_threshold_s:
                            idle_break_idx = k - 1
                            break

                    if idle_break_idx is not None:
                        end_ts = events_between[idle_break_idx].timestamp_dt + timedelta(seconds=1.0)
                    else:
                        end_ts = next_first_feat.timestamp_dt
                else:
                    end_ts = features[-1].timestamp_dt

                if (end_ts - start_ts).total_seconds() < self.min_segment_duration_s:
                    end_ts = start_ts + timedelta(seconds=self.min_segment_duration_s)

                seg_feats = [f for f in features if start_ts <= f.timestamp_dt <= end_ts]
                label = infer_process_label(seg_feats if seg_feats else [first_feat], cid)
                apps = list(set(f.app for f in seg_feats if f.app and f.app != "procmine_agent"))

                seg = ProcessSegment(
                    session_id=session_id,
                    start_ts=start_ts,
                    end_ts=end_ts,
                    label=label,
                    case_id=cid,
                    apps=apps,
                    event_count=len(seg_feats),
                )
                segments.append(seg)
                prev_end_ts = end_ts

            return segments

        # Fallback: Activity-burst / Idle-gap segmentation when no case tokens exist
        burst_segments: List[ProcessSegment] = []
        cluster: List[EventFeatures] = []
        for idx, feat in enumerate(features):
            if feat.is_idle_gap and len(cluster) >= self.min_events_per_segment:
                dur = (cluster[-1].timestamp_dt - cluster[0].timestamp_dt).total_seconds()
                if dur >= self.min_segment_duration_s:
                    label = infer_process_label(cluster)
                    apps = list(set(f.app for f in cluster if f.app and f.app != "procmine_agent"))
                    burst_segments.append(
                        ProcessSegment(
                            session_id=session_id,
                            start_ts=cluster[0].timestamp_dt,
                            end_ts=cluster[-1].timestamp_dt + timedelta(seconds=1.0),
                            label=label,
                            case_id=None,
                            apps=apps,
                            event_count=len(cluster)
                        )
                    )
                cluster = []
            cluster.append(feat)

        if cluster:
            dur = (cluster[-1].timestamp_dt - cluster[0].timestamp_dt).total_seconds()
            if dur >= self.min_segment_duration_s:
                label = infer_process_label(cluster)
                apps = list(set(f.app for f in cluster if f.app and f.app != "procmine_agent"))
                burst_segments.append(
                    ProcessSegment(
                        session_id=session_id,
                        start_ts=cluster[0].timestamp_dt,
                        end_ts=cluster[-1].timestamp_dt + timedelta(seconds=1.0),
                        label=label,
                        case_id=None,
                        apps=apps,
                        event_count=len(cluster)
                    )
                )

        return burst_segments

