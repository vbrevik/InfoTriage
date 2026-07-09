#!/usr/bin/env python3
"""tests/test_store_txn_hygiene.py — regression: read methods must not leave a txn open.

Phase-6 UAT gap (06-UAT.md): PostgresStore's read methods run a SELECT on the
non-autocommit connection and never commit/rollback, so the implicit read
transaction stays open until the next write. An observed 8.5-hour
idle-in-transaction connection let a queued fixture TRUNCATE (AccessExclusive)
pile locks behind it and blocked all reads — /sab could not read the tables.

Rationale: after a SELECT on a non-autocommit psycopg connection,
info.transaction_status is INTRANS until commit/rollback; a correctly-behaved
read ends its read txn and leaves the connection IDLE.

All tests are marked @db_live and auto-skipped when INFOTRIAGE_TEST_DSN is
unset or the test DB is unreachable (R8). The DSN is resolved EXCLUSIVELY from
INFOTRIAGE_TEST_DSN — no fallback, no hardcoded DSN (06-05 safety pattern) —
so a pytest run can never touch the production database.
"""
import os
import socket

import numpy as np
import psycopg
import pytest

from store import PostgresStore


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TEST_DSN_ENV = "INFOTRIAGE_TEST_DSN"  # the ONLY DSN source for db_live tests
DIM = 1024  # locked embedding dimension (D-05a)


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
    """Decorator: apply @pytest.mark.db_live AND @pytest.mark.skipif when the test DB is unavailable."""
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


def _truncate_all(dsn: str) -> None:
    """TRUNCATE all infotriage tables for per-test isolation."""
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(
            "TRUNCATE infotriage.entity_links, infotriage.embeddings, "
            "infotriage.enrichment, infotriage.ccir, infotriage.audit, "
            "infotriage.articles, infotriage.entities RESTART IDENTITY"
        )


def _unit_vector(dim: int = DIM) -> np.ndarray:
    """Deterministic 1024-dim unit vector — no embedding model invoked."""
    vec = np.zeros(dim, dtype=np.float32)
    vec[0] = 1.0
    return vec


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def pg_store(tmp_path):
    """Open a PostgresStore against the INFOTRIAGE_TEST_DSN test DB, truncated for isolation."""
    dsn = _get_dsn()
    # Bootstrap first: on a fresh test DB (docker-compose.test.yml) the infotriage
    # schema/extension don't exist yet — init_schema() must run before TRUNCATE and
    # before __enter__ (which registers the pgvector type adapter). (06-05 pattern.)
    PostgresStore(dsn=dsn, blob_root=tmp_path / "blobs").init_schema()
    _truncate_all(dsn)
    with PostgresStore(dsn=dsn, blob_root=tmp_path / "blobs") as s:
        yield s


# ---------------------------------------------------------------------------
# Regression: every read method must leave the connection IDLE (no INTRANS)
# ---------------------------------------------------------------------------

# (method name, call against empty/miss state, expected-result predicate)
_READ_CALLS = [
    ("get_item", lambda s: s.get_item("no-such-id"), lambda r: r is None),
    ("list_items", lambda s: s.list_items(), lambda r: r == []),
    ("get_enrichment", lambda s: s.get_enrichment("no-such-id"), lambda r: r is None),
    (
        "find_near_duplicate",
        lambda s: s.find_near_duplicate(_unit_vector()),
        lambda r: r is None,
    ),
]


@db_live
@pytest.mark.parametrize(
    "method_name,call,expect_miss",
    _READ_CALLS,
    ids=[name for name, _, _ in _READ_CALLS],
)
def test_read_method_leaves_connection_idle(pg_store, method_name, call, expect_miss):
    """After any PostgresStore read method returns, the connection must be IDLE.

    After a SELECT on a non-autocommit connection, transaction_status is
    INTRANS until commit/rollback; a correctly-behaved read ends its read txn
    (rollback) and leaves the connection IDLE. A connection left INTRANS while
    idle blocks DDL/TRUNCATE and queues all subsequent reads behind it
    (T-06G-04, 06-UAT.md root cause).

    # end read txn — avoid idle-in-transaction
    """
    result = call(pg_store)
    assert expect_miss(result), (
        f"{method_name} against an empty DB must return the miss value; got {result!r}"
    )
    status = pg_store._conn.info.transaction_status
    assert status == psycopg.pq.TransactionStatus.IDLE, (
        f"{method_name} left the connection in transaction_status "
        f"{status.name} — expected IDLE. The read method did not end its "
        f"read transaction (idle-in-transaction leak)."
    )

@db_live
def test_idle_in_transaction_backstop_is_set(tmp_path):
    """Verify the connection was created with idle_in_transaction_session_timeout set.

    This is the backstop that self-heals any future leaked read txn (the 300s cap
    prevents the 8.5-hour wedge that blocked DDL and queued all reads).
    """
    dsn = _get_dsn()
    store = PostgresStore(dsn=dsn, blob_root=tmp_path / "blobs")

    with store:
        # The connection options string should contain the timeout setting
        # psycopg3 stores this in conn.info.parameters
        params = dict(store._conn.info.get_parameters())
        options = params.get("options", "")
        assert "idle_in_transaction_session_timeout=300000" in options, (
            f"idle_in_transaction_session_timeout not set; "
            f"options={options!r}"
        )

