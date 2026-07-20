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

Phase 5 additions (D-05, D-06):
    - put_enrichment / get_enrichment — scoring results persistence (R1)
    - put_embedding / find_near_duplicate — pgvector semantic dedup (R4)
"""
from typing import Optional, Protocol, runtime_checkable

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

    # -------------------------------------------------------------------------
    # Enrichment persistence — D-05, R1
    # -------------------------------------------------------------------------

    def put_enrichment(self, item_id: str, fields: dict) -> None:
        """Upsert enrichment row for item_id. ON CONFLICT DO UPDATE all 7 columns.

        Args:
            item_id: article id (FK to infotriage.articles).
            fields: dict with any subset of ccir, cnr, score, bucket, why, pmesii, tessoc.

        Idempotent: calling twice with the same item_id updates in place, never errors.
        Security (V5/T-05-01): all SQL uses %s bind params — LLM output is opaque text.
        """
        ...

    def get_enrichment(self, item_id: str) -> Optional[dict]:
        """Return enrichment dict for item_id, or None if no enrichment row exists.

        Returns:
            dict with keys ccir, cnr, score, bucket, why, pmesii, tessoc; or None on miss.
        """
        ...

    # -------------------------------------------------------------------------
    # Embedding dedup — D-05, D-06, D-07, R4
    # -------------------------------------------------------------------------

    def put_embedding(self, item_id: str, vector: list[float]) -> None:
        """Upsert embedding vector for item_id into infotriage.embeddings.

        Idempotent: re-writing the same item_id updates the vector in place.
        Args:
            item_id: article id (FK to infotriage.articles).
            vector: 1024-dim float list (mE5-large dimension, D-05a).
        """
        ...

    def find_near_duplicate(
        self,
        vector: list[float],
        window_days: int = 7,
        threshold: float = 0.84,
    ) -> Optional[str]:
        """Return item_id of nearest duplicate within cosine threshold and time window.

        Postgres: uses <=> cosine distance operator with HNSW index; filters by
        created_at >= NOW() - INTERVAL window_days days (ADR-006, D-06).
        InMemoryStore: iterates stored vectors with stdlib cosine loop; window ignored (D-07).

        Args:
            vector: 1024-dim query vector.
            window_days: lookback window in days (ignored by InMemoryStore).
            threshold: cosine similarity threshold (default 0.84, mE5-large bake-off result).

        Returns:
            item_id of the nearest match if cosine_sim >= threshold, else None.
            Returns None when no embeddings are stored (first article is never a false positive).
        """
        ...

    # -------------------------------------------------------------------------
    # Entity resolution — Phase 8 (ADR-006)
    # -------------------------------------------------------------------------

    def put_entity(
        self,
        name: str,
        name_norm: str,
        lang: str,
        type: str | None,
        embedding: list[float] | None,
    ) -> str:
        """Upsert a canonical entity and return its id.

        Idempotent: ON CONFLICT (name_norm, lang) updates name, type, and embedding.
        A None embedding is stored as NULL and does not overwrite an existing vector
        (COALESCE preserves the prior vector).
        """
        ...

    def get_entity(self, entity_id: str) -> Optional[dict]:
        """Return entity dict for entity_id, or None if absent."""
        ...

    def get_entity_by_name_norm(self, name_norm: str, lang: str) -> Optional[dict]:
        """Return entity dict for (name_norm, lang), or None if absent."""
        ...

    def find_similar_entity(
        self,
        vector: list[float],
        threshold: float = 0.92,  # mE5-large validated T*; see 999.3-VERDICT.md
    ) -> Optional[dict]:
        """Return the nearest entity with cosine similarity >= threshold, or None.

        Only entities with a non-NULL embedding are considered. The returned dict
        contains at least ``entity_id`` and ``name``.
        """
        ...

    def link_entity(
        self, entity_id: str, item_id: str, mention: str, lang: str
    ) -> None:
        """Link an entity to an item with the surface mention and mention language.

        Idempotent: duplicate (entity_id, item_id, mention) links are ignored.
        """
        ...

    def get_entity_links(self, item_id: str) -> list[dict]:
        """Return entity-link rows for item_id joined to canonical entity names.

        Each row contains: entity_id, name, mention, lang.
        """
        ...

    def get_all_entities(self) -> list[dict]:
        """Return all canonical entities with language-tagged aliases and counts.

        Each dict contains: id, name, name_norm, lang, type, aliases,
        alias_count, link_count. aliases is a list of language-tagged strings in
        the form 'mention (lang)' (e.g. 'NATO (en)', 'НАТО (ru)'). Ordered by
        link_count DESC, then name_norm.
        """
        ...
