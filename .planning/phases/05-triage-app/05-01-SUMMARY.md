---
phase: 05-triage-app
plan: 01
subsystem: database
tags: [postgres, pgvector, store-protocol, inmemory]

requires:
  - phase: 04
    provides: Store Protocol with put_item/get_item; PostgresStore + InMemoryStore base implementations
provides:
  - put_enrichment / get_enrichment / put_embedding / find_near_duplicate on Store Protocol, PostgresStore, InMemoryStore
  - 006-enrichment.sql migration (enrichment scoring columns + unique indexes for upsert)
affects: [05-02, 05-03, 05-04, 05-05]

tech-stack:
  added: []
  patterns:
    - "ON CONFLICT (item_id) DO UPDATE upsert pattern backed by CREATE UNIQUE INDEX IF NOT EXISTS (not ADD CONSTRAINT — invalid Postgres syntax)"
    - "pgvector <=> cosine operator for find_near_duplicate; InMemoryStore mirrors via stdlib math.sqrt cosine loop (D-07)"

key-files:
  created:
    - libs/store/sql/006-enrichment.sql
    - tests/test_triage_enrichment.py
  modified:
    - libs/store/src/store/_protocol.py
    - libs/store/src/store/_postgres.py
    - libs/store/src/store/_inmemory.py

key-decisions:
  - "Used CREATE UNIQUE INDEX IF NOT EXISTS instead of ALTER TABLE ADD CONSTRAINT IF NOT EXISTS (latter is invalid Postgres) — index alone satisfies ON CONFLICT (item_id)"
  - "find_near_duplicate uses <=> (cosine) not <-> (L2); distance threshold computed as 1 - threshold"

patterns-established:
  - "Pattern: idempotent upsert = CREATE UNIQUE INDEX IF NOT EXISTS + ON CONFLICT (col) DO UPDATE SET ... = EXCLUDED.col"

requirements-completed: [R1, R4, ADR-004]

coverage:
  - id: D1
    description: "infotriage.enrichment gains ccir/cnr/score/bucket/why/pmesii/tessoc columns via idempotent migration"
    requirement: "R1"
    verification:
      - kind: unit
        ref: "tests/test_triage_enrichment.py#test_enrichment_schema"
        status: pass
    human_judgment: false
  - id: D2
    description: "put_enrichment / get_enrichment upsert and round-trip, idempotent on repeat writes, score CHECK enforced"
    requirement: "R1"
    verification:
      - kind: unit
        ref: "tests/test_triage_enrichment.py#test_put_get_enrichment"
        status: pass
      - kind: unit
        ref: "tests/test_triage_enrichment.py#test_put_enrichment_idempotent"
        status: pass
      - kind: integration
        ref: "tests/test_triage_enrichment.py#test_enrichment_score_check (db_live)"
        status: pass
    human_judgment: false
  - id: D3
    description: "put_embedding / find_near_duplicate: idempotent vector upsert, cosine-threshold dedup match, empty-store returns None"
    requirement: "R4"
    verification:
      - kind: unit
        ref: "tests/test_triage_enrichment.py#test_find_near_duplicate"
        status: pass
      - kind: unit
        ref: "tests/test_triage_enrichment.py#test_find_near_duplicate_empty"
        status: pass
      - kind: unit
        ref: "tests/test_triage_enrichment.py#test_put_embedding_idempotent"
        status: pass
    human_judgment: false
  - id: D4
    description: "InMemoryStore implements find_near_duplicate via stdlib cosine loop (no live pgvector needed for worker unit tests)"
    requirement: "ADR-004"
    verification:
      - kind: unit
        ref: "tests/test_triage_enrichment.py (inmemory param)"
        status: pass
    human_judgment: false

duration: 4min
completed: 2026-06-29
status: complete
---

# Phase 5 Plan 01: Enrichment Store Methods Summary

**Postgres + InMemory Store methods for enrichment scoring (put/get_enrichment) and pgvector-backed semantic dedup (put_embedding/find_near_duplicate), via an idempotent 006-enrichment.sql migration**

## Performance

- **Duration:** 4 min (22:17:48–22:22:02 UTC+2)
- **Started:** 2026-06-29T22:17:48+02:00
- **Completed:** 2026-06-29T22:22:02+02:00
- **Tasks:** 3 completed
- **Files modified:** 5 (1 created SQL, 1 created test, 3 modified store files)

## Accomplishments
- 006-enrichment.sql: idempotent migration adding 7 enrichment columns (ccir, cnr, score, bucket, why, pmesii, tessoc) plus `enrichment_item_id_unique` and `embeddings_item_id_unique` indexes
- put_enrichment/get_enrichment/put_embedding/find_near_duplicate implemented on Store Protocol, PostgresStore, and InMemoryStore
- find_near_duplicate uses the pgvector `<=>` cosine operator (Postgres) and a stdlib cosine loop (InMemoryStore, D-07) — returns `Optional[str]` matched item_id or None
- 12/12 tests passing (inmemory + db_live postgres) in tests/test_triage_enrichment.py

## Task Commits

Each task was committed atomically:

1. **Task 1: Write failing contract tests for enrichment + embedding store methods** - `0837fb0` (test)
2. **Task 2: Add 006-enrichment.sql idempotent migration (unique indexes + 7 columns)** - `a98a5e0` (chore)
3. **Task 3: Implement put_enrichment / get_enrichment / put_embedding / find_near_duplicate** - `eafc031` (feat)

_Note: Task 1 was the RED commit (TDD); Task 3 turned the suite GREEN._

## Files Created/Modified
- `libs/store/sql/006-enrichment.sql` - idempotent migration: unique indexes + 7 enrichment columns
- `tests/test_triage_enrichment.py` - 7-test contract suite, parametrized over inmemory + db_live postgres
- `libs/store/src/store/_protocol.py` - 4 new method signatures + Optional import
- `libs/store/src/store/_postgres.py` - ON CONFLICT upsert implementations + `<=>` cosine query
- `libs/store/src/store/_inmemory.py` - dict-backed implementations + `_cosine_sim` stdlib helper

## Decisions Made
- CREATE UNIQUE INDEX IF NOT EXISTS instead of ALTER TABLE ADD CONSTRAINT IF NOT EXISTS — the latter is invalid Postgres syntax; the unique index alone satisfies `ON CONFLICT (item_id)`
- `<=>` (cosine) operator chosen over `<->` (L2) for find_near_duplicate, matching ADR-004's cosine-threshold dedup design

## Deviations from Plan
None - plan executed exactly as written.

## Issues Encountered
None. This SUMMARY.md was reconstructed after the fact: the 3 task commits (test/migration/implement) landed in a prior session that ended before SUMMARY.md was written, tripping the execute-phase safe-resume gate. Verified before closing out: `pytest tests/test_triage_enrichment.py` → 12/12 passed; grep confirmed no `ADD CONSTRAINT IF NOT EXISTS` and no f-string SQL in `_postgres.py`.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Wave-2 worker plan (05-03) can now call put_enrichment/find_near_duplicate against either store
- No blockers

---
*Phase: 05-triage-app*
*Completed: 2026-06-29*
