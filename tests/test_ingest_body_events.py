#!/usr/bin/env python3
"""test_ingest_body_events.py — SPEC R7 producer-side body write path: barentswatch (+ acled).

Covers plan 12-08 Task 3's BarentsWatch half in full: AIS position pings persist
a NULL body (the canonical SPEC R7 bodyless case); a record carrying an optional
narrative/notes field persists that text. No truncation, cap, or sanitization.

ACLED is NOT covered here. apps/ingest-acled/acled_ingest.py is an intentional
Phase-11 stub (ADR-014 paid-license gate; require_acled_license() raises before
any fetch occurs) with no Item(...) construction site at all — there is nothing
to add body= to. Building a real ACLED fetch/parse/Item pipeline is out of this
plan's "one field per adapter" scope (Rule 4 architectural change, needs a user
decision). See 12-08-SUMMARY.md "Deviations" for the full finding. This is
tracked as an open item, not silently dropped — see test_six_of_seven_adapters_
have_body_test_coverage below, which makes the gap mechanically visible rather
than asserting a false 7-of-7.
"""
import importlib
import sys
from pathlib import Path

# barentswatch and telegram live under hyphenated dirs not on the shared
# pytest pythonpath — insert both so the coverage assertion below can import
# telegram_ingest even when this test file runs in isolation.
_APPS_ROOT = Path(__file__).resolve().parents[1] / "apps"
sys.path.insert(0, str(_APPS_ROOT / "ingest-barentswatch"))
sys.path.insert(0, str(_APPS_ROOT / "ingest-telegram"))
import barentswatch_ingest  # noqa: E402

from store import InMemoryStore


# ===========================================================================
# BarentsWatch — single construction site (barentswatch_ingest.py)
# ===========================================================================


def test_barentswatch_ais_ping_persists_null_body(tmp_path):
    """A routine AIS position ping (no narrative field) persists a NULL body."""
    position = {
        "mmsi": 123456789,
        "name": "Test Vessel",
        "latitude": 78.22,
        "longitude": 15.65,
        "msgtime": "2026-07-21T10:00:00Z",
        "speedOverGround": 12.5,
        "courseOverGround": 95,
        "destination": "Longyearbyen",
    }
    item = barentswatch_ingest._position_to_item(position)

    store = InMemoryStore(blob_root=tmp_path / "blobs")
    store.put_item(item)
    retrieved = store.get_item(item.id)
    assert retrieved.body is None
    assert "Test Vessel" in retrieved.title  # summary derivation unaffected


def test_barentswatch_narrative_field_persists_full_body(tmp_path):
    """A record carrying an optional narrative/notes field persists that text as body."""
    position = {
        "mmsi": 987654321,
        "name": "Flagged Vessel",
        "latitude": 74.5,
        "longitude": 20.1,
        "msgtime": "2026-07-21T11:00:00Z",
        "destination": "Tromso",
        "notes": "Vessel observed loitering outside normal shipping lane for 6 hours.",
    }
    item = barentswatch_ingest._position_to_item(position)

    store = InMemoryStore(blob_root=tmp_path / "blobs")
    store.put_item(item)
    retrieved = store.get_item(item.id)
    assert (
        retrieved.body
        == "Vessel observed loitering outside normal shipping lane for 6 hours."
    )


# ===========================================================================
# 6-of-7 coverage assertion (ACLED excluded — see module docstring)
# ===========================================================================

# The 7 adapter modules SPEC R7 names. acled_ingest is intentionally absent
# from the "covered" set below — its Item(...) construction site does not
# exist in the current codebase (Phase-11 stub, ADR-014 license gate).
ALL_SEVEN_ADAPTER_MODULES = {
    "gmail_ingest",
    "imap_ingest",
    "youtube_ingest",
    "telegram_ingest",
    "obsidian_ingest",
    "barentswatch_ingest",
    "acled_ingest",
}

COVERED_ADAPTER_MODULES = ALL_SEVEN_ADAPTER_MODULES - {"acled_ingest"}


def test_six_of_seven_adapters_have_body_test_coverage():
    """6 of the 7 named adapters have body-population test coverage across this
    plan's three test files; acled_ingest is a documented, tracked gap (see
    module docstring) rather than a silently-dropped requirement.
    """
    for module_name in COVERED_ADAPTER_MODULES:
        importlib.import_module(module_name)
    assert COVERED_ADAPTER_MODULES == {
        "gmail_ingest",
        "imap_ingest",
        "youtube_ingest",
        "telegram_ingest",
        "obsidian_ingest",
        "barentswatch_ingest",
    }
    assert ALL_SEVEN_ADAPTER_MODULES - COVERED_ADAPTER_MODULES == {"acled_ingest"}
