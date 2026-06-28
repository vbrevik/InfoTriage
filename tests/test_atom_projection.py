#!/usr/bin/env python3
"""tests/test_atom_projection.py — unit tests for the pull-on-demand Atom projection.

Covers R7 requirements and D-04/D-04a/D-04b decisions:
- render_atom returns valid Atom XML (well-formed, parseable)
- RSS and YouTube items appear in the output
- IMAP/email items are excluded (D-04a)
- Output is deterministic for the same store state (R7 idempotency)
- Empty store renders valid (entry-less) Atom XML, not an error
"""
import datetime

import defusedxml.ElementTree as ET  # XXE-safe parser (T-00-01-XXE; project mandate)

import pytest

from contracts import Item
from store import InMemoryStore, render_atom


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ts(offset_seconds: int = 0) -> datetime.datetime:
    base = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
    return base + datetime.timedelta(seconds=offset_seconds)


def _item(
    source_type: str,
    title: str,
    ts_offset: int = 0,
    url: str | None = None,
    summary: str | None = None,
) -> Item:
    return Item(
        source="Test Source",
        source_type=source_type,
        url=url or f"https://example.com/{source_type}/{title.lower().replace(' ', '-')}",
        title=title,
        ts=_ts(ts_offset),
        lang="en",
        summary=summary,
    )


@pytest.fixture
def mixed_store(tmp_path):
    """InMemoryStore containing rss, yt, and imap items."""
    store = InMemoryStore(blob_root=tmp_path / "blobs")
    store.put_item(_item("rss", "RSS Article One", ts_offset=10, summary="RSS summary"))
    store.put_item(_item("yt", "YouTube Video One", ts_offset=20))
    store.put_item(_item("imap", "Email Subject One", ts_offset=30))
    return store


@pytest.fixture
def empty_store(tmp_path):
    """Empty InMemoryStore for testing edge cases."""
    return InMemoryStore(blob_root=tmp_path / "blobs")


# ---------------------------------------------------------------------------
# Atom XML validity
# ---------------------------------------------------------------------------

def test_render_atom_is_bytes(mixed_store):
    result = render_atom(mixed_store)
    assert isinstance(result, bytes), "render_atom must return bytes (feedgen Pitfall 6)"


def test_render_atom_is_parseable_xml(mixed_store):
    result = render_atom(mixed_store)
    # Must not raise ParseError
    root = ET.fromstring(result)
    assert root is not None


def test_render_atom_is_atom_feed(mixed_store):
    result = render_atom(mixed_store)
    root = ET.fromstring(result)
    # Atom namespace
    assert "feed" in root.tag.lower()


# ---------------------------------------------------------------------------
# Content filtering (D-04a)
# ---------------------------------------------------------------------------

def test_rss_items_included(mixed_store):
    result = render_atom(mixed_store).decode("utf-8")
    assert "RSS Article One" in result, "RSS items must appear in Atom output"


def test_yt_items_included(mixed_store):
    result = render_atom(mixed_store).decode("utf-8")
    assert "YouTube Video One" in result, "YouTube items must appear in Atom output"


def test_imap_items_excluded(mixed_store):
    result = render_atom(mixed_store).decode("utf-8")
    assert "Email Subject One" not in result, (
        "IMAP/email items must be excluded from Atom output (D-04a)"
    )


def test_only_rss_yt_in_output(tmp_path):
    """Comprehensive exclusion test with multiple source types."""
    store = InMemoryStore(blob_root=tmp_path / "blobs")
    store.put_item(_item("rss", "RSS Feed Post"))
    store.put_item(_item("yt", "YouTube Upload"))
    store.put_item(_item("imap", "Email Newsletter"))
    store.put_item(_item("imap", "Another Email"))

    result = render_atom(store).decode("utf-8")

    assert "RSS Feed Post" in result
    assert "YouTube Upload" in result
    assert "Email Newsletter" not in result
    assert "Another Email" not in result


# ---------------------------------------------------------------------------
# Determinism (R7 idempotency)
# ---------------------------------------------------------------------------

def test_render_atom_deterministic(mixed_store):
    """Two calls on the same store state must return identical bytes."""
    result1 = render_atom(mixed_store)
    result2 = render_atom(mixed_store)
    assert result1 == result2, "render_atom must be deterministic for the same store state"


# ---------------------------------------------------------------------------
# Empty store
# ---------------------------------------------------------------------------

def test_empty_store_renders_valid_atom(empty_store):
    result = render_atom(empty_store)
    assert isinstance(result, bytes)
    root = ET.fromstring(result)
    assert root is not None


def test_empty_store_no_entries(empty_store):
    result = render_atom(empty_store).decode("utf-8")
    # Valid Atom with no <entry> elements
    root = ET.fromstring(result)
    ns = "{http://www.w3.org/2005/Atom}"
    entries = root.findall(f"{ns}entry")
    assert entries == [], f"Empty store must produce no entries, got {len(entries)}"


# ---------------------------------------------------------------------------
# URL and summary in entries
# ---------------------------------------------------------------------------

def test_entry_contains_url(tmp_path):
    store = InMemoryStore(blob_root=tmp_path / "blobs")
    item = _item("rss", "Link Test Item", url="https://example.com/specific-url")
    store.put_item(item)
    result = render_atom(store).decode("utf-8")
    assert "https://example.com/specific-url" in result


def test_entry_contains_summary(tmp_path):
    store = InMemoryStore(blob_root=tmp_path / "blobs")
    item = _item("rss", "Summary Test Item", summary="Detailed summary text")
    store.put_item(item)
    result = render_atom(store).decode("utf-8")
    assert "Detailed summary text" in result


# ---------------------------------------------------------------------------
# from store import render_atom resolution
# ---------------------------------------------------------------------------

def test_render_atom_importable():
    """render_atom must be importable from the store package."""
    from store import render_atom as _ra  # noqa: PLC0415
    assert callable(_ra)
