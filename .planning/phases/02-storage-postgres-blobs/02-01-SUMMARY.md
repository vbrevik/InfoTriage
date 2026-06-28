---
phase: 02-storage-postgres-blobs
plan: "01"
subsystem: storage
status: complete
tags: [postgres, pgvector, psycopg3, ddl, docker-compose, libs/store]

dependency_graph:
  requires: []
  provides:
    - libs/store (editable package, importable as `store`)
    - libs/store/sql/*.sql (5 ordered DDL files, 7 tables)
    - postgres service on :22000 (docker-compose)
    - db_live pytest marker
  affects:
    - plans 02-02, 02-03, 02-04 (all depend on store package + DDL)

tech_stack:
  added:
    - psycopg 3.3.4 (psycopg[binary]) — psycopg3 Postgres adapter
    - pgvector 0.4.2 — vector type registration for psycopg3
    - numpy >= 1.24 — float32 arrays for pgvector params
  patterns:
    - libs/store mirrors libs/contracts src-layout (setuptools, editable install)
    - Versioned .sql files applied in lexical order (001-schema first)
    - HNSW cosine indexes (m=16, ef_construction=64) per D-05b

key_files:
  created:
    - libs/store/pyproject.toml
    - libs/store/src/store/__init__.py
    - libs/store/sql/001-schema.sql
    - libs/store/sql/002-articles.sql
    - libs/store/sql/003-vectors.sql
    - libs/store/sql/004-audit.sql
    - libs/store/sql/005-stubs.sql
  modified:
    - requirements-dev.txt (added -e ./libs/store)
    - pyproject.toml (added db_live marker)
    - docker-compose.yml (added postgres service)

decisions:
  - "DD-1: CREATE SCHEMA IF NOT EXISTS infotriage (unquoted/lowercase); SET search_path = infotriage, public in 001-schema.sql"
  - "DD-2: Versioned .sql files 001-005, IF NOT EXISTS throughout, no migration framework"
  - "D-02/D-02a: articles hybrid mapping (real columns + JSONB payload), no tsvector/GIN"
  - "D-05a/D-05b: vector(1024) dimensions, HNSW cosine ops m=16 ef_construction=64"
  - "DD-3: enrichment/ccir as bare stubs (id, item_id, created_at only)"
  - "HNSW without CONCURRENTLY — cannot run inside transaction; plain CREATE INDEX IF NOT EXISTS used"

metrics:
  duration: "~10 minutes"
  completed: "2026-06-28"
  tasks_completed: 3
  tasks_total: 3
  files_created: 9
  files_modified: 3
---

# Phase 02 Plan 01: Storage Foundation — libs/store Scaffold, DDL, docker-compose

One-liner: editable `libs/store` package with psycopg3/pgvector deps, five versioned SQL files defining 7 infotriage tables with HNSW cosine indexes, and pgvector/pgvector:pg16 compose service on :22000.

## Summary

This plan lays the Phase 2 storage foundation:

1. **libs/store package** — mirrors the `libs/contracts` structure; editable install, depends on `contracts` (D-01), psycopg[binary]>=3.3, pgvector>=0.4.2, numpy>=1.24. Placeholder `__init__.py` (exports added in plan 02).

2. **SQL DDL** — five ordered, idempotent `.sql` files under `libs/store/sql/`: schema+extension (001), articles hybrid mapping (002), vector tables+HNSW indexes (003), audit table (004), enrichment+ccir stubs (005). All use `IF NOT EXISTS`; 7 tables total.

3. **docker-compose postgres service** — `pgvector/pgvector:pg16` on :22000, `pg_isready` healthcheck, dev-only password documented as non-secret.

All 87 existing tests remain green.

## Task Results

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Scaffold libs/store and install deps | 86a37fe | libs/store/pyproject.toml, src/store/__init__.py, requirements-dev.txt, pyproject.toml |
| 2 | Author SQL DDL for infotriage schema | e63add0 | libs/store/sql/001-005.sql |
| 3 | Add postgres service to docker-compose | 935ee6f | docker-compose.yml |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Comment text triggered DDL verifier assertions**

- **Found during:** Task 2 verification
- **Issue:** The comment `-- D-02a: no tsvector/GIN` in 002-articles.sql contained the word "tsvector", and the comment `-- NOTE: CREATE INDEX IF NOT EXISTS (never CONCURRENTLY ...)` in 003-vectors.sql contained "concurrently". The plan's verify script scans the entire file text (including comments), so both triggered assertion failures.
- **Fix:** Rephrased comments to remove the banned words while preserving intent. "tsvector/GIN" → "FTS/GIN"; "never CONCURRENTLY" → "no parallel build option".
- **Files modified:** libs/store/sql/002-articles.sql, libs/store/sql/003-vectors.sql
- **Commit:** e63add0

## Known Stubs

None — this plan only creates DDL and package scaffolding. No data flows or UI rendering are involved.

## Threat Flags

No new security-relevant surface beyond the threat register:

- `docker-compose.yml` postgres service: dev-only password `infotriage_dev` is documented as non-secret in the file comment; production uses `.env` via `INFOTRIAGE_PG_DSN` (T-02-03 disposition: mitigate — satisfied).
- psycopg/pgvector/numpy packages: confirmed legitimate via Context7 + Package Legitimacy Audit in RESEARCH (T-02-SC disposition: mitigate — satisfied via version pins).

## Self-Check: PASSED

Files exist:
- [x] libs/store/pyproject.toml — FOUND
- [x] libs/store/src/store/__init__.py — FOUND
- [x] libs/store/sql/001-schema.sql — FOUND
- [x] libs/store/sql/002-articles.sql — FOUND
- [x] libs/store/sql/003-vectors.sql — FOUND
- [x] libs/store/sql/004-audit.sql — FOUND
- [x] libs/store/sql/005-stubs.sql — FOUND
- [x] requirements-dev.txt contains -e ./libs/store — FOUND
- [x] pyproject.toml registers db_live marker — FOUND
- [x] docker-compose.yml postgres service on :22000 — FOUND

Commits verified:
- [x] 86a37fe — feat(02-01): scaffold libs/store package and install psycopg3 dependencies
- [x] e63add0 — feat(02-01): author versioned SQL DDL for full infotriage schema (7 tables + HNSW)
- [x] 935ee6f — feat(02-01): add postgres pgvector service to docker-compose on :22000

Test suite: 87 passed (no regressions).
