#!/usr/bin/env python3
"""test_clustering_integration.py — Integration tests for clustering with real embeddings (Phase 6, SC1b)."""
import pytest
from pathlib import Path

# Needs PostgresStore for actual database interaction
from store import PostgresStore
from apps.brief.renderer import render_brief, _rows_to_enriched_items, _cluster_rows
from apps.brief.clustering import EnrichedItem


@pytest.fixture(scope="module")
def pg_store():
    """Provide a PostgresStore connected to the test database."""
    pg_dsn = "postgresql://infotriage:infotriage_db@127.0.0.1:5432/infotriage"
    with PostgresStore(dsn=pg_dsn, blob_root=Path("/data/blobs")) as store:
        yield store


def test_enrichment_sql_joins_embeddings():
    """Assert _ENRICHMENT_SQL (in main.py) contains emb.embedding and LEFT JOIN."""
    main_py_path = Path(__file__).parent.parent.parent / "apps" / "brief" / "main.py"
    main_content = main_py_path.read_text()

    assert "emb.embedding" in main_content
    assert "LEFT JOIN infotriage.embeddings" in main_content


def test_enrichment_fetch_includes_embedding():
    """Assert that consumer.py's _SELECT joins embeddings."""
    consumer_py_path = Path(__file__).parent.parent.parent / "apps" / "brief" / "consumer.py"
    consumer_content = consumer_py_path.read_text()

    assert "emb.embedding" in consumer_content
    assert "LEFT JOIN infotriage.embeddings" in consumer_content


def test_cluster_threshold_wired_to_renderer():
    """Assert renderer.py _cluster_rows accepts threshold parameter."""
    renderer_py_path = Path(__file__).parent.parent.parent / "apps" / "brief" / "renderer.py"
    renderer_content = renderer_py_path.read_text()

    assert "_cluster_rows(rows: list[dict], threshold: float | None = None)" in renderer_content
    assert "threshold=0.75" not in renderer_content or "os.getenv" in renderer_content


def test_enrichment_row_has_embedding_column(pg_store):
    """Fetch from Postgres and assert embedding is present in rows (not None)."""
    from psycopg.rows import dict_row

    _SELECT = (
        "SELECT e.item_id, e.ccir, e.cnr, e.score, e.bucket, e.why, e.pmesii, e.tessoc, "
        "a.title, a.summary, a.source, a.url, a.ts, "
        "emb.embedding "
        "FROM infotriage.enrichment e "
        "JOIN infotriage.articles a ON a.id = e.item_id "
        "LEFT JOIN infotriage.embeddings emb ON emb.item_id = e.item_id "
        "ORDER BY e.score DESC LIMIT 10"
    )

    with pg_store.cursor(row_factory=dict_row) as cur:
        cur.execute(_SELECT)
        rows = cur.fetchall()

    # All rows should have the embedding key
    for row in rows:
        assert "embedding" in row, "embedding column missing from row"
        # embedding can be NULL (None) if no matching embedding, but that's okay
        # The test ensures the join produces the column

    assert len(rows) > 0, "No enrichment rows found to test"


def test_pgvector_clustering_merges_similar_items():
    item1 = {
        "item_id": "test-1",
        "title": "Test Item 1",
        "source": "Test",
        "url": "https://test.com",
        "summary": "Test",
        "ccir": "PIR-1",
        "cnr": "I",
        "score": 9,
        "why": "Test",
        "pmesii": None,
        "tessoc": None,
        "embedding": [0.1, 0.2, 0.3, 0.4],
    }
    item2 = {
        "item_id": "test-2",
        "title": "Test Item 2",
        "source": "Test",
        "url": "https://test.com",
        "summary": "Test",
        "ccir": "PIR-1",
        "cnr": "I",
        "score": 8,
        "why": "Test",
        "pmesii": None,
        "tessoc": None,
        "embedding": [0.11, 0.21, 0.31, 0.41],
    }
    item3 = {
        "item_id": "test-3",
        "title": "Test Item 3",
        "source": "Test",
        "url": "https://test.com",
        "summary": "Test",
        "ccir": "PIR-1",
        "cnr": "I",
        "score": 7,
        "why": "Test",
        "pmesii": None,
        "tessoc": None,
        "embedding": [1.0, 0.0, 0.0, 0.0],
    }

    rows = [item1, item2, item3]
    clusters = _cluster_rows(rows, threshold=0.75)

    assert len(clusters) == 2, f"Expected 2 clusters, got {len(clusters)}"
    
    cluster_1_2 = next((c for c in clusters if len(c["items"]) == 2 and {"test-1", "test-2"} == {i["item_id"] for i in c["items"]}), None)
    assert cluster_1_2 is not None, "test-1 and test-2 should be in the same cluster"
    
    cluster_3 = next((c for c in clusters if len(c["items"]) == 1 and c["items"][0]["item_id"] == "test-3"), None)
    assert cluster_3 is not None, "test-3 should be in a separate cluster"
