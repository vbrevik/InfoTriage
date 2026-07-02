#!/usr/bin/env python3
"""tests/test_triage_enrichment.py — contract tests for enrichment + embedding store methods.

Tests run against both InMemoryStore and PostgresStore. The postgres param is
auto-skipped when :22000 is unreachable (via skipif mark on the fixture param).
Standalone postgres-only tests (test_enrichment_schema, test_enrichment_score_check)
carry the registered db_live marker so `pytest -m db_live` selects them.

Covers D-05, D-06, D-07, R1, R4:
  - put_enrichment / get_enrichment round-trip and idempotency (R1)
  - score CHECK constraint (postgres only, R1 boundary edge)
  - put_embedding idempotency (R4)
  - find_near_duplicate with near/far/empty cases (R4, D-06)
  - infotriage.enrichment column presence after init_schema() (postgres only)
"""
import datetime
import math
import os
import socket

import pytest

from contracts import Item
from store import InMemoryStore, Store


# ---------------------------------------------------------------------------
# db_live marker helpers
# ---------------------------------------------------------------------------

def _pg_reachable() -> bool:
    """Return True if Postgres :22000 accepts a TCP connection within 1 second."""
    try:
        with socket.create_connection(("localhost", 22000), timeout=1.0):
            return True
    except OSError:
        return False


_PG_UP = _pg_reachable()  # evaluated once at collection time

# db_live + skipif marks for fixture parametrization: the registered 'db_live' marker
# (so `pytest -m "not db_live"` actually deselects this fixture's postgres variant —
# a plain skipif-only mark here would NOT carry the db_live marker, since skipif and
# db_live are two independent marks, not one) plus auto-skip when PG is unreachable.
_pg_live_skipif = (
    pytest.mark.db_live,
    pytest.mark.skipif(
        not _PG_UP,
        reason="Postgres :22000 unreachable — integration test skipped",
    ),
)


def db_live(fn):
    """Decorator for standalone postgres-only test functions.

    Applies both the registered 'db_live' named marker (for -m db_live selection)
    and a skipif mark (for auto-skip when :22000 is unreachable).
    Mirrors the pattern in tests/test_store_integration.py.
    """
    fn = pytest.mark.db_live(fn)
    fn = pytest.mark.skipif(
        not _PG_UP,
        reason="Postgres :22000 unreachable — integration test skipped",
    )(fn)
    return fn


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEV_DSN = "postgresql://infotriage:infotriage_dev@localhost:22000/infotriage"
DIM = 1024  # locked embedding dimension (D-05a, mE5-large)


# ---------------------------------------------------------------------------
# Vector fixtures
# ---------------------------------------------------------------------------

def _vec_base() -> list[float]:
    """1024-dim unit vector along dimension 0."""
    return [1.0] + [0.0] * (DIM - 1)


def _vec_near() -> list[float]:
    """1024-dim unit vector near _vec_base: cosine_sim = 0.9 >= 0.84 threshold.

    Constructed as [cos(θ), sin(θ), 0, ...] where cos(θ) = 0.9.
    Magnitude: sqrt(0.9^2 + sin^2) = 1.0 (unit vector).
    """
    sin_val = math.sqrt(1.0 - 0.9 ** 2)  # ≈ 0.4359
    return [0.9, sin_val] + [0.0] * (DIM - 2)


def _vec_far() -> list[float]:
    """1024-dim unit vector orthogonal to _vec_base: cosine_sim = 0.0 < 0.84."""
    return [0.0, 1.0] + [0.0] * (DIM - 2)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_dsn() -> str:
    return os.environ.get("INFOTRIAGE_PG_DSN", DEV_DSN)


def _truncate_all(dsn: str) -> None:
    """TRUNCATE all infotriage tables for per-test isolation."""
    import psycopg
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(
            "TRUNCATE infotriage.entity_links, infotriage.embeddings, "
            "infotriage.enrichment, infotriage.ccir, infotriage.audit, "
            "infotriage.articles, infotriage.entities RESTART IDENTITY"
        )


def _ts() -> datetime.datetime:
    return datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)


def _make_item(**kwargs) -> Item:
    defaults = dict(
        source="TestSource",
        source_type="rss",
        url="https://example.com/enrichment-test",
        title="Enrichment Test Item",
        ts=_ts(),
        lang="en",
    )
    defaults.update(kwargs)
    return Item(**defaults)


# ---------------------------------------------------------------------------
# Parametrized store fixture
# ---------------------------------------------------------------------------

@pytest.fixture(
    params=[
        "inmemory",
        pytest.param("postgres", marks=_pg_live_skipif),
    ]
)
def store(request, tmp_path):
    """Yield a fresh Store implementation for each parametrized variant.

    Mirrors tests/test_store_contract.py: a pytest fixture parametrized over
    'inmemory' and (db_live-skipif-marked) 'postgres'.
    """
    if request.param == "inmemory":
        yield InMemoryStore(blob_root=tmp_path / "blobs")
    else:
        from store import PostgresStore
        dsn = _get_dsn()
        _truncate_all(dsn)
        with PostgresStore(dsn=dsn, blob_root=tmp_path / "blobs") as s:
            s.init_schema()
            yield s


# ---------------------------------------------------------------------------
# Seed helper: enrichment FK references infotriage.articles(id)
# ---------------------------------------------------------------------------

def _seed_item(store) -> Item:
    """Put a minimal Item into the store and return it.

    Required before any enrichment/embedding write because both tables
    have a FK to infotriage.articles(id). The InMemoryStore has no FK
    enforcement but the same seed pattern is used for parity.
    """
    item = _make_item()
    store.put_item(item)
    return item


# ---------------------------------------------------------------------------
# Tests — enrichment round-trip and idempotency
# ---------------------------------------------------------------------------

def test_put_get_enrichment(store):
    """put_enrichment then get_enrichment returns dict with all 7 fields equal to what was written."""
    item = _seed_item(store)
    fields = {
        "ccir": "PIR-1",
        "cnr": "I",
        "score": 7,
        "bucket": "keep",
        "why": "NATO article",
        "pmesii": "Military",
        "tessoc": "Neutral",
    }
    store.put_enrichment(item.id, fields)
    got = store.get_enrichment(item.id)
    assert got is not None, "get_enrichment must return dict after put_enrichment"
    for key, expected in fields.items():
        assert got[key] == expected, f"Field '{key}': expected {expected!r}, got {got[key]!r}"


def test_put_enrichment_idempotent(store):
    """put_enrichment twice for the same item_id updates in place — no duplicate-row error."""
    item = _seed_item(store)
    store.put_enrichment(item.id, {
        "ccir": "PIR-1", "cnr": "I", "score": 5,
        "bucket": "keep", "why": "first write",
        "pmesii": "Political", "tessoc": "Neutral",
    })
    store.put_enrichment(item.id, {
        "ccir": "PIR-2", "cnr": "II", "score": 3,
        "bucket": "maybe", "why": "second write",
        "pmesii": "Military", "tessoc": "Enemy",
    })
    got = store.get_enrichment(item.id)
    assert got is not None
    assert got["ccir"] == "PIR-2", "Second write must win (idempotent upsert)"
    assert got["score"] == 3, "Second write must win"
    assert got["why"] == "second write", "Second write must win"


# ---------------------------------------------------------------------------
# Test — score CHECK constraint (postgres only, db_live)
# ---------------------------------------------------------------------------

@db_live
def test_enrichment_score_check(tmp_path):
    """put_enrichment with score=11 raises a DB error — CHECK (score BETWEEN 0 AND 10).

    Postgres only: the InMemoryStore has no schema-level CHECK constraint.
    The worker is responsible for clamping score to [0, 10] before calling put_enrichment.
    """
    from store import PostgresStore
    dsn = _get_dsn()
    _truncate_all(dsn)
    with PostgresStore(dsn=dsn, blob_root=tmp_path / "blobs") as s:
        s.init_schema()
        item = _make_item()
        s.put_item(item)
        with pytest.raises(Exception):
            s.put_enrichment(item.id, {
                "ccir": "X", "cnr": "I", "score": 11,
                "bucket": "skip", "why": "out-of-range score test",
                "pmesii": "P", "tessoc": "T",
            })
        # Rollback aborted transaction so context-manager __exit__ can close cleanly
        s._conn.rollback()


# ---------------------------------------------------------------------------
# Tests — embedding dedup (find_near_duplicate)
# ---------------------------------------------------------------------------

def test_find_near_duplicate(store):
    """put_embedding then find_near_duplicate with near vec returns item_id; far vec returns None."""
    item = _seed_item(store)
    store.put_embedding(item.id, _vec_base())

    # Near vector: cosine_sim = 0.9 >= 0.84 → should match
    result_near = store.find_near_duplicate(_vec_near())
    assert result_near == item.id, (
        f"Near vector (cos_sim=0.9) must match stored item_id; got {result_near!r}"
    )

    # Far vector: cosine_sim = 0.0 < 0.84 → should NOT match
    result_far = store.find_near_duplicate(_vec_far())
    assert result_far is None, (
        f"Far vector (cos_sim=0.0) must return None; got {result_far!r}"
    )


def test_find_near_duplicate_empty(store):
    """With no embeddings stored, find_near_duplicate returns None.

    First article in a window is never a false-positive duplicate (R4 unclassified edge).
    """
    result = store.find_near_duplicate(_vec_base())
    assert result is None, (
        f"Empty store must return None from find_near_duplicate; got {result!r}"
    )


def test_put_embedding_idempotent(store):
    """put_embedding twice for same item_id updates in place — stored vector is the second write."""
    item = _seed_item(store)
    store.put_embedding(item.id, _vec_base())
    store.put_embedding(item.id, _vec_far())  # second write: far vector replaces base vector

    # After second write, the stored vector is _vec_far (cosine_sim=0 with _vec_base).
    # find_near_duplicate(_vec_base) must return None (stored vector is far, not near).
    result = store.find_near_duplicate(_vec_base())
    assert result is None, (
        "After second put_embedding with far vector, find_near_duplicate must return None "
        f"(stored vector is no longer near base); got {result!r}"
    )


# ---------------------------------------------------------------------------
# Test — enrichment schema columns (postgres only, db_live)
# ---------------------------------------------------------------------------

@db_live
def test_enrichment_schema(tmp_path):
    """After init_schema(), infotriage.enrichment has all 7 scoring columns.

    Postgres only: verifies that 006-enrichment.sql migration adds ccir, cnr, score,
    bucket, why, pmesii, tessoc to the bare stub table from 005-stubs.sql (D-10, R1).
    """
    from store import PostgresStore
    dsn = _get_dsn()
    _truncate_all(dsn)
    with PostgresStore(dsn=dsn, blob_root=tmp_path / "blobs") as s:
        s.init_schema()
        rows = s._conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'infotriage' AND table_name = 'enrichment' "
            "ORDER BY column_name"
        ).fetchall()
        columns = {r["column_name"] for r in rows}
        for col in ("ccir", "cnr", "score", "bucket", "why", "pmesii", "tessoc"):
            assert col in columns, (
                f"Column '{col}' missing from infotriage.enrichment after init_schema(); "
                f"found columns: {sorted(columns)}"
            )
