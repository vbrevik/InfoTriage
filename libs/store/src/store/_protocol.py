#!/usr/bin/env python3
"""_protocol.py — Store Protocol: single mediating interface for all InfoTriage persistence.

Mirrors the BusClient Protocol in libs/contracts/src/contracts/_bus.py (same
@runtime_checkable decorator, same docstring style, same ... body stubs).

Implementations:
    - PostgresStore (production, plan 03) — psycopg3 + pgvector
    - InMemoryStore (tests) — dict-backed fake

Context manager: each implementation opens and closes its underlying resource
in __enter__/__exit__ (connection for Postgres; no-op for InMemory).

Per D-01a: blob operations (put_blob/get_blob) live on this single Store
interface — there is no separate BlobStore class exposed to callers.
"""
from typing import Protocol, runtime_checkable

from contracts import Item


@runtime_checkable
class Store(Protocol):
    """Single mediating interface for all InfoTriage persistence.

    Implementations: PostgresStore (production), InMemoryStore (tests).
    Context manager: opens and closes the underlying connection/resource.

    Any class with matching method signatures satisfies this Protocol without
    explicit inheritance (PEP 544 structural subtyping).
    """

    def __enter__(self) -> "Store":
        """Open the underlying resource (connection, file handle, etc.)."""
        ...

    def __exit__(self, *args) -> None:
        """Close the underlying resource. Commit on success, rollback on error."""
        ...

    def init_schema(self) -> None:
        """Apply all DDL idempotently. Safe to call on an existing schema.

        For PostgresStore: runs versioned SQL files under libs/store/sql/ in order.
        For InMemoryStore: no-op.
        """
        ...

    def put_item(self, item: Item) -> None:
        """Upsert item by item.id (last-write-wins). Raises on persistence failure.

        Must not silently swallow errors — a failed persist must raise (must-NOT).
        """
        ...

    def get_item(self, item_id: str) -> Item | None:
        """Return the Item for item_id, or None on miss. Never raises on absence."""
        ...

    def list_items(
        self,
        source_type_in: list[str] | None = None,
        limit: int = 200,
    ) -> list[Item]:
        """Return items ordered by (ts DESC, id DESC). Empty list on no match.

        Args:
            source_type_in: if given, filter to items whose source_type is in
                            this list (e.g. ["rss", "yt"] to exclude email).
            limit: maximum number of items to return (T-02-05 DoS mitigation).

        Returns:
            list of Item (possibly empty — never None).
        """
        ...

    def put_blob(self, data: bytes) -> str:
        """Store bytes at a content-addressed sharded path. Returns sha256 hex.

        Duplicate put of identical bytes is a no-op (idempotency, R4).
        Raises on any write failure — never returns success on a failed write.
        """
        ...

    def get_blob(self, blob_hash: str) -> bytes:
        """Return bytes for the blob identified by blob_hash.

        Raises:
            ValueError: if blob_hash is not a 64-char lowercase hex string (T-02-02).
            FileNotFoundError: if no blob with that hash has been stored.
        """
        ...
