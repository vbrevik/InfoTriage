#!/usr/bin/env python3
"""test_ingest_common_time.py — unit tests for ingest_common.time helpers."""
import datetime

import pytest

from ingest_common import parse_since


def test_parse_since_hours():
    """parse_since converts 'Nh' to a UTC datetime N hours ago."""
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    dt = parse_since("24h")
    assert now - datetime.timedelta(hours=24, minutes=1) < dt < now


def test_parse_since_days():
    """parse_since converts 'Nd' to a UTC datetime N days ago."""
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    dt = parse_since("7d")
    assert (
        now - datetime.timedelta(days=7, minutes=1)
        < dt
        < now - datetime.timedelta(days=6)
    )


def test_parse_since_none_returns_none():
    """parse_since returns None for empty/None input."""
    assert parse_since(None) is None
    assert parse_since("") is None
    assert parse_since("  ") is None


def test_parse_since_invalid_raises():
    """parse_since rejects malformed window strings."""
    with pytest.raises(ValueError, match="Invalid --since"):
        parse_since("1week")


def test_parse_since_case_insensitive():
    """parse_since accepts uppercase H/D."""
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    dt = parse_since("1H")
    assert now - datetime.timedelta(hours=1, minutes=1) < dt < now
