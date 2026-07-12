"""tests/conftest.py — shared pytest fixtures and markers for InfoTriage tests."""

from __future__ import annotations

import os
import socket

import psycopg
import pytest


TEST_DSN_ENV = "INFOTRIAGE_TEST_DSN"


def _test_db_reachable() -> bool:
    """Return True if the INFOTRIAGE_TEST_DSN test DB accepts a TCP connection within 1s."""
    dsn = os.environ.get(TEST_DSN_ENV)
    if not dsn:
        return False
    try:
        info = psycopg.conninfo.conninfo_to_dict(dsn)
    except psycopg.Error:
        return False
    host = str(info.get("host") or "localhost")
    port = int(info.get("port") or 5432)
    try:
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except OSError:
        return False


def db_live(fn):
    """Decorator: mark a test as needing the live test Postgres and skip if it is unreachable.

    Reachability is evaluated lazily (at test collection/run time) so a test DB
    that starts after pytest begins still gets used.
    """
    fn = pytest.mark.db_live(fn)
    fn = pytest.mark.skipif(
        not _test_db_reachable(),
        reason="INFOTRIAGE_TEST_DSN unset or test DB unreachable — db_live test skipped",
    )(fn)
    return fn


@pytest.fixture
def pg_store(tmp_path):
    """Open a PostgresStore against the INFOTRIAGE_TEST_DSN test DB, truncated for isolation."""
    dsn = os.environ.get(TEST_DSN_ENV)
    if not dsn:
        pytest.skip("INFOTRIAGE_TEST_DSN not set")
    # Bootstrap first: on a fresh test DB the infotriage schema/extension may not
    # exist yet — init_schema() must run before TRUNCATE and before __enter__.
    from store import PostgresStore

    PostgresStore(dsn=dsn, blob_root=tmp_path / "blobs").init_schema()
    # Truncate all infotriage tables for per-test isolation
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(
            "TRUNCATE infotriage.entity_links, infotriage.embeddings, "
            "infotriage.enrichment, infotriage.ccir, infotriage.audit, "
            "infotriage.articles, infotriage.entities RESTART IDENTITY"
        )
    with PostgresStore(dsn=dsn, blob_root=tmp_path / "blobs") as store:
        yield store
