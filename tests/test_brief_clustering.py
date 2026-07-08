#!/usr/bin/env python3
"""Unit tests for apps.brief.clustering (Phase 6, Plan 06-02, Task 4).

Tests cover:
- Single cluster: similar items merge into one cluster
- Multiple clusters: similar items merge, dissimilar stay separate
- CCIR boundary: items in different CCIR sections never share a cluster
- Single-item cluster: no close match → singleton clusters
- Empty input: returns empty list, no exception
- Default threshold: verify 0.75 on both clustering functions
"""
import inspect
import math
import sys
import unittest

sys.path.insert(0, __import__("os").path.join(__import__("os").path.dirname(__file__), ".."))

from apps.brief.clustering import (
    EnrichedItem,
    _cosine_distance,
    cluster_items,
    cluster_items_in_memory,
)


# ---- helpers ----------------------------------------------------------------


def _item(
    item_id: str = "1",
    title: str = "Article",
    source: str = "src",
    url: str = "http://example.com",
    summary: str = "summary",
    ccir: str = "PIR-1",
    cnr: str = "I",
    score: int = 9,
    bucket: str = "read",
    why: str = "test",
    pmesii: str | None = None,
    tessoc: str | None = None,
    embedding: list[float] | None = None,
) -> EnrichedItem:
    """Factory for EnrichedItem with defaults."""
    return EnrichedItem(
        item_id=item_id,
        title=title,
        source=source,
        url=url,
        summary=summary,
        ccir=ccir,
        cnr=cnr,
        score=score,
        bucket=bucket,
        why=why,
        pmesii=pmesii,
        tessoc=tessoc,
        embedding=embedding or [1.0, 0.0, 0.0, 0.0],
    )


class TestCosineDistance(unittest.TestCase):
    """Verify _cosine_distance helper."""

    def test_identical_vectors(self):
        # Cosine distance of identical vectors = 0
        vec = [0.9, 0.1, 0.05, 0.05]
        self.assertAlmostEqual(_cosine_distance(vec, vec), 0.0, places=10)

    def test_opposite_vectors(self):
        # Orthogonal unit vectors → similarity = 0, distance = 1
        self.assertAlmostEqual(_cosine_distance([1.0, 0.0], [0.0, 1.0]), 1.0, places=10)

    def test_zero_vector(self):
        # Zero vector should return max distance (1.0)
        self.assertEqual(_cosine_distance([0.0, 0.0], [1.0, 0.0]), 1.0)

    def test_similar_vectors_low_distance(self):
        # Near-identical vectors → low distance
        dist = _cosine_distance([1.0, 0.0, 0.0], [0.99, 0.01, 0.0])
        self.assertLess(dist, 0.02, "Near-identical vectors should have low distance")


# ---- Test 1: Single Cluster -------------------------------------------------


class TestSingleCluster(unittest.TestCase):
    """3 items with nearly identical embeddings in the same CCIR section → 1 cluster."""

    def test_all_three_merge(self):
        items = [
            _item(
                item_id="1",
                title="Article 1",
                summary="s1",
                why="w1",
                embedding=[0.9, 0.1, 0.05, 0.05],
            ),
            _item(
                item_id="2",
                title="Article 2",
                summary="s2",
                why="w2",
                embedding=[0.85, 0.12, 0.03, 0.0],
            ),
            _item(
                item_id="3",
                title="Article 3",
                summary="s3",
                why="w3",
                embedding=[0.88, 0.09, 0.02, 0.01],
            ),
        ]
        clusters = cluster_items_in_memory(items, threshold=0.75)
        self.assertEqual(len(clusters), 1, "All 3 items should be in one cluster")
        self.assertEqual(len(clusters[0]), 3)


# ---- Test 2: Multiple Clusters ----------------------------------------------


class TestMultipleClusters(unittest.TestCase):
    """4 items: 2 similar (cosine > 0.75), 2 orthogonal → 3 clusters."""

    def test_two_merge_two_singleton(self):
        items = [
            _item(item_id="1", title="A", summary="m", why="w",
                  ccir="PIR-1", cnr="I", score=9,
                  embedding=[1.0, 0.0, 0.0, 0.0]),
            _item(item_id="2", title="B", summary="m", why="w",
                  ccir="PIR-1", cnr="I", score=8,
                  embedding=[0.9, 0.1, 0.0, 0.0]),
            _item(item_id="3", title="C", summary="m", why="w",
                  ccir="PIR-1", cnr="I", score=7,
                  embedding=[0.0, 1.0, 0.0, 0.0]),
            _item(item_id="4", title="D", summary="m", why="w",
                  ccir="PIR-1", cnr="I", score=6,
                  embedding=[0.0, 0.0, 1.0, 0.0]),
        ]
        clusters = cluster_items_in_memory(items, threshold=0.75)
        self.assertEqual(len(clusters), 3, "Expected 3 clusters")

        # Find the cluster with 2 items
        two_item = [c for c in clusters if len(c) == 2]
        self.assertEqual(len(two_item), 1, "Exactly one cluster should have 2 items")
        self.assertEqual(set(c.item_id for c in two_item[0]), {"1", "2"})

        # Remaining are singletons
        singletons = [c for c in clusters if len(c) == 1]
        self.assertEqual(len(singletons), 2)
        self.assertEqual(
            {c[0].item_id for c in singletons},
            {"3", "4"},
        )


# ---- Test 3: CCIR Boundary (Property-Based) ----------------------------------


class TestCcirBoundary(unittest.TestCase):
    """Items in different CCIR sections must never be in the same cluster."""

    def test_no_cross_ccir_clustering(self):
        # Create 5 items: 2 in PIR-1 (similar), 2 in PIR-2 (similar), 1 in PIR-3
        items = []
        for i, (ccir_id, emb) in enumerate([
            ("PIR-1", [0.9, 0.1, 0.0, 0.0]),
            ("PIR-1", [0.85, 0.12, 0.03, 0.0]),  # similar to first
            ("PIR-2", [0.9, 0.1, 0.0, 0.0]),      # same embedding but different CCIR
            ("PIR-2", [0.88, 0.08, 0.04, 0.0]),   # similar to previous CCIR-2
            ("PIR-3", [0.1, 0.1, 0.7, 0.1]),
        ]):
            items.append(_item(
                item_id=str(i),
                title=f"A{i}",
                ccir=ccir_id,
                score=9 - i,
                embedding=emb,
            ))

        clusters = cluster_items_in_memory(items, threshold=0.75)

        # Property: NO cluster should span 2+ CCIR sections
        for cluster in clusters:
            ccirs = set(item.ccir for item in cluster)
            self.assertEqual(
                len(ccirs),
                1,
                f"Cluster spans multiple CCIRs: {ccirs} — {cluster} items",
            )

        # PIR-1: items 0+1 merge (1 cluster), PIR-2: items 2+3 merge (1 cluster), PIR-3: item 4 singleton = 3 total
        self.assertEqual(len(clusters), 3)


# ---- Test 4: Single Item Clusters -------------------------------------------


class TestSingleItemCluster(unittest.TestCase):
    """Orthogonal items → each becomes a singleton cluster."""

    def test_all_singletons(self):
        items = [
            _item(item_id="1", ccir="PIR-1", score=9,
                  embedding=[1.0, 0.0, 0.0, 0.0]),
            _item(item_id="2", ccir="PIR-1", score=8,
                  embedding=[0.0, 1.0, 0.0, 0.0]),
            _item(item_id="3", ccir="PIR-1", score=7,
                  embedding=[0.0, 0.0, 1.0, 0.0]),
        ]
        clusters = cluster_items_in_memory(items, threshold=0.75)
        self.assertEqual(len(clusters), 3)
        for cluster in clusters:
            self.assertEqual(len(cluster), 1)

    def test_missing_embedding_passes_through_as_singleton(self):
        items = [
            _item(item_id="with-embedding", ccir="PIR-1", score=9, embedding=[1.0, 0.0]),
            EnrichedItem(
                item_id="without-embedding",
                title="No embedding",
                source="src",
                url="http://example.com/no-embedding",
                summary="summary",
                ccir="PIR-1",
                cnr="I",
                score=8,
                bucket="read",
                why="missing embedding",
                pmesii=None,
                tessoc=None,
                embedding=None,
            ),
        ]

        clusters = cluster_items_in_memory(items, threshold=0.75)
        cluster_ids = [set(item.item_id for item in cluster) for cluster in clusters]

        self.assertIn({"without-embedding"}, cluster_ids)


# ---- Test 5: Empty Input ----------------------------------------------------


class TestEmptyInput(unittest.TestCase):
    """0 items → empty list, no exception."""

    def test_empty_returns_empty_list(self):
        clusters = cluster_items_in_memory([], threshold=0.75)
        self.assertEqual(clusters, [])


# ---- Test 6: Default Threshold ----------------------------------------------


class TestThresholdDefault(unittest.TestCase):
    """Verify default threshold is 0.75 on both clustering functions."""

    def test_cluster_items_in_memory_default(self):
        sig = inspect.signature(cluster_items_in_memory)
        self.assertEqual(
            sig.parameters["threshold"].default,
            0.75,
            "cluster_items_in_memory default threshold should be 0.75",
        )

    def test_cluster_items_default(self):
        sig = inspect.signature(cluster_items)
        self.assertEqual(
            sig.parameters["threshold"].default,
            0.75,
            "cluster_items default threshold should be 0.75",
        )


if __name__ == "__main__":
    unittest.main()
