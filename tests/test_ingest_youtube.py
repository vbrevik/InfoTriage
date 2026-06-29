#!/usr/bin/env python3
"""test_ingest_youtube.py — tests for ingest-youtube adapter (SPEC R2, R6).

Tests:
  - R2 dual output: 2-video channel → 2 rows, 2 events, body_ref blobs, Atom XML
  - R2 idempotency: re-run over same listing → same row count, no second event
  - R2-empty backstop: empty channel → 0 rows, 0 events, no exception
  - R6 blob-dedup backstop: same transcript bytes twice → exactly one blob file

Uses InMemoryStore (real blob_root=tmp_path) + InMemoryBus.
Monkeypatches yt_dlp_list (no subprocess), load_channels, build_store, build_bus,
and OUT_DIR (no filesystem side-effects outside tmp_path).
"""
import pathlib

import pytest

from contracts import InMemoryBus, Item
from store import InMemoryStore


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class _ClosableInMemoryBus(InMemoryBus):
    """InMemoryBus with async close() for production-code compatibility."""

    async def close(self) -> None:
        pass


def _test_channels(url: str = "https://youtube.com/@test") -> list[dict]:
    return [{"channel": url, "max_per_run": 5, "name": "TestChannel"}]


# ---------------------------------------------------------------------------
# R2: dual output — 2-video channel
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingest_r2_dual_output(tmp_path: pathlib.Path, monkeypatch) -> None:
    """For a channel listing 2 videos:
      - 2 rows in store, each with source_type='yt' and body_ref set
      - get_blob(body_ref) returns the stub bytes for each item
      - 2 events published to bus
      - Non-empty youtube-TestChannel.xml Atom file written (dual output)
    """
    import youtube_ingest

    blob_root = tmp_path / "blobs"
    atom_dir = tmp_path / "feeds"
    store = InMemoryStore(blob_root=blob_root)
    bus = _ClosableInMemoryBus()

    monkeypatch.setattr(youtube_ingest, "load_channels", lambda: _test_channels())
    monkeypatch.setattr(youtube_ingest, "build_store", lambda: store)
    monkeypatch.setattr(youtube_ingest, "build_bus", lambda: bus)
    monkeypatch.setattr(
        youtube_ingest,
        "yt_dlp_list",
        lambda ch, max_n: [("vid1", "Video One"), ("vid2", "Video Two")],
    )
    monkeypatch.setattr(youtube_ingest, "OUT_DIR", str(atom_dir))

    await youtube_ingest.ingest()

    # 2 rows in store
    items = store.list_items()
    assert len(items) == 2, f"expected 2 items, got {len(items)}"

    # All source_type == "yt" with body_ref resolving to stub bytes
    for item in items:
        assert item.source_type == "yt", f"source_type must be 'yt', got {item.source_type!r}"
        assert item.url.startswith("https://youtu.be/"), f"url must be youtu.be link, got {item.url!r}"
        assert item.body_ref is not None, "body_ref must be set after put_blob"
        blob_bytes = store.get_blob(item.body_ref)
        assert b"transcription disabled" in blob_bytes, "blob must contain stub text"

    # 2 events published
    events = await bus.subscribe("item.ingested")
    assert len(events) == 2, f"expected 2 events, got {len(events)}"

    # Non-empty Atom XML written (dual output preserved)
    atom_files = list(atom_dir.glob("youtube-*.xml"))
    assert len(atom_files) == 1, f"expected 1 Atom file, got {atom_files}"
    content = atom_files[0].read_text()
    assert "<entry>" in content, "Atom file must contain entries"
    assert "Video One" in content or "Video Two" in content, "Atom must include video titles"


# ---------------------------------------------------------------------------
# R2: idempotent re-run
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingest_r2_idempotent_rerun(tmp_path: pathlib.Path, monkeypatch) -> None:
    """Re-running ingest against identical channel listing:
      - Same row count after second run
      - No second 'item.ingested' event for already-seen items
    """
    import youtube_ingest

    blob_root = tmp_path / "blobs"
    atom_dir = tmp_path / "feeds"
    store = InMemoryStore(blob_root=blob_root)
    bus = _ClosableInMemoryBus()

    monkeypatch.setattr(youtube_ingest, "load_channels", lambda: _test_channels())
    monkeypatch.setattr(youtube_ingest, "build_store", lambda: store)
    monkeypatch.setattr(youtube_ingest, "build_bus", lambda: bus)
    monkeypatch.setattr(
        youtube_ingest,
        "yt_dlp_list",
        lambda ch, max_n: [("vid1", "Title 1")],
    )
    monkeypatch.setattr(youtube_ingest, "OUT_DIR", str(atom_dir))

    # First run
    await youtube_ingest.ingest()
    assert len(store.list_items()) == 1
    events_after_first = await bus.subscribe("item.ingested")
    assert len(events_after_first) == 1

    # Second run (same videos — idempotent)
    await youtube_ingest.ingest()
    assert len(store.list_items()) == 1, "row count must not increase on re-run"
    events_after_second = await bus.subscribe("item.ingested")
    # InMemoryBus deduplicates by (routing_key, item_id); persist_and_publish
    # also skips publish when item already exists — double protection
    assert len(events_after_second) == 1, "no second event published for duplicate item"


# ---------------------------------------------------------------------------
# R2-empty backstop: empty channel
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingest_r2_empty_channel(tmp_path: pathlib.Path, monkeypatch) -> None:
    """Empty channel (yt_dlp_list returns []): 0 rows, 0 events, no exception."""
    import youtube_ingest

    blob_root = tmp_path / "blobs"
    atom_dir = tmp_path / "feeds"
    store = InMemoryStore(blob_root=blob_root)
    bus = _ClosableInMemoryBus()

    monkeypatch.setattr(youtube_ingest, "load_channels", lambda: _test_channels())
    monkeypatch.setattr(youtube_ingest, "build_store", lambda: store)
    monkeypatch.setattr(youtube_ingest, "build_bus", lambda: bus)
    monkeypatch.setattr(youtube_ingest, "yt_dlp_list", lambda ch, max_n: [])
    monkeypatch.setattr(youtube_ingest, "OUT_DIR", str(atom_dir))

    # Must not raise
    await youtube_ingest.ingest()

    assert store.list_items() == [], "no items for empty channel"
    events = await bus.subscribe("item.ingested")
    assert events == [], "no events for empty channel"


# ---------------------------------------------------------------------------
# R6 blob-dedup backstop: same bytes → one file
# ---------------------------------------------------------------------------


def test_blob_dedup_same_content_one_file(tmp_path: pathlib.Path) -> None:
    """Storing identical transcript bytes twice yields exactly one blob file on disk."""
    store = InMemoryStore(blob_root=tmp_path / "blobs")
    data = b"(transcription disabled - identical stub)"

    hash1 = store.put_blob(data)
    hash2 = store.put_blob(data)

    assert hash1 == hash2, "identical content must produce identical hash"
    blob_files = [f for f in (tmp_path / "blobs").rglob("*") if f.is_file()]
    assert len(blob_files) == 1, f"expected 1 blob file, got {len(blob_files)}: {blob_files}"


def test_blob_dedup_distinct_content_distinct_files(tmp_path: pathlib.Path) -> None:
    """Storing distinct transcript bytes produces distinct blob files (one each)."""
    store = InMemoryStore(blob_root=tmp_path / "blobs")
    data_a = b"stub text for video one"
    data_b = b"stub text for video two"

    hash_a = store.put_blob(data_a)
    hash_b = store.put_blob(data_b)

    assert hash_a != hash_b, "distinct content must produce distinct hashes"
    blob_files = [f for f in (tmp_path / "blobs").rglob("*") if f.is_file()]
    assert len(blob_files) == 2, f"expected 2 blob files, got {len(blob_files)}"
