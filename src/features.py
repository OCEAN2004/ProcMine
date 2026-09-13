"""Feature engineering module for operation logs.

Extracts temporal, contextual, interaction, data-transfer (clipboard),
and transaction/case features from normalized event streams.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

from src.preprocessing import NormalizedEvent


# General case token pattern: e.g. RT-132457-001, P4-07010448-012, BR-175009-001
CASE_PATTERN = re.compile(r'(?:^|[^A-Za-z0-9])([A-Z]{1,4}-\d{6,8}-\d{3,4}|P\d{1,2}-\d{6,8}-\d{3,4})\b')

# Core submission / action buttons
SUBMISSION_KEYWORDS = {
    "承認", "確認", "登録", "保留", "差戻し", "保存", "申請", "完了",
    "approve", "confirm", "register", "hold", "save", "submit", "complete"
}


@dataclass
class EventFeatures:
    """Rich feature representation of an event within its temporal window."""
    event_id: str
    timestamp_dt: datetime
    timestamp_ms: int
    app: str
    window_title: str
    url_route: str
    domain_port: str
    event_type: str
    delta_s: float
    is_idle_gap: bool
    is_app_switch: bool
    is_url_change: bool
    is_title_change: bool
    is_clipboard_transfer: bool
    is_submission_action: bool
    detected_case_id: Optional[str] = None
    row_element_id: Optional[str] = None


class FeatureExtractor:
    """Extracts features across a normalized event timeline."""

    def __init__(
        self,
        idle_gap_threshold_s: float = 15.0,
    ):
        self.idle_gap_threshold_s = idle_gap_threshold_s

    def extract_url_route(self, url: str) -> str:
        """Extract path or hash route (e.g. /#/payroll-items -> payroll-items)."""
        if not url:
            return ""
        if "#/" in url:
            route = url.split("#/")[-1].split("?")[0].strip("/")
            return route.lower()
        try:
            parsed = urlparse(url)
            return parsed.path.strip("/").lower()
        except Exception:
            return ""

    def find_case_id(self, event_dict: Dict[str, Any]) -> Optional[str]:
        """Search event payloads and UI contexts for case identifiers."""
        # 1. Check UIA tree path automation IDs
        ext = event_dict.get("extensions") or {}
        uia = ext.get("uia_v2") or {}
        tree = uia.get("tree_path") or []
        for node in tree:
            aid = node.get("automation_id") or ""
            if "row-" in aid:
                matches = CASE_PATTERN.findall(aid)
                if matches:
                    return matches[0]

        # 2. Check target element name
        payload = event_dict.get("payload") or {}
        te = payload.get("target_element") or {}
        te_name = te.get("name") or ""
        matches = CASE_PATTERN.findall(te_name)
        if matches:
            return matches[0]

        # 3. Check clipboard content
        clip = payload.get("content_preview") or ""
        matches = CASE_PATTERN.findall(clip)
        if matches:
            return matches[0]

        # 4. Fallback search over full string dump
        text_dump = f"{str(payload)} {str(event_dict.get('context') or {})}"
        matches = CASE_PATTERN.findall(text_dump)
        if matches:
            return matches[0]

        return None

    def is_action_submit(self, event_dict: Dict[str, Any]) -> bool:
        """Detect whether this event is a submission/approval/completion action."""
        etype = event_dict.get("event_type", "")
        payload = event_dict.get("payload") or {}

        if etype == "browser_click":
            elem = payload.get("element") or {}
            txt = (elem.get("text") or "").lower()
            attrs = elem.get("attributes") or {}
            elem_id = (attrs.get("id") or "").lower()
            if any(k in txt or k in elem_id for k in SUBMISSION_KEYWORDS):
                return True

        if etype == "mouse_click":
            te = payload.get("target_element") or {}
            name = (te.get("name") or "").lower()
            auto_id = (te.get("automation_id") or "").lower()
            if any(k in name or k in auto_id for k in SUBMISSION_KEYWORDS):
                return True

        return False

    def extract_features(
        self,
        raw_events: List[Dict[str, Any]],
        normalized_events: List[NormalizedEvent]
    ) -> List[EventFeatures]:
        """Compute behavioral features for all events in a session."""
        features_list: List[EventFeatures] = []
        n = len(normalized_events)

        prev_app = ""
        prev_route = ""
        prev_title = ""

        # Map raw event_id to raw dict for fast lookup
        raw_lookup = {e.get("event_id"): e for e in raw_events if e.get("event_id")}

        for idx, ne in enumerate(normalized_events):
            raw_e = raw_lookup.get(ne.event_id, {})
            route = self.extract_url_route(ne.browser_url)
            domain_port = ne.browser_domain

            # Transition flags
            is_app_switch = (ne.app != prev_app) if prev_app else False
            is_url_change = (route != prev_route) if (route and prev_route) else False
            is_title_change = (ne.window_title != prev_title) if prev_title else False
            is_idle = ne.delta_s >= self.idle_gap_threshold_s

            # Case token detection
            case_id = self.find_case_id(raw_e)
            is_submit = self.is_action_submit(raw_e)

            features_list.append(
                EventFeatures(
                    event_id=ne.event_id,
                    timestamp_dt=ne.timestamp_dt,
                    timestamp_ms=ne.timestamp_ms,
                    app=ne.app,
                    window_title=ne.window_title,
                    url_route=route,
                    domain_port=domain_port,
                    event_type=ne.event_type,
                    delta_s=ne.delta_s,
                    is_idle_gap=is_idle,
                    is_app_switch=is_app_switch,
                    is_url_change=is_url_change,
                    is_title_change=is_title_change,
                    is_clipboard_transfer=ne.is_clipboard,
                    is_submission_action=is_submit,
                    detected_case_id=case_id
                )
            )

            if ne.app:
                prev_app = ne.app
            if route:
                prev_route = route
            if ne.window_title:
                prev_title = ne.window_title

        return features_list
