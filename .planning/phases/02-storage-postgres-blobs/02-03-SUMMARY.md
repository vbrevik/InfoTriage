---
phase: 02-storage-postgres-blobs
plan: "03"
subsystem: storage
tags: [postgres, psycopg3, pgvector, integration-test, store-protocol]
dependency_graph:
  requires: ["02-02"]
  provides: [PostgresStore, live-schema-on-22000, db_live-integration-tests]
  affects: [apps/triage/digest.py, tests/test_store_contract.py]
tech_stack:
  added: [psycopg3==3.3.4, pgvector-python==0.4.2]
  patterns: [psycopg3-context-manager, register_vector-after-DDL, Jsonb-wrapper, HNSW-cosine-query, Gram-Schmidt-fixture-vectors]
key_files:
  created:
    - libs/store/src/store/_postgres.py
    - tests/test_store_integration.py
  modified:
    - libs/store/src/store/__init__.py
    - tests/test_store_contract.py
decisions:
  - "register_vector in init_schema must run AFTER DDL files are applied (not before), or it fails on a fresh DB where the vector extension does not yet exist"
  - "pg_store fixture truncates all infotriage tables before each test for per-test isolation (RESTART IDENTITY)"
  - "db_live decorator applies both pytest.mark.db_live and pytest.mark.skipif so -m db_live selects integration tests AND they auto-skip when :22000 is unreachable"
  - "No-silent-loss test uses SELECT 1/0 to put connection in aborted state (no patching needed)"
metrics:
  duration: "12m"
  completed: "2026-06-28"
  tasks_completed: 3
  tasks_total: 3
  files_created: 2
  files_modified: 2
status: complete
---

# Phase 02 Plan 03: PostgresStore + Live Schema + Integration Tests Summary

PostgresStore implemented with psycopg3 and pgvector, infotriage schema applied to a live Postgres on :22000, and all R1/R2/R3/R5/D-05 requirements verified against the running database.

## Tasks Completed

| # | Task | Commit | Key Files |
|---|------|--------|-----------|
| 1 | Implement PostgresStore behind Store Protocol | 34bd6fd | `_postgres.py`, `__init__.py` |
| 1a | Fix: register_vector ordering + postgres test isolation | 9c94f47 | `_postgres.py`, `test_store_contract.py` |
| 2 | [GATE] Schema applied to live :22000 (cleared in-session) | — | docker compose postgres |
| 3 | Live integration tests — all db_live assertions green | 11d69a0 | `test_store_integration.py` |

## What Was Built

### PostgresStore (`libs/store/src/store/_postgres.py`)

psycopg3-backed production Store implementation:

- `__init__(dsn, blob_root)` — takes DSN from caller, never reads env (D-03)
- `__enter__` — opens one psycopg.connect(row_factory=dict_row) + `register_vector(conn)` (Pitfall 1)
- `__exit__` — commit on clean exit, rollback on error, always close (D-03a)
- `init_schema()` — separate autocommit connection, applies `libs/store/sql/*.sql` in sorted order, then `register_vector(ddl_conn)` AFTER DDL so the extension exists when the adapter registers (Bug fix — PATTERNS.md ordering was wrong for fresh DB)
- `put_item()` — `ON CONFLICT (id) DO UPDATE` upsert + audit row in SAME transaction (DD-5), `Jsonb(item.payload)` wrapper (Pitfall 2), all SQL bind-param only (V5/T-02-01)
- `get_item()` — SELECT by id, None on miss, reconstructs Item from dict_row
- `list_items()` — `WHERE source_type = ANY(%s)` for safe list params (Open Q3), `ORDER BY ts DESC, id DESC LIMIT %s`
- `put_blob()/get_blob()` — delegate to `_blob` helpers (D-01a), `put_blob` also writes audit row when inside context manager

### `__init__.py` updated

`PostgresStore` added to imports and `__all__`. `from store import Store, PostgresStore, InMemoryStore, render_atom` now resolves.

### Live schema on :22000

7 tables applied via `init_schema()`: `articles`, `audit`, `ccir`, `embeddings`, `enrichment`, `entities`, `entity_links`. Extension `vector` confirmed. Both `embeddings.embedding` and `entities.embedding` confirmed as `vector(1024)`. HNSW indexes on both with `vector_cosine_ops`.

### Integration tests (`tests/test_store_integration.py`)

7 `@db_live` tests — all green with DB up, all auto-skip when :22000 unreachable (R8):

| Test | Req | What it proves |
|------|-----|----------------|
| `test_init_schema_idempotent` | R1 | Two calls, no error, IF NOT EXISTS is a no-op |
| `test_all_tables_exist` | R2 | `information_schema` reports exactly 7 tables |
| `test_item_roundtrip` | R2, D-02 | All columns incl. JSONB payload recovered equal after put/get |
| `test_put_item_upsert_live` | R5 | Same id twice → 1 row, latest summary wins |
| `test_dimension_is_1024` | D-05a | Catalog shows `vector(1024)`; 1024-dim insert succeeds, 512-dim rejected |
| `test_vector_cosine_threshold` | R3, D-05b | NATO pair (cos≈0.92) links at >= 0.85; Trump/Putin (cos≈0.72) stays distinct |
| `test_put_item_failure_raises` | must-NOT | Aborted-connection state → psycopg.Error raised, no silent success |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `register_vector` called before CREATE EXTENSION in `init_schema`**
- **Found during:** Task 2 gate — `init_schema()` failed on a fresh DB
- **Issue:** PATTERNS.md pattern calls `register_vector(ddl_conn)` BEFORE applying SQL files. On a fresh database, the `vector` type doesn't exist yet when pgvector tries to register its type adapter → `psycopg.ProgrammingError: vector type not found in the database`
- **Fix:** Moved `register_vector(ddl_conn)` to AFTER the SQL execution loop. On first run: DDL creates the extension, then registration succeeds. On subsequent runs: extension already exists (IF NOT EXISTS), registration succeeds.
- **Files modified:** `libs/store/src/store/_postgres.py`
- **Commit:** 9c94f47

**2. [Rule 1 - Bug] Test isolation missing from postgres fixture in `test_store_contract.py`**
- **Found during:** Full test run with live DB — `test_list_empty_returns_empty_list[postgres]` and `test_list_items_ordering_ts_desc[postgres]` failed because previous postgres tests left data
- **Issue:** The `store` fixture for the postgres param called `init_schema()` but never truncated the tables, so tests sharing the DB interfered with each other
- **Fix:** Added `TRUNCATE ... RESTART IDENTITY` of all infotriage tables before each postgres test
- **Files modified:** `tests/test_store_contract.py`
- **Commit:** 9c94f47

**3. [Rule 1 - Bug] `db_live` decorator applied `skipif` mark only, not `db_live` mark**
- **Found during:** `pytest -m db_live` collected 0 tests from test_store_integration.py
- **Issue:** `db_live = pytest.mark.skipif(...)` creates a `skipif` mark. `pytest -m db_live` selects tests by the `db_live` label, which was never applied.
- **Fix:** Changed `db_live` to a decorator function that applies BOTH `pytest.mark.db_live` (for `-m db_live` selection) AND `pytest.mark.skipif(not _PG_UP, ...)` (for auto-skip). Uses in-place mark application (no functools.wraps) so pytest's fixture injection continues to work.
- **Files modified:** `tests/test_store_integration.py`
- **Commit:** 11d69a0

## Test Results

```
pytest tests/ -q  (no DB)  → 127 passed (integration auto-skipped)
pytest tests/ -q  (DB up)  → 146 passed (all db_live tests run and pass)
pytest -m db_live (DB up)  → 7 passed (integration suite)
```

## Threat Flags

None. All SQL is parameterized (V5/T-02-01). JSONB uses Jsonb() wrapper (T-02-04). DSN comes from caller (T-02-03). pgvector packages confirmed legitimate (T-02-SC, approved in RESEARCH.md). No new trust boundaries introduced beyond what the threat model covers.

## Self-Check: PASSED

- [x] `libs/store/src/store/_postgres.py` exists
- [x] `tests/test_store_integration.py` exists
- [x] Commits 34bd6fd, 9c94f47, 11d69a0 in git log
- [x] 146 tests pass; schema live on :22000 with 7 tables + vector(1024) columns
