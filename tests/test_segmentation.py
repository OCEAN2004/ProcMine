"""Unit tests for segmentation engine and boundary detection."""

from datetime import datetime, timezone
import pytest

from src.data_loader import DataLoader
from src.preprocessing import Preprocessor
from src.segmentation import ProcessSegment, ProcessSegmenter


def test_segment_session_non_overlapping():
    """Verify that segmented executions in Dataset B are strictly non-overlapping."""
    loader = DataLoader(".")
    preprocessor = Preprocessor(filter_agent_noise=True)
    segmenter = ProcessSegmenter()

    s_id = loader.list_sessions("dataset_b")[0]
    events = loader.load_session_events("dataset_b", s_id)
    norm_events = preprocessor.normalize_events(events)

    segments = segmenter.segment_session(s_id, events, norm_events)
    assert len(segments) > 0

    for i in range(len(segments) - 1):
        s1 = segments[i]
        s2 = segments[i + 1]
        assert s1.start_ts < s1.end_ts, f"Invalid duration for {s1.label}"
        assert s1.end_ts <= s2.start_ts, f"Overlap detected between {s1.case_id} and {s2.case_id}"


def test_segment_deliverable_schema():
    """Verify that each segment conforms to the exact required deliverable schema."""
    loader = DataLoader(".")
    preprocessor = Preprocessor(filter_agent_noise=True)
    segmenter = ProcessSegmenter()

    s_id = loader.list_sessions("dataset_b")[0]
    events = loader.load_session_events("dataset_b", s_id)
    norm_events = preprocessor.normalize_events(events)

    segments = segmenter.segment_session(s_id, events, norm_events)
    for seg in segments:
        d = seg.to_dict()
        assert "session_id" in d
        assert "start" in d
        assert "end" in d
        assert "label" in d
        assert d["start"].endswith("Z")
        assert d["end"].endswith("Z")
        assert isinstance(d["label"], str) and len(d["label"]) > 0


def test_empty_events_handling():
    """Ensure segmenter handles empty or noisy inputs safely."""
    segmenter = ProcessSegmenter()
    segs = segmenter.segment_session("empty_ses", [], [])
    assert segs == []

