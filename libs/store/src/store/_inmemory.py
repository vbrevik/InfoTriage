#!/usr/bin/env python3
"""_inmemory.py — dict-backed Store fake for unit tests.

Mirrors InMemoryBus in libs/contracts/src/contracts/_bus.py (same dict-backed
shape, no external deps, no thread-safety for single-process scope).

Must not diverge from PostgresStore's observable contract — the shared
parametrized test in tests/test_store_contract.py enforces this parity.

Blob operations delegate to the _blob helpers against a filesystem root
(not an in-memory dict) so the actual shard path logic is exercised in tests
(A1 assumption confirmed: we test real paths, not a memory shortcut).

Phase 5 additions (D-05, D-06, D-07):
    - _enrichments dict: item_id → 7-field enrichment dict
    - _embeddings dict: item_id → list[float] vector
    - _cosine_sim: stdlib cosine similarity helper for find_near_duplicate
"""
import math
from collections import defaultdict
from pathlib import Path
from typing import Optional, cast

from contracts import Item

from ._blob import get_blob as _get_blob
from ._blob import put_blob as _put_blob


def _cosine_sim(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two equal-length float vectors using stdlib math.

    Returns 0.0 for zero vectors (no division by zero). Implements D-07:
    InMemoryStore cosine loop so worker tests need no live pgvector.
    """
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


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
        # Phase 5 state: enrichment and embedding dicts (D-05, D-07)
        self._enrichments: dict[str, dict] = {}
        self._embeddings: dict[str, list[float]] = {}
        # Phase 8 state: entity resolution (ADR-006)
        self._entities: dict[tuple[str, str], dict] = {}
        self._entity_links: dict[tuple[str, str, str], dict] = {}

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

    # -------------------------------------------------------------------------
    # Enrichment persistence — D-05, R1
    # -------------------------------------------------------------------------

    def put_enrichment(self, item_id: str, fields: dict) -> None:
        """Upsert enrichment row for item_id. Last-write-wins, no duplicate error.

        Mirrors ON CONFLICT DO UPDATE semantics of PostgresStore.
        """
        self._enrichments[item_id] = {
            "ccir": fields.get("ccir"),
            "cnr": fields.get("cnr"),
            "score": fields.get("score"),
            "bucket": fields.get("bucket"),
            "why": fields.get("why"),
            "pmesii": fields.get("pmesii"),
            "tessoc": fields.get("tessoc"),
        }

    def get_enrichment(self, item_id: str) -> Optional[dict]:
        """Return enrichment dict for item_id, or None if absent."""
        return self._enrichments.get(item_id)

    # -------------------------------------------------------------------------
    # Embedding dedup — D-05, D-06, D-07
    # -------------------------------------------------------------------------

    def put_embedding(self, item_id: str, vector: list[float]) -> None:
        """Upsert embedding vector for item_id. Last-write-wins, no duplicate error.

        Mirrors ON CONFLICT DO UPDATE semantics of PostgresStore.
        """
        self._embeddings[item_id] = list(vector)

    def find_near_duplicate(
        self,
        vector: list[float],
        window_days: int = 7,
        threshold: float = 0.84,
    ) -> Optional[str]:
        """Return item_id of nearest stored embedding with cosine_sim >= threshold, or None.

        InMemoryStore implementation (D-07): iterates all stored vectors using stdlib
        _cosine_sim helper. window_days is ignored (no timestamps in the fake).
        Returns None when no embeddings are stored (first article is never a false positive).
        """
        best_id: Optional[str] = None
        best_sim: float = -1.0
        for stored_id, stored_vec in self._embeddings.items():
            sim = _cosine_sim(vector, stored_vec)
            if sim > best_sim:
                best_sim = sim
                best_id = stored_id
        if best_sim >= threshold:
            return best_id
        return None

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

        Idempotent: keyed by (name_norm, lang). A None embedding does not overwrite
        an existing vector.
        """
        key = (name_norm, lang)
        existing = self._entities.get(key)
        if existing is not None:
            # Preserve existing embedding if new embedding is None.
            if embedding is None:
                embedding = existing.get("embedding")
            existing.update(
                {
                    "name": name,
                    "type": type,
                    "embedding": embedding,
                }
            )
            return cast(str, existing["id"])
        entity_id = str(len(self._entities) + 1)
        self._entities[key] = {
            "id": entity_id,
            "name": name,
            "name_norm": name_norm,
            "lang": lang,
            "type": type,
            "embedding": embedding,
        }
        return entity_id

    def get_entity(self, entity_id: str) -> Optional[dict]:
        """Return entity dict for entity_id, or None if absent."""
        for entity in self._entities.values():
            if entity["id"] == entity_id:
                return dict(entity)
        return None

    def get_entity_by_name_norm(self, name_norm: str, lang: str) -> Optional[dict]:
        """Return entity dict for (name_norm, lang), or None if absent."""
        entity = self._entities.get((name_norm, lang))
        if entity is not None:
            return dict(entity)
        return None

    def find_similar_entity(
        self,
        vector: list[float],
        threshold: float = 0.92,  # mE5-large validated T*; see 999.3-VERDICT.md
    ) -> Optional[dict]:
        """Return the nearest entity with cosine similarity >= threshold, or None."""
        best_id: Optional[str] = None
        best_name: Optional[str] = None
        best_sim: float = -1.0
        for entity in self._entities.values():
            stored = entity.get("embedding")
            if stored is None:
                continue
            sim = _cosine_sim(vector, stored)
            if sim > best_sim:
                best_sim = sim
                best_id = entity["id"]
                best_name = entity["name"]
        if best_sim >= threshold:
            return {"entity_id": best_id, "name": best_name}
        return None

    def link_entity(
        self, entity_id: str, item_id: str, mention: str, lang: str
    ) -> None:
        """Link an entity to an item with the surface mention and mention language."""
        key = (entity_id, item_id, mention)
        if key not in self._entity_links:
            self._entity_links[key] = {
                "entity_id": entity_id,
                "item_id": item_id,
                "mention": mention,
                "lang": lang,
            }

    def get_entity_links(self, item_id: str) -> list[dict]:
        """Return entity-link rows for item_id joined to canonical entity names."""
        results = []
        for link in self._entity_links.values():
            if link["item_id"] == item_id:
                entity = self.get_entity(link["entity_id"])
                if entity is not None:
                    results.append(
                        {
                            "entity_id": link["entity_id"],
                            "name": entity["name"],
                            "type": entity["type"],
                            "mention": link["mention"],
                            "lang": link["lang"],
                        }
                    )
        results.sort(key=lambda r: (r["name"], r["mention"]))
        return results

    def get_all_entities(self) -> list[dict]:
        """Return all canonical entities with language-tagged aliases and counts."""
        # Build per-entity aggregate stats from stored links.
        alias_map: dict[str, set[str]] = defaultdict(set)
        item_map: dict[str, set[str]] = defaultdict(set)
        for link in self._entity_links.values():
            entity_id = link["entity_id"]
            alias_map[entity_id].add(f"{link['mention']} ({link['lang']})")
            item_map[entity_id].add(link["item_id"])

        results = []
        for entity in self._entities.values():
            entity_id = entity["id"]
            aliases = sorted(alias_map.get(entity_id, set()))
            results.append(
                {
                    "id": entity_id,
                    "name": entity["name"],
                    "name_norm": entity["name_norm"],
                    "lang": entity["lang"],
                    "type": entity["type"],
                    "aliases": aliases,
                    "link_count": len(item_map.get(entity_id, set())),
                }
            )

        results.sort(key=lambda r: (-r["link_count"], r["name_norm"]))
        return results
