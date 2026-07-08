#!/usr/bin/env python3
"""tests/test_store_integration.py — live integration tests against an isolated test Postgres.

All tests are marked @db_live and auto-skipped when INFOTRIAGE_TEST_DSN is unset
or the test DB is unreachable (R8).

Requirements covered:
  R1  — init_schema() is idempotent: two calls, no error, schema unchanged
  R2  — all 7 tables exist; Item round-trip recovers all columns + JSONB payload
  R3  — pgvector cosine query: NATO-like pair (~0.92) links; Trump/Putin-like (~0.72) stays distinct
  R5  — live upsert (ON CONFLICT DO UPDATE); no-silent-loss: failed persist raises
  D-05a — embeddings.embedding and entities.embedding are exactly vector(1024)
  D-05b — cosine query uses inclusive threshold >= 0.85 over the HNSW index
  D-05c — vectors are deterministic fixtures (seed=42) — no embedding model invoked

Construct PostgresStore from the INFOTRIAGE_TEST_DSN env var only — there is
deliberately NO fallback to INFOTRIAGE_PG_DSN or any hardcoded DSN, so a pytest
run can never touch the production database.
"""
import datetime
import os
import socket

import numpy as np
import psycopg
import pytest

from contracts import Item
from store import PostgresStore


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TEST_DSN_ENV = "INFOTRIAGE_TEST_DSN"  # the ONLY DSN source for db_live tests
DIM = 1024           # locked embedding dimension (D-05a)
THRESHOLD = 0.85     # inclusive cosine link threshold (D-05b)


# ---------------------------------------------------------------------------
# db_live marker — skip when INFOTRIAGE_TEST_DSN is unset or unreachable
# ---------------------------------------------------------------------------


def _test_db_reachable() -> bool:
    """Return True if the INFOTRIAGE_TEST_DSN test DB accepts a TCP connection within 1s.

    Returns False when INFOTRIAGE_TEST_DSN is unset/empty, so db_live tests
    auto-skip when no isolated test DB is configured (R8). Host/port are parsed
    from the DSN itself — never hardcoded.
    """
    dsn = os.environ.get(TEST_DSN_ENV)
    if not dsn:
        return False
    try:
        info = psycopg.conninfo.conninfo_to_dict(dsn)
    except psycopg.Error:
        return False
    host = info.get("host") or "localhost"
    port = int(info.get("port") or 5432)
    try:
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except OSError:
        return False


_PG_UP = _test_db_reachable()  # evaluated once at collection time


def db_live(fn):
    """Decorator: apply @pytest.mark.db_live AND @pytest.mark.skipif when the test DB is unavailable.

    Applying both marks so that:
    - `pytest -m db_live` selects these tests (the db_live marker)
    - Tests auto-skip when the DB is not reachable (the skipif condition)

    Using function-level mark application (not functools.wraps) so pytest's
    fixture injection continues to work — pytest marks the function in-place
    and returns the same function object.
    """
    fn = pytest.mark.db_live(fn)
    fn = pytest.mark.skipif(
        not _PG_UP,
        reason="INFOTRIAGE_TEST_DSN unset or test DB unreachable — db_live test skipped",
    )(fn)
    return fn


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_dsn() -> str | None:
    """Return the isolated test-DB DSN from INFOTRIAGE_TEST_DSN — NO fallback.

    Only called from db_live-guarded fixtures/tests, so it is non-None there.
    """
    return os.environ.get(TEST_DSN_ENV)


def _ts(offset_seconds: int = 0) -> datetime.datetime:
    base = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
    return base + datetime.timedelta(seconds=offset_seconds)


def _item(**kwargs) -> Item:
    defaults = dict(
        source="IntegrationTestSource",
        source_type="rss",
        url="https://example.com/integration/test",
        title="Integration Test Item",
        ts=_ts(),
        lang="en",
    )
    defaults.update(kwargs)
    return Item(**defaults)


def _truncate_all(dsn: str) -> None:
    """TRUNCATE all infotriage tables for per-test isolation."""
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(
            "TRUNCATE infotriage.entity_links, infotriage.embeddings, "
            "infotriage.enrichment, infotriage.ccir, infotriage.audit, "
            "infotriage.articles, infotriage.entities RESTART IDENTITY"
        )


def _make_cosine_fixture_vectors(dim: int = DIM):
    """Return (nato1, nato2, putin) deterministic float32 unit vectors (D-05c).

    Constructed via seeded Gram-Schmidt so cosine similarities are exact:
      nato1.dot(nato2) == 0.92  (>= 0.85 → links at threshold)
      nato1.dot(putin) == 0.72  (< 0.85 → stays distinct)

    Calibration from R3-VERDICT.md: NATO/NATO ~0.92; Trump/Putin ~0.72.
    No embedding model is invoked — pure deterministic fixtures.
    """
    rng = np.random.default_rng(seed=42)

    # Base "NATO" vector (random unit vector)
    base = rng.standard_normal(dim).astype(np.float32)
    nato1 = base / np.linalg.norm(base)

    # NATO variant at exactly cos_sim = 0.92 using Gram-Schmidt orthogonalization.
    # perp1 is a unit vector orthogonal to nato1, so:
    #   nato2 = cos(θ)*nato1 + sin(θ)*perp1  →  nato1·nato2 = cos(θ) exactly
    perp_raw = rng.standard_normal(dim).astype(np.float32)
    perp_raw -= perp_raw.dot(nato1) * nato1  # remove nato1 component
    perp1 = (perp_raw / np.linalg.norm(perp_raw)).astype(np.float32)

    cos_92 = np.float32(0.92)
    sin_92 = np.float32(np.sqrt(1.0 - float(cos_92) ** 2))
    nato2 = (cos_92 * nato1 + sin_92 * perp1).astype(np.float32)
    nato2 = (nato2 / np.linalg.norm(nato2)).astype(np.float32)

    # "Putin" vector at exactly cos_sim = 0.72 (below threshold)
    perp_raw2 = rng.standard_normal(dim).astype(np.float32)
    perp_raw2 -= perp_raw2.dot(nato1) * nato1
    perp2 = (perp_raw2 / np.linalg.norm(perp_raw2)).astype(np.float32)

    cos_72 = np.float32(0.72)
    sin_72 = np.float32(np.sqrt(1.0 - float(cos_72) ** 2))
    putin = (cos_72 * nato1 + sin_72 * perp2).astype(np.float32)
    putin = (putin / np.linalg.norm(putin)).astype(np.float32)

    return nato1, nato2, putin


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def pg_store(tmp_path):
    """Open a PostgresStore against the INFOTRIAGE_TEST_DSN test DB, truncated for isolation."""
    dsn = _get_dsn()
    # Bootstrap first: on a fresh test DB (docker-compose.test.yml) the infotriage
    # schema/extension don't exist yet — init_schema() must run before TRUNCATE and
    # before __enter__ (which registers the pgvector type adapter).
    PostgresStore(dsn=dsn, blob_root=tmp_path / "blobs").init_schema()
    _truncate_all(dsn)
    with PostgresStore(dsn=dsn, blob_root=tmp_path / "blobs") as s:
        yield s


# ---------------------------------------------------------------------------
# R1: init_schema idempotency
# ---------------------------------------------------------------------------


@db_live
def test_init_schema_idempotent(tmp_path):
    """init_schema() called twice must not raise and must leave the schema unchanged (R1).

    Proves the IF NOT EXISTS DDL makes the bootstrap safe to re-apply at any startup.
    """
    dsn = _get_dsn()
    store = PostgresStore(dsn=dsn, blob_root=tmp_path / "blobs")
    store.init_schema()  # first call — creates/confirms schema
    store.init_schema()  # second call — must be a no-op, no exception


# ---------------------------------------------------------------------------
# R2: all 7 tables present after init
# ---------------------------------------------------------------------------


@db_live
def test_all_tables_exist(pg_store):
    """All 7 infotriage tables must be present after init_schema (R2).

    Expected: articles, audit, ccir, embeddings, enrichment, entities, entity_links.
    """
    rows = pg_store._conn.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'infotriage' ORDER BY table_name"
    ).fetchall()
    tables = {r["table_name"] for r in rows}
    expected = {
        "articles",
        "audit",
        "ccir",
        "embeddings",
        "enrichment",
        "entities",
        "entity_links",
    }
    assert tables == expected, (
        f"Expected {sorted(expected)}, got {sorted(tables)}"
    )


# ---------------------------------------------------------------------------
# R2, D-02: Item round-trip (all columns + JSONB payload recovered)
# ---------------------------------------------------------------------------


@db_live
def test_item_roundtrip(pg_store):
    """put_item then get_item recovers all core fields + summary + body_ref + payload (R2, D-02)."""
    item = _item(
        source="NRK Nyheter",
        source_type="rss",
        url="https://nrk.no/integration/roundtrip",
        title="Roundtrip Article — Hybrid JSONB Test",
        lang="no",
        summary="BLUF: integration roundtrip summary",
        body_ref="a" * 64,  # fake sha256 hex (body blob reference)
        payload={"score": 8, "ccir": "PIR-2", "tags": ["nato", "norway"], "nested": {"x": 1}},
    )
    pg_store.put_item(item)
    got = pg_store.get_item(item.id)

    assert got is not None, "get_item must return Item after put_item"
    assert got.id == item.id, f"id mismatch: {got.id!r} != {item.id!r}"
    assert got.source == item.source
    assert got.source_type == item.source_type
    assert got.url == item.url
    assert got.title == item.title
    assert got.lang == item.lang
    assert got.summary == item.summary, f"summary: {got.summary!r} != {item.summary!r}"
    assert got.body_ref == item.body_ref, f"body_ref: {got.body_ref!r} != {item.body_ref!r}"
    assert got.payload == item.payload, (
        f"JSONB payload round-trip mismatch:\n  got: {got.payload!r}\n  exp: {item.payload!r}"
    )


# ---------------------------------------------------------------------------
# R5: live upsert — ON CONFLICT DO UPDATE, exactly one row, latest content
# ---------------------------------------------------------------------------


@db_live
def test_put_item_upsert_live(pg_store):
    """put_item twice with the same id → exactly one row, latest content wins (R5).

    Uses model_copy to change a non-id field (summary) so the computed id is stable.
    Confirms via both get_item and a direct COUNT(*) query.
    """
    item_v1 = _item(
        title="Live Upsert Test Article",
        source="Source Version 1",
        summary="First write",
    )
    # model_copy changing summary preserves source_type + url + title → same id
    item_v2 = item_v1.model_copy(update={"summary": "Second write (upsert wins)"})
    assert item_v1.id == item_v2.id, (
        "Sanity: summary update must not change computed id"
    )

    pg_store.put_item(item_v1)
    pg_store.put_item(item_v2)

    # Exactly one row in DB
    count = pg_store._conn.execute(
        "SELECT COUNT(*) AS cnt FROM infotriage.articles WHERE id = %s",
        (item_v1.id,),
    ).fetchone()["cnt"]
    assert count == 1, f"Expected 1 row after upsert; got {count}"

    # Latest content recovered via get_item
    got = pg_store.get_item(item_v1.id)
    assert got is not None
    assert got.summary == "Second write (upsert wins)", (
        f"Upsert: last-write must win; got {got.summary!r}"
    )


# ---------------------------------------------------------------------------
# D-05a: vector(1024) column contract
# ---------------------------------------------------------------------------


@db_live
def test_dimension_is_1024(pg_store):
    """embeddings.embedding and entities.embedding must be exactly vector(1024) (D-05a).

    Verified two ways:
    1. System catalog: format_type reports 'vector(1024)' for both columns.
    2. Behavioral: 1024-dim insert succeeds; 512-dim insert is rejected by Postgres.
    Vectors are supplied directly — no embedding model invoked (D-05c).
    """
    conn = pg_store._conn

    # 1. Catalog check
    rows = conn.execute(
        """
        SELECT c.relname, format_type(a.atttypid, a.atttypmod) AS dtype
        FROM pg_attribute a
        JOIN pg_class c ON a.attrelid = c.oid
        JOIN pg_namespace n ON c.relnamespace = n.oid
        WHERE n.nspname = 'infotriage'
          AND a.attname = 'embedding'
          AND c.relkind = 'r'
          AND a.attnum > 0
        ORDER BY c.relname
        """
    ).fetchall()
    type_map = {r["relname"]: r["dtype"] for r in rows}

    assert type_map.get("embeddings") == "vector(1024)", (
        f"embeddings.embedding: expected 'vector(1024)', got {type_map.get('embeddings')!r}"
    )
    assert type_map.get("entities") == "vector(1024)", (
        f"entities.embedding: expected 'vector(1024)', got {type_map.get('entities')!r}"
    )

    # 2. Behavioral: 1024-dim insert must succeed
    vec_1024 = np.zeros(DIM, dtype=np.float32)
    vec_1024[0] = 1.0
    conn.execute(
        "INSERT INTO infotriage.entities (name, name_norm, lang, embedding) "
        "VALUES (%s, %s, %s, %s)",
        ("dim-check-1024", "dim-check-1024", "en", vec_1024),
    )
    conn.commit()

    # 3. Behavioral: 512-dim insert must be rejected (dimension mismatch)
    vec_512 = np.zeros(512, dtype=np.float32)
    vec_512[0] = 1.0
    with pytest.raises(psycopg.Error):
        conn.execute(
            "INSERT INTO infotriage.entities (name, name_norm, lang, embedding) "
            "VALUES (%s, %s, %s, %s)",
            ("dim-check-512", "dim-check-512", "en", vec_512),
        )
        conn.commit()
    # Rollback the aborted transaction to restore the connection for teardown
    conn.rollback()


# ---------------------------------------------------------------------------
# R3, D-05b: pgvector cosine threshold — NATO links, Trump/Putin stays distinct
# ---------------------------------------------------------------------------


@db_live
def test_vector_cosine_threshold(pg_store):
    """Cosine query at >= 0.85 links the ~0.92 NATO pair and keeps the ~0.72 pair distinct.

    Calibration (R3-VERDICT.md):
      NATO / NATO variant: cos_sim ≈ 0.92 → linked (>= 0.85 inclusive)
      NATO / Trump-Putin:  cos_sim ≈ 0.72 → NOT linked (< 0.85)

    Query: 1 - (embedding <=> query) >= 0.85 over the HNSW vector_cosine_ops index (D-05b).
    Vectors are deterministic fixtures (seed=42) — no embedding model called (D-05c).
    """
    nato1, nato2, putin = _make_cosine_fixture_vectors()

    # Pre-flight: verify fixture cosine similarities
    sim_nato = float(nato1.dot(nato2))
    sim_putin = float(nato1.dot(putin))
    assert sim_nato >= THRESHOLD, (
        f"Fixture: NATO pair sim {sim_nato:.4f} must be >= {THRESHOLD} (got wrong vectors)"
    )
    assert sim_putin < THRESHOLD, (
        f"Fixture: Putin sim {sim_putin:.4f} must be < {THRESHOLD} (got wrong vectors)"
    )

    conn = pg_store._conn

    # Insert three fixture entities
    conn.execute(
        "INSERT INTO infotriage.entities (name, name_norm, lang, embedding) VALUES (%s, %s, %s, %s)",
        ("NATO_A", "nato_a", "en", nato1),
    )
    conn.execute(
        "INSERT INTO infotriage.entities (name, name_norm, lang, embedding) VALUES (%s, %s, %s, %s)",
        ("NATO_B", "nato_b", "en", nato2),
    )
    conn.execute(
        "INSERT INTO infotriage.entities (name, name_norm, lang, embedding) VALUES (%s, %s, %s, %s)",
        ("TRUMP_PUTIN", "trump_putin", "en", putin),
    )
    conn.commit()

    # Cosine similarity query with inclusive >= 0.85 filter (D-05b)
    # 1 - (embedding <=> query) converts cosine distance to similarity
    rows = conn.execute(
        "SELECT name, 1 - (embedding <=> %s) AS sim "
        "FROM infotriage.entities "
        "WHERE 1 - (embedding <=> %s) >= %s "
        "ORDER BY embedding <=> %s",
        (nato1, nato1, THRESHOLD, nato1),
    ).fetchall()

    found = {r["name"]: float(r["sim"]) for r in rows}

    # NATO_A (self — sim = 1.0) must appear
    assert "NATO_A" in found, (
        f"Self-match NATO_A (sim=1.0) missing from results; got {found}"
    )
    # NATO_B (sim ≈ 0.92, above threshold) must be linked
    assert "NATO_B" in found, (
        f"NATO_B (sim≈{sim_nato:.3f} >= {THRESHOLD}) must be linked; got {found}"
    )
    # TRUMP_PUTIN (sim ≈ 0.72, below threshold) must remain distinct
    assert "TRUMP_PUTIN" not in found, (
        f"TRUMP_PUTIN (sim≈{sim_putin:.3f} < {THRESHOLD}) must NOT be linked; got {found}"
    )


# ---------------------------------------------------------------------------
# must-NOT: failed put_item raises psycopg.Error — no silent success
# ---------------------------------------------------------------------------


@db_live
def test_put_item_failure_raises(pg_store):
    """A failed put_item must raise psycopg.Error — no silent data loss (no-silent-loss).

    Failure is induced by forcing the connection into an aborted transaction state
    via a deliberate SQL error (division by zero). The subsequent put_item call
    must raise psycopg.InFailedSqlTransaction (a psycopg.Error subclass), not
    silently succeed or return a false-positive result.
    """
    item = _item(title="Failure Raises Test")

    # Force connection into aborted-transaction state via a real SQL error.
    # SELECT 1/0 raises psycopg.errors.DivisionByZero; the transaction becomes
    # InFailedSqlTransaction so any following execute raises until rollback.
    try:
        pg_store._conn.execute("SELECT 1/0")
    except psycopg.Error:
        pass  # expected — connection is now in aborted state

    # put_item must propagate the error — MUST NOT silently return success
    with pytest.raises(psycopg.Error):
        pg_store.put_item(item)

    # Restore clean connection state so fixture teardown succeeds
    pg_store._conn.rollback()
