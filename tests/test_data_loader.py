"""Unit tests for data loader and session reconstruction."""

import json
from datetime import datetime, timezone
from pathlib import Path
import pytest

from src.data_loader import DataLoader, format_iso_utc, parse_iso_utc


def test_parse_iso_utc():
    """Test ISO UTC parsing and formatting."""
    iso_str = "2026-07-01T16:44:24.390Z"
    dt = parse_iso_utc(iso_str)
    assert dt is not None
    assert dt.tzinfo == timezone.utc
    assert dt.year == 2026
    assert dt.month == 7
    assert dt.day == 1

    re_formatted = format_iso_utc(dt)
    assert re_formatted.endswith("Z")

    # None and invalid handling
    assert parse_iso_utc(None) is None
    assert parse_iso_utc("") is None
    assert parse_iso_utc("invalid-date") is None


def test_data_loader_list_sessions():
    """Verify session discovery in Dataset A and Dataset B."""
    loader = DataLoader(".")
    sessions_a = loader.list_sessions("dataset_a")
    sessions_b = loader.list_sessions("dataset_b")

    assert len(sessions_a) == 63
    assert len(sessions_b) == 15
    assert all(s.startswith("ses_") for s in sessions_a)
    assert all(s.startswith("ses_") for s in sessions_b)


def test_load_session_events():
    """Test multi-chunk event loading and chronological sorting."""
    loader = DataLoader(".")
    sessions_b = loader.list_sessions("dataset_b")
    first_session = sessions_b[0]

    events = loader.load_session_events("dataset_b", first_session, sort_by_time=True)
    assert len(events) > 0

    # Ensure strictly sorted by timestamp_ms
    ts_list = [e.get("timestamp_ms", 0) for e in events]
    assert ts_list == sorted(ts_list)


def test_load_ground_truth():
    """Verify ground truth manifest and execution loading for Dataset A."""
    loader = DataLoader(".")
    sessions_a = loader.list_sessions("dataset_a")
    first_session = sessions_a[0]

    execs = loader.load_ground_truth_executions("dataset_a", first_session)
    assert len(execs) > 0
    assert all(e.session_id == first_session for e in execs)
    assert all(e.duration_seconds >= 0.0 for e in execs)

