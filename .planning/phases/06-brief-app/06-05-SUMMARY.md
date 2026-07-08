---
phase: 06-brief-app
plan: 05
subsystem: testing
tags: [pytest, postgres, pgvector, dsn-safety, docker-compose, gap-closure]
requires:
  - "06-UAT.md root cause: db_live fixtures wiped production Postgres :22000"
provides:
  - "INFOTRIAGE_TEST_DSN as the only DSN source for db_live tests (no prod fallback)"
  - "tests/test_dsn_safety.py always-run regression guard against prod-port DSNs"
  - "docker-compose.test.yml throwaway tmpfs test Postgres on :22062"
affects:
  - "06-06 (store txn hygiene) — db_live tests now safely runnable during its verification"
tech-stack:
  added: ["pgvector/pgvector:pg16 test container (tmpfs)"]
  patterns:
    - "Test DSN resolved exclusively from INFOTRIAGE_TEST_DSN; reachability probe parses host/port from the DSN itself"
    - "Fixtures bootstrap init_schema() before TRUNCATE and before store __enter__ (fresh-DB safe)"
key-files:
  created:
    - tests/test_dsn_safety.py
    - docker-compose.test.yml
  modified:
    - tests/test_store_integration.py
    - tests/test_triage_enrichment.py
    - tests/test_store_contract.py
    - pyproject.toml
    - libs/store/sql/001-schema.sql
decisions:
  - "db_live tests resolve DSN exclusively from INFOTRIAGE_TEST_DSN — never INFOTRIAGE_PG_DSN, never a literal; unset ⇒ skip (R8 preserved)"
  - "CREATE EXTENSION vector must use WITH SCHEMA public — installing into the infotriage schema breaks register_vector() on default-search_path connections"
  - "db_live fixtures must run init_schema() before TRUNCATE and before entering the store context, so a fresh compose DB needs no manual setup"
metrics:
  duration: "~15 min"
  completed: "2026-07-08"
status: complete
---

# Phase 6 Plan 05: Test-DSN Safety Summary

Made it structurally impossible for pytest to touch production Postgres: db_live tests now resolve their DSN exclusively from INFOTRIAGE_TEST_DSN (no fallback), an always-run guard test rejects any prod-port (22000) DSN literal or socket probe under tests/, and a tmpfs-backed throwaway test Postgres on :22062 keeps db_live tests runnable.

## What Was Built

### Task 1 — DSN/reachability rework (commit 2d6c255)

All three db_live test files (`tests/test_store_integration.py`, `tests/test_triage_enrichment.py`, `tests/test_store_contract.py`):

- Deleted the hardcoded prod `DEV_DSN` constants and the inline `INFOTRIAGE_PG_DSN` fallback.
- `_get_dsn()` returns `os.environ.get("INFOTRIAGE_TEST_DSN")` with NO fallback (may be None; only called under db_live guards).
- `_pg_reachable()` → `_test_db_reachable()`: returns False when INFOTRIAGE_TEST_DSN is unset (auto-skip, R8); otherwise parses host/port from the DSN via `psycopg.conninfo.conninfo_to_dict` and probes with a 1s socket connect. No hardcoded port anywhere.
- Skipif reasons and docstrings scrubbed of ":22000" prose; dual-mark pattern (db_live + skipif) preserved so `-m db_live` selection and auto-skip both keep working.
- `_truncate_all` untouched functionally — it now only ever receives the isolated test DSN.

### Task 2 — Regression guard + test compose + marker (commit 6fecb46)

- `tests/test_dsn_safety.py` (always-run, NOT db_live): scans every `tests/**/*.py` except itself for (1) a `postgresql://…:22000` DSN literal or (2) a `create_connection(("…", 22000)` probe; fails listing offenders. Second test validates INFOTRIAGE_TEST_DSN's port is not 22000 when set. PROD_HOST_PORT=22000 lives only in this guard.
- `docker-compose.test.yml`: `pgvector/pgvector:pg16` as `infotriage-postgres-test` on host port 22062, tmpfs data dir (no shared volume with prod `./data/postgres`), usage comment with the exact export + pytest commands.
- `pyproject.toml`: db_live marker description updated to "requires INFOTRIAGE_TEST_DSN pointing at a reachable isolated test Postgres".

## Verification Results

- Skip path: `env -u INFOTRIAGE_TEST_DSN INFOTRIAGE_PG_DSN=postgresql://should-not-be-used:0/x python3 -m pytest <3 files + guard> -q` → 19 passed, 26 skipped, zero errors, no prod-port connection attempted.
- Guard: `pytest tests/test_dsn_safety.py -q` → 2 passed.
- Compose: valid YAML; marker registered with new description (`pytest --markers`).
- Live path (isolated DB only, per safety note): fresh `docker compose -f docker-compose.test.yml up -d` then `INFOTRIAGE_TEST_DSN=postgresql://test:test@localhost:22062/infotriage_test python3 -m pytest -m db_live -q` → **26 passed** against a pristine tmpfs DB. Container torn down afterwards.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] pgvector extension installed into wrong schema on fresh DBs**
- **Found during:** Task 2 live verification against the fresh compose DB
- **Issue:** `001-schema.sql` ran `SET search_path = infotriage, public` before `CREATE EXTENSION IF NOT EXISTS vector`, so on a freshly bootstrapped DB the extension landed in the `infotriage` schema. `PostgresStore.__enter__`'s `register_vector()` (default search_path) then failed with "vector type not found". Invisible on prod because its extension already lived in `public`.
- **Fix:** `CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;` (idempotent no-op on existing DBs)
- **Files modified:** libs/store/sql/001-schema.sql
- **Commit:** f92f8ed

**2. [Rule 3 - Blocking] db_live fixtures broke on a truly fresh DB (order dependence)**
- **Found during:** Task 2 live verification
- **Issue:** Fixtures ran `_truncate_all()` and `PostgresStore.__enter__` (pgvector adapter registration) before any `init_schema()` had ever run — errors on a pristine DB, contradicting the compose file's "no manual schema setup" contract.
- **Fix:** Each db_live fixture/test now calls `PostgresStore(...).init_schema()` (own connection, no `__enter__`) before TRUNCATE and before entering the store context; redundant inner `init_schema()` calls removed.
- **Files modified:** tests/test_store_integration.py, tests/test_store_contract.py, tests/test_triage_enrichment.py
- **Commit:** f92f8ed

## Deferred Issues (out of scope, logged to deferred-items.md)

- `tests/integration/test_clustering_integration.py` carries a hardcoded DSN at `127.0.0.1:5432` (container-internal port, NOT prod :22000 — guard correctly does not trip) with no skip guard; errors on hosts with an unrelated local Postgres. Pre-existing; candidate for INFOTRIAGE_TEST_DSN migration in a follow-up.
- 4 pre-existing RabbitMQ test failures (`test_bus_consume.py`, `test_bus_rabbitmq.py`) — unrelated to DSN work (known live-consumer contention issue).

## Requirements

Plan frontmatter references "spec §Reading-surface routing" (spec section, not a REQUIREMENTS.md ID) — no `requirements mark-complete` applicable.

## Commits

| Commit | Description |
|--------|-------------|
| 2d6c255 | fix(06-05): require INFOTRIAGE_TEST_DSN in db_live tests — remove prod DSN fallback |
| 6fecb46 | test(06-05): add prod-DSN regression guard + throwaway test Postgres compose |
| f92f8ed | fix(06-05): make db_live fixtures work on a fresh test DB |

## Self-Check: PASSED

- tests/test_dsn_safety.py — FOUND
- docker-compose.test.yml — FOUND
- Commits 2d6c255, 6fecb46, f92f8ed — FOUND in git log
