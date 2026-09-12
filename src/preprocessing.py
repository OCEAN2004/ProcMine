"""Preprocessing and event normalization module.

Filters recording noise (uploads, agent heartbeats), normalizes application
and browser context, and extracts standardized event records.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from src.data_loader import parse_iso_utc


# System events that represent agent overhead rather than employee work
AGENT_SYSTEM_NOISE_TYPES = {
    "upload_started",
    "upload_completed",
    "upload_failed",
    "extension_connected",
    "extension_disconnected",
}


def normalize_app_name(raw_name: Optional[str]) -> str:
    """Normalize application and process names to clean canonical tokens."""
    if not raw_name:
        return "unknown"
    name = raw_name.lower().strip()
    if name.endswith(".exe"):
        name = name[:-4]
    if "chrome" in name:
        return "chrome"
    if "msedge" in name or "edge" in name:
        return "msedge"
    if "excel" in name:
        return "excel"
    if "winword" in name or "word" in name:
        return "word"
    if "notepad" in name:
        return "notepad"
    if "terminal" in name or "powershell" in name or "cmd" in name:
        return "terminal"
    if "explorer" in name:
        return "explorer"
    if "procmine" in name:
        return "procmine_agent"
    return name


def extract_url_domain_and_port(url_str: Optional[str]) -> str:
    """Extract host and port or domain token from URL."""
    if not url_str:
        return ""
    try:
        parsed = urlparse(url_str)
        if parsed.netloc:
            return parsed.netloc.lower()
        return parsed.path.lower()
    except Exception:
        return ""


@dataclass
class NormalizedEvent:
    """Standardized representation of a single human or system interaction event."""
    event_id: str
    session_id: str
    chunk_id: str
    timestamp_ms: int
    timestamp_dt: datetime
    layer: str
    event_type: str
    app: str
    window_title: str
    browser_url: str
    browser_domain: str
    browser_title: str
    delta_s: float
    is_interaction: bool
    is_clipboard: bool
    is_app_switch: bool
    details: Dict[str, Any]


class Preprocessor:
    """Transforms raw JSON event streams into structured, normalized events."""

    def __init__(self, filter_agent_noise: bool = True):
        self.filter_agent_noise = filter_agent_noise

    def is_noise(self, event: Dict[str, Any]) -> bool:
        """Check if an event is recording agent background noise."""
        event_type = event.get("event_type", "")
        layer = event.get("layer", "")

        if self.filter_agent_noise and event_type in AGENT_SYSTEM_NOISE_TYPES:
            return True

        # Pure system upload layers without user context
        if layer == "SYSTEM" and event_type not in {"session_start", "session_end"}:
            return True

        return False

    def normalize_events(
        self,
        raw_events: List[Dict[str, Any]]
    ) -> List[NormalizedEvent]:
        """Normalize a session's raw events, filter noise, and compute temporal deltas."""
        normalized: List[NormalizedEvent] = []
        prev_ts_ms: Optional[int] = None

        for evt in raw_events:
            if self.is_noise(evt):
                continue

            event_id = evt.get("event_id", "")
            session_id = evt.get("session_id", "")
            chunk_id = (evt.get("correlation") or {}).get("chunk_id", "")
            ts_ms = evt.get("timestamp_ms", 0)
            iso_str = evt.get("timestamp_iso", "")
            ts_dt = parse_iso_utc(iso_str) if iso_str else datetime.fromtimestamp(ts_ms / 1000.0)

            layer = evt.get("layer", "")
            event_type = evt.get("event_type", "")

            # Resolve active app name & window title
            context = evt.get("context") or {}
            payload = evt.get("payload") or {}

            active_app_ctx = context.get("active_app") or {}
            raw_app = (
                active_app_ctx.get("app_name")
                or active_app_ctx.get("process_name")
                or (payload.get("new_app") or {}).get("app_name")
                or (payload.get("new_app") or {}).get("process_name")
                or ""
            )
            app = normalize_app_name(raw_app)

            window_title = (
                active_app_ctx.get("window_title")
                or (payload.get("new_app") or {}).get("window_title")
                or ""
            )

            # Browser tab info
            browser_tab = context.get("active_browser_tab") or {}
            browser_url = browser_tab.get("url", "")
            browser_domain = extract_url_domain_and_port(browser_url)
            browser_title = browser_tab.get("title", "")

            # Interaction flags
            is_interaction = event_type in {
                "mouse_click", "mouse_double_click", "mouse_scroll",
                "keystroke", "shortcut", "browser_click", "browser_form_input",
                "clipboard_change"
            }
            is_clipboard = event_type == "clipboard_change" or "clipboard" in event_type
            is_app_switch = event_type == "app_switch"

            # Compute delta seconds from previous kept event
            delta_s = 0.0
            if prev_ts_ms is not None and ts_ms >= prev_ts_ms:
                delta_s = (ts_ms - prev_ts_ms) / 1000.0
            prev_ts_ms = ts_ms

            normalized.append(
                NormalizedEvent(
                    event_id=event_id,
                    session_id=session_id,
                    chunk_id=chunk_id,
                    timestamp_ms=ts_ms,
                    timestamp_dt=ts_dt,
                    layer=layer,
                    event_type=event_type,
                    app=app,
                    window_title=window_title,
                    browser_url=browser_url,
                    browser_domain=browser_domain,
                    browser_title=browser_title,
                    delta_s=delta_s,
                    is_interaction=is_interaction,
                    is_clipboard=is_clipboard,
                    is_app_switch=is_app_switch,
                    details=payload
                )
            )

        return normalized

