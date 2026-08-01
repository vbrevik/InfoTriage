#!/usr/bin/env python3
"""tests/test_alerting_state_store.py — contract tests for alert_state store methods.

Phase 12 plan 12-02 (D-02): dedupe/throttle state substrate for the alerting
service. Tests run against both InMemoryStore and PostgresStore. The postgres
param is auto-skipped when INFOTRIAGE_TEST_DSN is unset or the test DB is
unreachable — mirrors tests/test_store_entities.py's parametrized-fixture
pattern.

``-k migration`` selects the two migration-only tests below (static SQL check
+ db_live table-creation/idempotency check) so plan 12-02 Task 1 can verify
the migration in isolation before the Store methods exist (Task 2 appends the
six-method parity + concurrency tests to this same file).
"""
from __future__ import annotations

import os
import socket
from pathlib import Path

import pytest


TEST_DSN_ENV = "INFOTRIAGE_TEST_DSN"


def _test_db_reachable() -> bool:
    """Return True if the INFOTRIAGE_TEST_DSN test DB accepts a TCP connection within 1s."""
    import psycopg

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


_PG_UP = _test_db_reachable()


# -----------------------------------------------------------------------------
# Task 1: migration-only tests (`-k migration`) — no Store methods required.
# -----------------------------------------------------------------------------


def test_alert_state_migration_sql_declares_table_and_load_bearing_index():
    """Static check: 011-alert-state.sql declares the table and the unique index
    that makes claim_alert's ON CONFLICT legal (T-12-07)."""
    sql_path = (
        Path(__file__).resolve().parent.parent
        / "libs"
        / "store"
        / "sql"
        / "011-alert-state.sql"
    )
    src = sql_path.read_text()
    assert "CREATE TABLE IF NOT EXISTS infotriage.alert_state" in src
    assert "CREATE UNIQUE INDEX IF NOT EXISTS alert_state_dedupe_id_unique" in src


@pytest.mark.db_live
@pytest.mark.skipif(
    not _PG_UP,
    reason="INFOTRIAGE_TEST_DSN unset or test DB unreachable — db_live test skipped",
)
def test_alert_state_migration_creates_table_and_reapply_is_idempotent(tmp_path):
    """Behavior (db_live): init_schema() creates infotriage.alert_state, and
    re-applying the migration file a second time raises no error."""
    import psycopg
    from store import PostgresStore

    dsn = os.environ[TEST_DSN_ENV]
    PostgresStore(dsn=dsn, blob_root=tmp_path / "blobs").init_schema()
    with psycopg.connect(dsn) as conn:
        row = conn.execute("SELECT to_regclass('infotriage.alert_state')").fetchone()
        assert row[0] is not None
        conn.rollback()
    # Re-applying the migration (via a fresh init_schema() call) must be a no-op.
    PostgresStore(dsn=dsn, blob_root=tmp_path / "blobs").init_schema()
