"""tests/test_ccir_vectors.py — Phase 9 CCIR vectors and recall search."""
from __future__ import annotations

import datetime
import os

import pytest

from store import InMemoryStore, PostgresStore

from tests.conftest import db_live, pg_store  # noqa: F401

@pytest.fixture
def inmemory_store(tmp_path):
    return InMemoryStore(blob_root=tmp_path / "blobs")


def _cosine_sim(a: list[float], b: list[float]) -> float:
    import math

    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def test_put_ccir_vector_and_find_similar(inmemory_store):
    store = inmemory_store
    vec = [1.0] + [0.0] * 1023
    store.put_ccir_vector("PIR-1", vec)
    result = store.find_similar_ccir(vec)
    assert result is not None
    assert result["ccir_id"] == "PIR-1"
    assert result["similarity"] == pytest.approx(1.0, abs=1e-6)


def test_find_similar_ccir_returns_nearest_even_when_far(inmemory_store):
    store = inmemory_store
    vec = [1.0] + [0.0] * 1023
    far = [0.0] * 1024
    store.put_ccir_vector("PIR-1", vec)
    result = store.find_similar_ccir(far)
    assert result is not None
    assert result["ccir_id"] == "PIR-1"
    assert result["similarity"] == pytest.approx(0.0, abs=1e-6)


def test_find_similar_ccir_returns_none_when_empty(inmemory_store):
    store = inmemory_store
    result = store.find_similar_ccir([1.0] * 1024)
    assert result is None


def test_recall_items_skips_by_default(inmemory_store):
    from contracts import Item

    store = inmemory_store
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    item = Item(
        source="nrk",
        source_type="rss",
        url="https://example.com/1",
        title="Arctic security",
        ts=now,
        lang="en",
        summary="test summary",
        body_ref=None,
        payload={},
    )
    store.put_item(item)
    store.put_embedding(item.id, [1.0] * 1024)
    store.put_enrichment(
        item.id,
        {"ccir": "PIR-2", "cnr": "II", "score": 6, "bucket": "skip", "why": "", "pmesii": "Military", "tessoc": "Espionage"},
    )
    results = store.recall_items([1.0] * 1024)
    assert results == []


def test_recall_items_filters_by_ccir(inmemory_store):
    from contracts import Item

    store = inmemory_store
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    for i, ccir in enumerate(["PIR-1", "PIR-2"]):
        item = Item(
            source="nrk",
            source_type="rss",
            url=f"https://example.com/{i}",
            title=f"Article {i}",
            ts=now,
            lang="en",
            summary=f"summary {i}",
            body_ref=None,
            payload={},
        )
        store.put_item(item)
        store.put_embedding(item.id, [float(i + 1)] * 1024)
        store.put_enrichment(
            item.id,
            {"ccir": ccir, "cnr": "II", "score": 6, "bucket": "keep", "why": "", "pmesii": "Military", "tessoc": "Espionage"},
        )

    results = store.recall_items([1.0] * 1024, ccir="PIR-1")
    assert len(results) == 1
    assert results[0]["ccir"] == "PIR-1"


def test_recall_items_filters_by_since(inmemory_store):
    from contracts import Item

    store = inmemory_store
    old = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
    new = datetime.datetime(2026, 7, 1, tzinfo=datetime.timezone.utc)
    for ts in [old, new]:
        item = Item(
            source="nrk",
            source_type="rss",
            url=f"https://example.com/{ts.timestamp()}",
            title="Article",
            ts=ts,
            lang="en",
            summary="summary",
            body_ref=None,
            payload={},
        )
        store.put_item(item)
        store.put_embedding(item.id, [1.0] * 1024)
        store.put_enrichment(
            item.id,
            {"ccir": "PIR-1", "cnr": "II", "score": 6, "bucket": "keep", "why": "", "pmesii": "Military", "tessoc": "Espionage"},
        )

    results = store.recall_items([1.0] * 1024, since=new)
    assert len(results) == 1
    assert results[0]["title"] == "Article"


def test_audit_write(inmemory_store):
    store = inmemory_store
    store.audit_write(op="pre_filter_skip", table_name="enrichment", item_id="x", details={"foo": 1})
    assert len(store._audit) == 1
    assert store._audit[0]["op"] == "pre_filter_skip"
    assert store._audit[0]["details"] == {"foo": 1}


# ---------------------------------------------------------------------------
# db_live Postgres coverage
# ---------------------------------------------------------------------------


def _unit(dim: int = 1024) -> list[float]:
    vec = [0.0] * dim
    vec[0] = 1.0
    return vec


@db_live
def test_put_ccir_vector_and_find_similar_db_live(pg_store):
    from contracts import Item

    pg_store.put_ccir_vector("PIR-1", _unit())
    result = pg_store.find_similar_ccir(_unit())
    assert result is not None
    assert result["ccir_id"] == "PIR-1"
    assert result["similarity"] == pytest.approx(1.0, abs=1e-6)


@db_live
def test_find_similar_ccir_returns_nearest_below_threshold_db_live(pg_store):
    vec = _unit()
    far = [0.0] * 1024
    far[1] = 1.0
    pg_store.put_ccir_vector("PIR-1", vec)
    result = pg_store.find_similar_ccir(far)
    assert result is not None
    assert result["ccir_id"] == "PIR-1"
    assert result["similarity"] == pytest.approx(0.0, abs=1e-6)


@db_live
def test_recall_items_db_live(pg_store):
    from contracts import Item

    now = datetime.datetime.now(tz=datetime.timezone.utc)
    item = Item(
        source="nrk",
        source_type="rss",
        url="https://example.com/1",
        title="Arctic security",
        ts=now,
        lang="en",
        summary="summary",
        body_ref=None,
        payload={},
    )
    pg_store.put_item(item)
    pg_store.put_embedding(item.id, _unit())
    pg_store.put_enrichment(
        item.id,
        {"ccir": "PIR-2", "cnr": "II", "score": 6, "bucket": "keep", "why": "", "pmesii": "Military", "tessoc": "Espionage"},
    )
    results = pg_store.recall_items(_unit(), ccir="PIR-2")
    assert len(results) == 1
    assert results[0]["item_id"] == item.id
    assert results[0]["ccir"] == "PIR-2"


@db_live
def test_audit_write_db_live(pg_store):
    pg_store.audit_write(op="pre_filter_skip", table_name="enrichment", item_id="x", details={"foo": 1})
    row = pg_store._conn.execute(
        "SELECT op, table_name, item_id, details FROM infotriage.audit WHERE item_id = %s",
        ("x",),
    ).fetchone()
    pg_store._conn.rollback()
    assert row is not None
    assert row["op"] == "pre_filter_skip"
    assert row["details"] == {"foo": 1}
