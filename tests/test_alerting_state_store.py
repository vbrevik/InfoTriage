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

import datetime
import os
import socket
import threading
from pathlib import Path

import pytest

from store import InMemoryStore


TEST_DSN_ENV = "INFOTRIAGE_TEST_DSN"

# Fixed injected clock — every test drives claim_alert/count_alerts_in_window/etc.
# through an explicit `now=` so TTL/window boundaries are deterministic (SPEC R2/R3),
# never dependent on wall-clock time.
BASE = datetime.datetime(2026, 1, 1, 0, 0, 0, tzinfo=datetime.timezone.utc)


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

_pg_live_skipif = (
    pytest.mark.db_live,
    pytest.mark.skipif(
        not _PG_UP,
        reason="INFOTRIAGE_TEST_DSN unset or test DB unreachable — db_live test skipped",
    ),
)


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


# -----------------------------------------------------------------------------
# Task 2: parity tests over both Store implementations
# -----------------------------------------------------------------------------


@pytest.fixture(
    params=[
        "inmemory",
        pytest.param("postgres", marks=_pg_live_skipif),
    ]
)
def store(request, tmp_path):
    """Yield a fresh Store implementation for each parametrized variant."""
    if request.param == "inmemory":
        yield InMemoryStore(blob_root=tmp_path / "blobs")
    else:
        import psycopg
        from store import PostgresStore

        dsn = os.environ.get(TEST_DSN_ENV)
        PostgresStore(dsn=dsn, blob_root=tmp_path / "blobs").init_schema()
        # Truncate alert_state for per-test isolation — this file owns its own
        # truncation (tests/conftest.py's shared pg_store fixture does not
        # include alert_state), matching test_store_entities.py's precedent of
        # each contract-test file truncating the tables it exercises.
        with psycopg.connect(dsn, autocommit=True) as conn:
            conn.execute("TRUNCATE infotriage.alert_state RESTART IDENTITY")
        with PostgresStore(dsn=dsn, blob_root=tmp_path / "blobs") as s:
            yield s


def _raw_row(store_impl, dedupe_id: str) -> "dict | None":
    """Read a raw alert_state row directly, bypassing the Store protocol's narrow
    method surface (list_undigested_suppressed only exposes 6 of 11 columns and
    only for suppressed+undigested rows) — needed to assert suppressed/digested_at/
    delivered_at/dlx_at after claim_alert's re-fire reset (Test 3).

    InMemoryStore: reads the private ``_alert_state`` dict directly (established
    test-only pattern in this suite — see tests/test_bus_consume.py's
    ``bus._queues`` reads). PostgresStore: reads via the store's own public
    ``cursor()`` API (Phase 6 ad-hoc SELECT surface), not a private attribute.
    """
    if isinstance(store_impl, InMemoryStore):
        row = store_impl._alert_state.get(dedupe_id)
        return dict(row) if row is not None else None
    cur = store_impl.cursor()
    cur.execute(
        "SELECT dedupe_id, item_id, cnr_tier, alert_id, fired_at, suppressed, "
        "pmesii, title, digested_at, delivered_at, dlx_at "
        "FROM infotriage.alert_state WHERE dedupe_id = %s",
        (dedupe_id,),
    )
    row = cur.fetchone()
    store_impl._conn.rollback()  # end read txn — avoid idle-in-transaction
    return dict(row) if row is not None else None


# --- Test 1: fresh claim -----------------------------------------------------


def test_claim_alert_fresh_dedupe_id_claims_and_writes_one_row(store):
    dedupe_id = "dedupe-fresh-001"
    assert store.claim_alert(dedupe_id, "item-1", "CAT-I", "alert-1", now=BASE) is True
    row = _raw_row(store, dedupe_id)
    assert row is not None
    assert row["item_id"] == "item-1"
    assert row["cnr_tier"] == "CAT-I"
    assert row["alert_id"] == "alert-1"
    assert row["suppressed"] is False


# --- Test 2: within-TTL suppress, fired_at untouched -------------------------


def test_claim_alert_within_ttl_suppressed_and_fired_at_unchanged(store):
    dedupe_id = "dedupe-ttl-001"
    assert store.claim_alert(dedupe_id, "item-1", "CAT-I", "alert-1", now=BASE) is True

    repeat_now = BASE + datetime.timedelta(hours=1)
    assert (
        store.claim_alert(dedupe_id, "item-1", "CAT-I", "alert-2", now=repeat_now)
        is False
    )

    row = _raw_row(store, dedupe_id)
    assert row["fired_at"] == BASE
    assert row["alert_id"] == "alert-1"  # not refreshed by the suppressed attempt


# --- Test 3: beyond-TTL re-fire, full state reset -----------------------------


def test_claim_alert_beyond_ttl_refires_and_resets_state(store):
    dedupe_id = "dedupe-refire-001"
    assert store.claim_alert(dedupe_id, "item-1", "CAT-I", "alert-1", now=BASE) is True
    store.mark_alert_suppressed(dedupe_id, pmesii="Military", title="Original headline")
    store.mark_alerts_digested([dedupe_id], now=BASE)
    store.mark_alert_outcome(dedupe_id, outcome="delivered", now=BASE)

    pre = _raw_row(store, dedupe_id)
    assert pre["suppressed"] is True
    assert pre["digested_at"] is not None
    assert pre["delivered_at"] is not None

    refire_now = BASE + datetime.timedelta(hours=24, seconds=1)
    assert (
        store.claim_alert(dedupe_id, "item-2", "CAT-II", "alert-2", now=refire_now)
        is True
    )

    post = _raw_row(store, dedupe_id)
    assert post["fired_at"] == refire_now
    assert post["alert_id"] == "alert-2"
    assert post["item_id"] == "item-2"
    assert post["cnr_tier"] == "CAT-II"
    assert post["suppressed"] is False
    assert post["digested_at"] is None
    assert post["delivered_at"] is None
    assert post["dlx_at"] is None


# --- Test 4: sliding-window count, suppressed excluded -----------------------


def test_count_alerts_in_window_counts_only_nonsuppressed_within_window(store):
    for i in range(5):
        assert (
            store.claim_alert(
                f"dedupe-win-{i}",
                f"item-{i}",
                "CAT-I",
                f"alert-{i}",
                now=BASE + datetime.timedelta(seconds=i),
            )
            is True
        )

    check_now = BASE + datetime.timedelta(seconds=10)
    assert store.count_alerts_in_window(window_seconds=60, now=check_now) == 5

    store.mark_alert_suppressed("dedupe-win-0")
    assert store.count_alerts_in_window(window_seconds=60, now=check_now) == 4


def test_count_alerts_in_window_excludes_rows_outside_window(store):
    store.claim_alert("dedupe-outside-001", "item-1", "CAT-I", "alert-1", now=BASE)
    far_now = BASE + datetime.timedelta(seconds=120)
    assert store.count_alerts_in_window(window_seconds=60, now=far_now) == 0


# --- Test 5: mark_alert_suppressed --------------------------------------------


def test_mark_alert_suppressed_flips_flag_and_records_pmesii_title(store):
    dedupe_id = "dedupe-supp-001"
    store.claim_alert(dedupe_id, "item-1", "CAT-I", "alert-1", now=BASE)
    store.mark_alert_suppressed(dedupe_id, pmesii="Military", title="Some headline")

    row = _raw_row(store, dedupe_id)
    assert row["suppressed"] is True
    assert row["pmesii"] == "Military"
    assert row["title"] == "Some headline"
    # a suppressed row stops counting toward the window
    assert store.count_alerts_in_window(window_seconds=60, now=BASE) == 0


# --- Test 6: list_undigested_suppressed / mark_alerts_digested ---------------


def test_list_undigested_suppressed_returns_until_digested(store):
    dedupe_id = "dedupe-digest-001"
    store.claim_alert(dedupe_id, "item-1", "CAT-I", "alert-1", now=BASE)
    store.mark_alert_suppressed(dedupe_id, pmesii="Military", title="Headline")

    pending = store.list_undigested_suppressed(now=BASE)
    assert any(r["dedupe_id"] == dedupe_id for r in pending)

    # not consumed by reading — returned again on a second call
    pending_again = store.list_undigested_suppressed(now=BASE)
    assert any(r["dedupe_id"] == dedupe_id for r in pending_again)

    store.mark_alerts_digested([dedupe_id], now=BASE)
    after = store.list_undigested_suppressed(now=BASE)
    assert all(r["dedupe_id"] != dedupe_id for r in after)


def test_mark_alerts_digested_empty_sequence_is_noop(store):
    # Must not raise for an empty sequence.
    store.mark_alerts_digested([], now=BASE)


# --- Test 7: mark_alert_outcome -----------------------------------------------


def test_mark_alert_outcome_sets_delivered_or_dlx_independently(store):
    delivered_id, dlx_id = "dedupe-out-delivered", "dedupe-out-dlx"
    store.claim_alert(delivered_id, "item-1", "CAT-I", "alert-1", now=BASE)
    store.claim_alert(dlx_id, "item-2", "CAT-I", "alert-2", now=BASE)

    store.mark_alert_outcome(delivered_id, outcome="delivered", now=BASE)
    store.mark_alert_outcome(dlx_id, outcome="dead_lettered", now=BASE)

    delivered_row = _raw_row(store, delivered_id)
    dlx_row = _raw_row(store, dlx_id)
    assert delivered_row["delivered_at"] is not None
    assert delivered_row["dlx_at"] is None
    assert dlx_row["dlx_at"] is not None
    assert dlx_row["delivered_at"] is None


def test_mark_alert_outcome_raises_on_bogus_outcome(store):
    dedupe_id = "dedupe-out-bogus"
    store.claim_alert(dedupe_id, "item-1", "CAT-I", "alert-1", now=BASE)
    with pytest.raises(ValueError):
        store.mark_alert_outcome(dedupe_id, outcome="bogus")


# --- Test 8 (implicit): the `store` fixture parametrization over InMemoryStore
# and PostgresStore already runs every test above against both implementations,
# proving identical behavior (D-02 parity requirement).


# --- Concurrency: two real PostgresStore connections race the same dedupe_id ---


@pytest.mark.db_live
@pytest.mark.skipif(
    not _PG_UP,
    reason="INFOTRIAGE_TEST_DSN unset or test DB unreachable — db_live test skipped",
)
def test_claim_alert_concurrent_claims_yield_exactly_one_winner(tmp_path):
    """Two separate PostgresStore connections race claim_alert on the same
    dedupe_id. The single INSERT-ON-CONFLICT-WHERE-RETURNING statement is the
    entire race window (T-12-07) — exactly one call must return True."""
    import psycopg
    from store import PostgresStore

    dsn = os.environ[TEST_DSN_ENV]
    PostgresStore(dsn=dsn, blob_root=tmp_path / "blobs").init_schema()
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute("TRUNCATE infotriage.alert_state RESTART IDENTITY")

    dedupe_id = "dedupe-race-001"
    results: list[bool] = []
    results_lock = threading.Lock()
    barrier = threading.Barrier(2)

    def _claim(alert_id: str) -> None:
        with PostgresStore(dsn=dsn, blob_root=tmp_path / "blobs") as s:
            barrier.wait()  # maximize overlap between the two connections
            claimed = s.claim_alert(dedupe_id, "item-1", "CAT-I", alert_id, now=BASE)
            with results_lock:
                results.append(claimed)

    t1 = threading.Thread(target=_claim, args=("alert-race-1",))
    t2 = threading.Thread(target=_claim, args=("alert-race-2",))
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    assert sorted(results) == [False, True]
