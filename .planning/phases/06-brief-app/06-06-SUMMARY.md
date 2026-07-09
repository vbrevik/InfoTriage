# Plan 06-06 Summary: Store Transaction Hygiene

**Status:** complete  
**Date:** 2026-07-09

## Delivered

- `libs/store/src/store/_postgres.py` — all four read methods now end their read transaction with `rollback()` after fetching, preventing idle-in-connection leaks.
- `__enter__` adds `idle_in_transaction_session_timeout=300000` (5-minute) backstop on the connection parameter — self-heals any future leaked read txn (e.g. raw `cursor()` caller).
- `tests/test_store_txn_hygiene.py` — db_live regression test (5 tests) asserting IDLE after every read method, and verifying the backstop is set.

## Verification Results

- `tests/test_store_txn_hygiene.py` — **5/5 passed** (get_item, list_items, get_enrichment, find_near_duplicate all leave connection IDLE; backstop verified)
- `tests/test_store_integration.py` — **26 passed** (no write regression, DD-5 preserved)
- `tests/test_store_contract.py` — passed (db_live)
- `tests/test_triage_enrichment.py` — passed (db_live)
- `tests/test_dsn_safety.py` — **2 passed** (no prod DSN introduced)
- Full test suite: **242 passed, 4 failed** — 4 failures are pre-existing RabbitMQ contention issues (unrelated to this plan)

## Tasks Completed

### Task 1: Regression Test (RED → GREEN)
- Created `tests/test_store_txn_hygiene.py` following the INFOTRIAGE_TEST_DSN pattern from 06-05
- Parameterized test exercises all 4 read methods against empty DB, asserts `TransactionStatus.IDLE` after each
- Separate test verifies the `idle_in_transaction_session_timeout=300000` backstop on the connection
- All tests pass against ephemeral test DB; auto-skip when no test DB configured

### Task 2: Read Method Fixes + Backstop
- **get_item**: `self._conn.rollback()` after `fetchone()`, before both miss/hit return paths ✅
- **list_items**: `self._conn.rollback()` after `fetchall()` (both branches), before list comprehension return ✅
- **get_enrichment**: `self._conn.rollback()` after `fetchone()`, before both miss/hit return paths ✅
- **find_near_duplicate**: `self._conn.rollback()` after `fetchone()`, before both hit/None return paths ✅
- **Backstop**: `__enter__` passes `options="-c idle_in_transaction_session_timeout=300000"` to psycopg.connect ✅
- **No write methods changed**: put_item, put_enrichment, put_embedding, put_blob all retain their explicit commit() ✅
- **No autocommit**: Connection remains non-autocommit (preserves DD-5 write+audit atomicity) ✅

## Commits

| Commit | Description |
|--------|-------------|
| 4f16534 | test(06-06): add failing txn-hygiene regression — reads must leave connection IDLE |
| 53d2174 | fix(06-06): end read txn in PostgresStore read methods + idle-in-transaction backstop |

## Requirements

Plan references "spec §Reading-surface routing" (spec section, not REQUIREMENTS.md ID) — no `requirements mark-complete` applicable.

## Self-Check: PASSED

- `libs/store/src/store/_postgres.py` — rollback on all 4 read methods + backstop in __enter__
- `tests/test_store_txn_hygiene.py` — 5 tests, all passing
- Commits 4f16534, 53d2174 — FOUND in git log
