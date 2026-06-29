#!/usr/bin/env python3
"""test_ingest_idempotency.py — tests for persist_and_publish idempotency (R6).

Verifies that running the adapter twice over the same source item:
  - leaves exactly ONE entry in the store, and
  - publishes exactly ONE payload to the "item.ingested" queue.

Uses InMemoryStore + InMemoryBus (no external deps required).
"""
import asyncio
import datetime
import pathlib

import pytest

from contracts import InMemoryBus, Item
from store import InMemoryStore
from ingest_common import persist_and_publish


def _make_item() -> Item:
    """Construct a canonical test item."""
    return Item(
        source="TestFeed",
        source_type="rss",
        url="https://example.com/article/1",
        title="Test Article",
        ts=datetime.datetime(2026, 6, 29, 10, 0, 0, tzinfo=datetime.timezone.utc),
        lang="en",
    )


@pytest.mark.asyncio
async def test_persist_and_publish_new_item(tmp_path: pathlib.Path) -> None:
    """First call: inserts item and publishes exactly once — returns True."""
    store = InMemoryStore(blob_root=tmp_path / "blobs")
    bus = InMemoryBus()
    item = _make_item()

    result = await persist_and_publish(store, bus, item)

    assert result is True
    assert len(store.list_items()) == 1
    messages = await bus.subscribe("item.ingested")
    assert len(messages) == 1
    payload = messages[0]
    assert payload["source"] == item.source
    assert payload["source_type"] == item.source_type
    assert payload["ts"] == item.ts.isoformat()


@pytest.mark.asyncio
async def test_persist_and_publish_duplicate_item(tmp_path: pathlib.Path) -> None:
    """Second call with same item: upserts store but publishes nothing — returns False."""
    store = InMemoryStore(blob_root=tmp_path / "blobs")
    bus = InMemoryBus()
    item = _make_item()

    first = await persist_and_publish(store, bus, item)
    second = await persist_and_publish(store, bus, item)

    assert first is True
    assert second is False
    # Exactly one item in store (upsert, last-write-wins)
    assert len(store.list_items()) == 1
    # Exactly one event on the bus (R6 idempotency)
    messages = await bus.subscribe("item.ingested")
    assert len(messages) == 1


@pytest.mark.asyncio
async def test_persist_and_publish_payload_shape(tmp_path: pathlib.Path) -> None:
    """Published payload contains source, source_type, ts keys (no id leak)."""
    store = InMemoryStore(blob_root=tmp_path / "blobs")
    bus = InMemoryBus()
    item = _make_item()

    await persist_and_publish(store, bus, item)

    messages = await bus.subscribe("item.ingested")
    assert len(messages) == 1
    payload = messages[0]
    assert set(payload.keys()) == {"source", "source_type", "ts"}
