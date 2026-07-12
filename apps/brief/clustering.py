#!/usr/bin/env python3
"""clustering.py — pgvector HNSW semantic clustering for the Brief App.

Clusters enriched items within each CCIR section using cosine similarity on
the mE5-large embeddings already populated by Phase 5 (worker.py).

Uses the same SQL patterns as PostgresStore.find_near_duplicate():
  - pgvector <=> cosine distance operator (NOT <-> L2)
  - %s bind params everywhere (never f-string SQL)
  - register_vector() already called by PostgresStore.__enter__

Threshold: cosine similarity threshold (0.0-1.0). Converts to pgvector
distance as: max_dist = 1.0 - threshold. Default 0.75, configurable via
CLUSTER_THRESHOLD env var (wired in main.py).

Greedy assignment clustering:
  1. For each CCIR section, fetch enriched items + embeddings.
  2. Sort items by score descending.
  3. For each item, find nearest cluster centroid within max_dist.
  4. Add to that cluster if found; otherwise start a new singleton.
  5. Return list[list[EnrichedItem]] — each inner list is a cluster.

Acceptance criterion (from 06-SPEC.md R4):
  Given 3 NATO articles (2 Ukraine defense, 1 Arctic policy), pgvector
  clustering with threshold 0.75 merges only the 2 Ukraine articles —
  the Arctic article remains a separate single-item cluster.
"""
import os
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from store._postgres import PostgresStore  # noqa: F401


@dataclass
class EnrichedItem:
    """Enriched item with embedding vector.

    Mirrors the enrichment row keys + embedding from the database query.
    Fields match the enrichment row keys defined in the store contract:
      item_id, ccir, cnr, score, bucket, why, pmesii, tessoc
    Plus article fields:
      title, summary, source, url
    Plus embedding from infotriage.embeddings table.
    """

    item_id: str
    title: str
    source: str
    url: str
    summary: str
    ccir: str
    cnr: str
    score: int
    bucket: str
    why: str
    pmesii: str | None
    tessoc: str | None
    embedding: list[float] | None


def _as_list(vec) -> list[float]:
    """Convert pgvector Vector or any iterable to list[float]."""
    if isinstance(vec, list):
        return cast(list[float], vec)
    if hasattr(vec, "to_list"):
        return cast(list[float], vec.to_list())
    return cast(list[float], list(vec))


def _cosine_distance(a: list[float], b: list[float]) -> float:
    """Compute cosine distance between two equal-length float vectors.

    Cosine distance = 1 - cosine similarity. This is exactly what pgvector's
    <=> operator returns, so we use the same metric for the in-memory fallback.

    Returns 1.0 for zero vectors (maximum distance).
    """
    a = _as_list(a)
    b = _as_list(b)
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 1.0
    similarity = dot / (norm_a * norm_b)
    return 1.0 - similarity


def cluster_items(
    store: "PostgresStore",
    ccir_sections: list[tuple[str, str]],
    threshold: float = 0.75,
    window_hours: int = 24,
) -> list[list[EnrichedItem]]:
    """Cluster enriched items by semantic similarity within each CCIR section.

    Uses pgvector <=> cosine distance operator on the infotriage.embeddings
    table. Clustering is greedy: items are processed in descending score order,
    and each item is added to the nearest existing cluster (by centroid) if
    the cosine distance is below the threshold.

    Items in different CCIR sections are never merged — clustering runs
    independently per section.

    Args:
        store: Open PostgresStore instance (must be used inside `with` block).
               Must have pgvector registered (PostgresStore.__enter__ does this).
        ccir_sections: List of (ccir_id, ccir_title) tuples. Only these CCIR
                       sections are queried; items outside are ignored.
        threshold: Cosine similarity threshold for merging (0.0-1.0).
                   Equivalent pgvector max distance: 1.0 - threshold.
        window_hours: Time window in hours for item selection (default 24).

    Returns:
        list[list[EnrichedItem]] — each inner list is a cluster with >= 1 item.
    """
    # Convert similarity threshold to pgvector distance:
    # pgvector <=> returns distance (0 = identical, 2 = opposite),
    # similarity = 1 - distance, so distance <= 1 - threshold.
    max_dist = 1.0 - threshold

    # Build CCIR lookup for filtering
    ccir_ids = [cid for cid, _ in ccir_sections]

    # Query enrichment + articles + embeddings for items in these CCIRs
    # within the time window. Joined so we get all fields in one query.
    query = """
        SELECT e.item_id, e.ccir, e.cnr, e.score, e.bucket, e.why,
               e.pmesii, e.tessoc,
               a.title, a.summary, a.source, a.url
        FROM infotriage.enrichment e
        JOIN infotriage.articles a ON a.id = e.item_id
        WHERE e.ccir = ANY(%s)
          AND e.created_at >= NOW() - CAST(%s AS interval)
        ORDER BY e.score DESC
    """

    cursor = store.cursor()
    rows = cursor.execute(
        query,
        (ccir_ids, f"{window_hours} hours"),
    ).fetchall()
    cursor.close()

    # Collect item_ids for a batch embedding lookup
    item_ids = [row["item_id"] for row in rows]
    if not item_ids:
        return []

    # Fetch embeddings in a single query
    # ANY(%s) used instead
    emb_query = """
        SELECT item_id, embedding
        FROM infotriage.embeddings
        WHERE item_id = ANY(%s)
    """
    emb_cursor = store.cursor()
    emb_rows = emb_cursor.execute(emb_query, (item_ids,)).fetchall()
    emb_cursor.close()

    # Build embedding lookup: item_id -> embedding vector
    embedding_map: dict[str, list[float]] = {
        row["item_id"]: row["embedding"] for row in emb_rows
    }

    # Build EnrichedItem objects. Items without embeddings pass through as
    # singleton clusters because they cannot be compared semantically.
    items_by_ccir: dict[str, list[EnrichedItem]] = {}
    for row in rows:
        emb = embedding_map.get(row["item_id"])
        item = EnrichedItem(
            item_id=row["item_id"],
            title=row["title"],
            source=row["source"],
            url=row["url"],
            summary=row["summary"],
            ccir=row["ccir"],
            cnr=row["cnr"],
            score=row["score"],
            bucket=row["bucket"],
            why=row["why"],
            pmesii=row["pmesii"],
            tessoc=row["tessoc"],
            embedding=emb,
        )
        cid = (row["ccir"] or "none").upper()
        items_by_ccir.setdefault(cid, []).append(item)

    # Greedy assignment clustering per CCIR section
    all_clusters: list[list[EnrichedItem]] = []

    for cid, _ in ccir_sections:
        items = items_by_ccir.get(cid, [])
        if not items:
            continue

        # Sort by score descending (higher score processed first)
        items.sort(key=lambda i: -i.score)

        # Clusters: list of (centroid_vector, [items])
        clusters: list[tuple[list[float], list[EnrichedItem]]] = []

        for item in items:
            if item.embedding is None:
                clusters.append(([], [item]))
                continue

            best_cluster_idx: int | None = None
            best_dist = max_dist

            for idx, (centroid, _) in enumerate(clusters):
                if not centroid:
                    continue
                dist = _cosine_distance(item.embedding, centroid)
                if dist < best_dist:
                    best_dist = dist
                    best_cluster_idx = idx

            if best_cluster_idx is not None:
                # Add to nearest cluster, update centroid
                cluster_items = clusters[best_cluster_idx][1]
                cluster_items.append(item)
                # Recompute centroid as mean of all embeddings in cluster
                n = len(cluster_items)
                dim = len(item.embedding)
                new_centroid: list[float] = [0.0] * dim
                for ci in cluster_items:
                    if ci.embedding is None:
                        continue
                    for d in range(dim):
                        new_centroid[d] += ci.embedding[d]
                clusters[best_cluster_idx] = (
                    [v / n for v in new_centroid],
                    cluster_items,
                )
            else:
                # New singleton cluster
                clusters.append((list(item.embedding), [item]))

        # Extract cluster item lists (remove centroids)
        for _, cluster_items in clusters:
            all_clusters.append(cluster_items)

    return all_clusters


def cluster_items_in_memory(
    items: list[EnrichedItem],
    threshold: float = 0.75,
) -> list[list[EnrichedItem]]:
    """Pure-Python fallback clustering using cosine distance in-memory.

    Implements the same greedy assignment algorithm as cluster_items() but
    operates entirely in Python using _cosine_distance(). This enables
    unit tests without requiring a Postgres/pgvector connection.

    Items without embeddings cannot be compared semantically, so they pass
    through as singleton clusters.

    Args:
        items: List of EnrichedItem with embedding vectors already populated.
        threshold: Cosine similarity threshold (0.0-1.0).
                   Same default as cluster_items().

    Returns:
        list[list[EnrichedItem]] — each inner list is a cluster with >= 1 item.

    Example:
        >>> items = [
        ...     EnrichedItem(..., embedding=[0.9, 0.1, ...]),
        ...     EnrichedItem(..., embedding=[0.85, 0.15, ...]),
        ...     EnrichedItem(..., embedding=[0.1, 0.9, ...]),
        ... ]
        >>> clusters = cluster_items_in_memory(items, threshold=0.75)
        >>> len(clusters)  # 2 clusters: [item0, item1] and [item2]
        2
    """
    if not items:
        return []

    max_dist = 1.0 - threshold

    # Group by CCIR section (mirrors cluster_items() per-section logic).
    # Items in different CCIR sections are never merged.
    items_by_ccir: dict[str, list[EnrichedItem]] = {}
    for item in items:
        items_by_ccir.setdefault(item.ccir, []).append(item)

    all_clusters: list[list[EnrichedItem]] = []

    for ccir_id, ccir_items in items_by_ccir.items():
        # Sort by score descending
        ccir_items.sort(key=lambda i: -i.score)

        # Each CCIR section has its own cluster list and centroids.
        section_clusters: list[list[EnrichedItem]] = []
        centroids: list[list[float]] = []

        for item in ccir_items:
            if item.embedding is None:
                section_clusters.append([item])
                continue

            best_idx: int | None = None
            best_dist = max_dist
            for idx, centroid in enumerate(centroids):
                dist = _cosine_distance(item.embedding, centroid)
                if dist < best_dist:
                    best_dist = dist
                    best_idx = idx

            if best_idx is not None:
                section_clusters[best_idx].append(item)
                # Update centroid
                cluster = section_clusters[best_idx]
                n = len(cluster)
                item_emb = _as_list(item.embedding)
                dim = len(item_emb)
                new_centroid = [0.0] * dim
                for ci in cluster:
                    if ci.embedding is None:
                        continue
                    ci_emb = _as_list(ci.embedding)
                    for d in range(dim):
                        new_centroid[d] += ci_emb[d]
                centroids[best_idx] = [v / n for v in new_centroid]
            else:
                section_clusters.append([item])
                centroids.append(_as_list(item.embedding))

        all_clusters.extend(section_clusters)

    return all_clusters
