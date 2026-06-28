#!/usr/bin/env python3
"""_inmemory.py — dict-backed Store fake for unit tests.

Mirrors InMemoryBus in libs/contracts/src/contracts/_bus.py (same dict-backed
shape, no external deps, no thread-safety for single-process scope).

Must not diverge from PostgresStore's observable contract — the shared
parametrized test in tests/test_store_contract.py enforces this parity.

Blob operations delegate to the _blob helpers against a filesystem root
(not an in-memory dict) so the actual shard path logic is exercised in tests
(A1 assumption confirmed: we test real paths, not a memory shortcut).
"""
from pathlib import Path

from contracts import Item

from ._blob import get_blob as _get_blob
from ._blob import put_blob as _put_blob


class InMemoryStore:
    """Dict-backed Store implementation for in-process use in tests.

    Thread-safety: NOT thread-safe. Single-process scope only (matching
    Phase 1 InMemoryBus note). PostgresStore is the production impl.

    Usage:
        with InMemoryStore(blob_root=tmp_path / "blobs") as store:
            store.put_item(item)
            got = store.get_item(item.id)

    The context manager __enter__/__exit__ are no-ops (nothing to open or
    close), but are implemented for protocol compliance so the same caller
    code works for both InMemoryStore and PostgresStore.
    """

    def __init__(self, blob_root: Path) -> None:
        self._items: dict[str, Item] = {}
        self._blob_root = blob_root  # blobs written to disk, not kept in memory

    # Context manager — no-ops; implemented for Store Protocol compliance

    def __enter__(self) -> "InMemoryStore":
        return self

    def __exit__(self, *args) -> None:
        pass  # nothing to close for the in-memory fake

    # Schema — no-op for the fake (no DDL to apply)

    def init_schema(self) -> None:
        pass

    # Item CRUD

    def put_item(self, item: Item) -> None:
        """Upsert by item.id — last-write-wins (mirrors ON CONFLICT DO UPDATE)."""
        self._items[item.id] = item

    def get_item(self, item_id: str) -> Item | None:
        """Return Item or None on miss — never raises on absence."""
        return self._items.get(item_id)

    def list_items(
        self,
        source_type_in: list[str] | None = None,
        limit: int = 200,
    ) -> list[Item]:
        """Return items filtered and ordered by (ts DESC, id DESC).

        Empty list if no items match (never returns None).
        limit caps the result set (T-02-05 DoS mitigation — matches PostgresStore).
        """
        items = list(self._items.values())
        if source_type_in is not None:
            items = [i for i in items if i.source_type in source_type_in]
        items.sort(key=lambda i: (i.ts, i.id), reverse=True)
        return items[:limit]

    # Blob operations — delegate to _blob helpers (D-01a: same code path as PostgresStore)

    def put_blob(self, data: bytes) -> str:
        """Store bytes at content-addressed path; return sha256 hex.

        Delegates to _blob.put_blob so InMemoryStore exercises the same
        atomic write + shard path logic as PostgresStore (D-01a).
        """
        return _put_blob(self._blob_root, data)

    def get_blob(self, blob_hash: str) -> bytes:
        """Return bytes for blob_hash.

        Raises ValueError on invalid hash (T-02-02 traversal guard).
        Raises FileNotFoundError on miss.
        Delegates to _blob.get_blob (D-01a).
        """
        return _get_blob(self._blob_root, blob_hash)
