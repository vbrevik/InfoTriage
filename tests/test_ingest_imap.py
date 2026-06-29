#!/usr/bin/env python3
"""test_ingest_imap.py — R1 unit tests for ingest-imap adapter.

Verifies SPEC R1 and its key edges:
  R1:         2 messages → 2 Items (source_type="imap") and 2 item.ingested events on
              first run; second run over identical messages → 0 new events (R6 idempotency).
  R1-empty:   empty mailbox (0 matching messages) → 0 rows, 0 events, no exception
              (backstop edge — requires held-out/empty-mailbox test per PLAN.md).
  No-Atom:    no data/feeds/imap-*.xml file is created during any run.

Uses mocked imaplib layer + InMemoryStore + InMemoryBus (no external deps).
"""
import pathlib

import pytest

from contracts import InMemoryBus, Item
from store import InMemoryStore

# ---------------------------------------------------------------------------
# Fixture data
# ---------------------------------------------------------------------------

FIXTURE_MAILBOX = {
    "name": "test-mailbox",
    "host": "imap.example.com",
    "user": "test@example.com",
    "password": "secret",
    "query": "newer_than:7d",
    "provider": "imap",
}

FIXTURE_ENTRIES = [
    ("Subject One", "sender@example.com", "Body of message one", "<msg1@example.com>"),
    ("Subject Two", "sender@example.com", "Body of message two", "<msg2@example.com>"),
]


class _MockImap:
    """Minimal IMAP stub — only the methods used by imap_ingest.fetch_items."""

    def select(self, folder, readonly=False):
        return ("OK", [b"2"])

    def logout(self):
        pass


# ---------------------------------------------------------------------------
# R1: 2 messages → 2 Items + 2 events (first run)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingest_r1_two_messages(tmp_path: pathlib.Path, monkeypatch) -> None:
    """R1: 2 IMAP messages → 2 Items with source_type='imap', 2 events on first run."""
    import imap_ingest  # local import after monkeypatching scope is established

    store = InMemoryStore(blob_root=tmp_path / "blobs")
    bus = InMemoryBus()

    monkeypatch.setattr(imap_ingest, "load_mailboxes", lambda: [FIXTURE_MAILBOX])
    monkeypatch.setattr(imap_ingest, "connect", lambda host, user, pw: _MockImap())
    monkeypatch.setattr(
        imap_ingest,
        "search_ids",
        lambda imap, query, provider: [b"1", b"2"],
    )
    monkeypatch.setattr(
        imap_ingest,
        "fetch_entries",
        lambda imap, ids, max_recent=60: FIXTURE_ENTRIES,
    )
    monkeypatch.setattr(imap_ingest, "build_store", lambda: store)
    monkeypatch.setattr(imap_ingest, "build_bus", lambda: bus)

    await imap_ingest.ingest()

    # 2 Items persisted
    items = store.list_items()
    assert len(items) == 2, f"Expected 2 items, got {len(items)}"

    # All items have correct source_type and imap:// URL
    for it in items:
        assert it.source_type == "imap"
        assert it.url.startswith("imap://imap.example.com/")
        assert it.lang == "und"

    # 2 item.ingested events published
    events = await bus.subscribe("item.ingested")
    assert len(events) == 2, f"Expected 2 events, got {len(events)}"

    # No Atom file written anywhere under the project root
    atom_files = list(tmp_path.glob("**/imap-*.xml"))
    assert atom_files == [], f"Unexpected Atom files: {atom_files}"


# ---------------------------------------------------------------------------
# R1 idempotency: second run over identical messages → 0 new events
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingest_r1_idempotency(tmp_path: pathlib.Path, monkeypatch) -> None:
    """R1/R6: re-running over the same messages leaves row count unchanged, 0 new events."""
    import imap_ingest

    store = InMemoryStore(blob_root=tmp_path / "blobs")
    bus = InMemoryBus()

    monkeypatch.setattr(imap_ingest, "load_mailboxes", lambda: [FIXTURE_MAILBOX])
    monkeypatch.setattr(imap_ingest, "connect", lambda host, user, pw: _MockImap())
    monkeypatch.setattr(
        imap_ingest,
        "search_ids",
        lambda imap, query, provider: [b"1", b"2"],
    )
    monkeypatch.setattr(
        imap_ingest,
        "fetch_entries",
        lambda imap, ids, max_recent=60: FIXTURE_ENTRIES,
    )
    monkeypatch.setattr(imap_ingest, "build_store", lambda: store)
    monkeypatch.setattr(imap_ingest, "build_bus", lambda: bus)

    # First run
    await imap_ingest.ingest()
    # Second run — same fixtures, same message IDs → idempotent
    await imap_ingest.ingest()

    # Row count unchanged
    assert len(store.list_items()) == 2

    # Bus dedup — still exactly 2 events total (no second wave)
    events = await bus.subscribe("item.ingested")
    assert len(events) == 2, f"Expected 2 events after 2 runs, got {len(events)}"


# ---------------------------------------------------------------------------
# R1-empty backstop: empty mailbox → 0 rows, 0 events, no exception
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingest_r1_empty_mailbox(tmp_path: pathlib.Path, monkeypatch) -> None:
    """R1-empty: empty INBOX (0 matching messages) → 0 rows, 0 events, clean exit."""
    import imap_ingest

    store = InMemoryStore(blob_root=tmp_path / "blobs")
    bus = InMemoryBus()

    monkeypatch.setattr(imap_ingest, "load_mailboxes", lambda: [FIXTURE_MAILBOX])
    monkeypatch.setattr(imap_ingest, "connect", lambda host, user, pw: _MockImap())
    # Empty search → no IDs
    monkeypatch.setattr(
        imap_ingest,
        "search_ids",
        lambda imap, query, provider: [],
    )
    # Empty fetch → no entries
    monkeypatch.setattr(
        imap_ingest,
        "fetch_entries",
        lambda imap, ids, max_recent=60: [],
    )
    monkeypatch.setattr(imap_ingest, "build_store", lambda: store)
    monkeypatch.setattr(imap_ingest, "build_bus", lambda: bus)

    # Must not raise
    await imap_ingest.ingest()

    assert len(store.list_items()) == 0
    events = await bus.subscribe("item.ingested")
    assert len(events) == 0
