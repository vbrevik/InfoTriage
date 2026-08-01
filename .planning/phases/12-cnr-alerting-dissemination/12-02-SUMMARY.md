---
phase: 12-cnr-alerting-dissemination
plan: 02
subsystem: database
tags: [postgres, psycopg3, store-protocol, dedupe, throttle, tdd]

# Dependency graph
requires:
  - phase: 12-cnr-alerting-dissemination (plan 01)
    provides: apps/alerting service shape (emitter/outbox/deep_link/alerting_worker) this substrate will be wired into by plans 12-04/12-05
provides:
  - infotriage.alert_state Postgres table (migration 011-alert-state.sql)
  - Store protocol methods claim_alert, count_alerts_in_window, mark_alert_suppressed, list_undigested_suppressed, mark_alerts_digested, mark_alert_outcome
  - PostgresStore + InMemoryStore parity implementations of all six methods
  - Injectable-clock TTL/window semantics proven deterministic in tests
affects: [12-04-dedupe, 12-05-throttle, 12-06, 12-07, 12-08, 12-09]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Atomic check-and-set via single INSERT ... ON CONFLICT DO UPDATE ... WHERE ... RETURNING statement — a failing WHERE clause degrades to Postgres's native DO NOTHING, giving race-safe claim semantics with zero application-level locking."
    - "Injectable now: datetime | None = None on every time-aware Store method, defaulting to server/wall-clock time, for deterministic TTL/sliding-window testing."
    - "Outcome dispatch via literal-per-branch SQL (if/elif on a validated string) instead of composing a column name — avoids f-string SQL entirely even for a 2-way column choice."

key-files:
  created:
    - libs/store/sql/011-alert-state.sql
    - tests/test_alerting_state_store.py
  modified:
    - libs/store/src/store/_protocol.py
    - libs/store/src/store/_postgres.py
    - libs/store/src/store/_inmemory.py
    - tests/test_store_integration.py

key-decisions:
  - "claim_alert's re-fire path resets suppressed/digested_at/delivered_at/dlx_at to NULL/false so a re-fired alert behaves exactly like a fresh one for downstream throttle/digest logic."
  - "list_undigested_suppressed and mark_alerts_digested both accept `now` for protocol signature symmetry with the other four time-aware methods, even though neither implementation currently uses it for filtering (digested_at IS NULL is time-independent) — kept for forward compatibility with plan 12-06's digest scheduler."
  - "Raw-row test helper (_raw_row) reads PostgresStore via its existing public cursor() API and InMemoryStore via its private _alert_state dict, because the Store protocol itself intentionally exposes no direct row-read — list_undigested_suppressed only returns 6 of 11 columns and only for suppressed+undigested rows."

patterns-established:
  - "Migration test split across two tasks in the same file: Task 1 lands `-k migration`-selectable tests (static SQL declaration check + db_live init_schema/idempotency check) before the Store methods exist; Task 2 appends the parity + concurrency tests to the same file. Lets each task's own <verify> command run standalone."

requirements-completed: [ADR-003]

coverage:
  - id: D1
    description: "Migration 011-alert-state.sql creates infotriage.alert_state idempotently, picked up automatically by init_schema()'s glob-and-apply."
    requirement: "ADR-003"
    verification:
      - kind: unit
        ref: "tests/test_alerting_state_store.py::test_alert_state_migration_sql_declares_table_and_load_bearing_index"
        status: pass
      - kind: integration
        ref: "tests/test_alerting_state_store.py::test_alert_state_migration_creates_table_and_reapply_is_idempotent"
        status: pass
    human_judgment: false
  - id: D2
    description: "claim_alert atomically dedupes on (item_id, cnr_tier) within a 24h TTL with an injectable clock, and two concurrent claims of the same dedupe_id yield exactly one winner."
    requirement: "ADR-003"
    verification:
      - kind: unit
        ref: "tests/test_alerting_state_store.py::test_claim_alert_fresh_dedupe_id_claims_and_writes_one_row"
        status: pass
      - kind: unit
        ref: "tests/test_alerting_state_store.py::test_claim_alert_within_ttl_suppressed_and_fired_at_unchanged"
        status: pass
      - kind: unit
        ref: "tests/test_alerting_state_store.py::test_claim_alert_beyond_ttl_refires_and_resets_state"
        status: pass
      - kind: integration
        ref: "tests/test_alerting_state_store.py::test_claim_alert_concurrent_claims_yield_exactly_one_winner"
        status: pass
    human_judgment: false
  - id: D3
    description: "count_alerts_in_window computes sliding-window throttle counts from an injectable clock against fired_at, excluding suppressed rows."
    requirement: "ADR-003"
    verification:
      - kind: unit
        ref: "tests/test_alerting_state_store.py::test_count_alerts_in_window_counts_only_nonsuppressed_within_window"
        status: pass
      - kind: unit
        ref: "tests/test_alerting_state_store.py::test_count_alerts_in_window_excludes_rows_outside_window"
        status: pass
    human_judgment: false
  - id: D4
    description: "mark_alert_suppressed / list_undigested_suppressed / mark_alerts_digested form the never-silently-dropped digest pipeline for throttled alerts."
    requirement: "ADR-003"
    verification:
      - kind: unit
        ref: "tests/test_alerting_state_store.py::test_mark_alert_suppressed_flips_flag_and_records_pmesii_title"
        status: pass
      - kind: unit
        ref: "tests/test_alerting_state_store.py::test_list_undigested_suppressed_returns_until_digested"
        status: pass
      - kind: unit
        ref: "tests/test_alerting_state_store.py::test_mark_alerts_digested_empty_sequence_is_noop"
        status: pass
    human_judgment: false
  - id: D5
    description: "mark_alert_outcome records delivered/dead_lettered independently and rejects any other outcome string."
    requirement: "ADR-003"
    verification:
      - kind: unit
        ref: "tests/test_alerting_state_store.py::test_mark_alert_outcome_sets_delivered_or_dlx_independently"
        status: pass
      - kind: unit
        ref: "tests/test_alerting_state_store.py::test_mark_alert_outcome_raises_on_bogus_outcome"
        status: pass
    human_judgment: false
  - id: D6
    description: "PostgresStore and InMemoryStore return identical results for every alert_state method under the same call sequence (D-02 parity)."
    requirement: "ADR-003"
    verification:
      - kind: integration
        ref: "tests/test_alerting_state_store.py — 10 behavior tests parametrized over [inmemory, postgres] via the `store` fixture"
        status: pass
    human_judgment: false

duration: ~25min
completed: 2026-08-01
status: complete
---

# Phase 12 Plan 2: Postgres alert_state dedupe/throttle substrate Summary

**infotriage.alert_state Postgres table (migration 011) plus six Store protocol methods (claim_alert, count_alerts_in_window, mark_alert_suppressed, list_undigested_suppressed, mark_alerts_digested, mark_alert_outcome) implemented with matching PostgresStore/InMemoryStore semantics, injectable clocks throughout, and a real two-connection race test proving the atomic dedupe claim.**

## Performance

- **Duration:** ~25 min
- **Completed:** 2026-08-01T16:42Z
- **Tasks:** 2 (Task 1 migration, Task 2 TDD Store methods)
- **Files modified:** 6 (2 created, 4 modified)

## Accomplishments

- `libs/store/sql/011-alert-state.sql` — idempotent `infotriage.alert_state` table with the load-bearing `alert_state_dedupe_id_unique` index (backs the atomic ON CONFLICT claim), `alert_state_fired_at_idx` (sliding-window scans), and `alert_state_digest_pending_idx` (digest lookup).
- Six new Store protocol methods declared in `_protocol.py` and implemented identically in `_postgres.py` and `_inmemory.py`, every time-aware one taking a keyword-only `now: datetime | None = None` for deterministic TTL/window testing (SPEC R2/R3).
- `claim_alert` is a single `INSERT ... ON CONFLICT (dedupe_id) DO UPDATE ... WHERE ... RETURNING` statement — no separate read anywhere in the race path (T-12-07). A two-connection threaded race test against a live throwaway Postgres confirms exactly one winner per contested `dedupe_id`.
- 23 new tests in `tests/test_alerting_state_store.py`, structured so `-k migration` isolates the two migration-only tests from the ten parity behavior tests (parametrized over `InMemoryStore`/`PostgresStore`) and the one concurrency test.
- `make -f ops/Makefile test-safe`: **720 passed, 0 failed** against a throwaway Postgres (697 baseline + 23 new, 0 regressions). mypy `--strict` clean, black clean.

## Task Commits

Each task was committed atomically (Task 2 followed the tdd="true" RED→GREEN cycle per plan):

1. **Task 1: Migration 011-alert-state.sql** — `79999da` (feat) — SQL migration + 2 migration-only tests + a Rule-1 fix to a pre-existing test invalidated by the new table.
2. **Task 2 RED: failing tests for alert_state Store methods** — `cb6da82` (test) — 10 parity tests + 1 concurrency test added; confirmed 10 failed / 1 passed / 12 skipped (AttributeError — methods don't exist yet).
3. **Task 2 GREEN: implement alert_state Store methods** — `0211a1e` (feat) — six Protocol methods + PostgresStore/InMemoryStore implementations; confirmed all green, including a Rule-1 bugfix found via the full `make test-safe` run.

**Plan metadata:** committed via `<final_commit>` below (this SUMMARY + STATE.md + ROADMAP.md).

## Files Created/Modified

- `libs/store/sql/011-alert-state.sql` — new `infotriage.alert_state` table + 3 indexes.
- `libs/store/src/store/_protocol.py` — 6 new method declarations (dedupe/throttle/digest/outcome).
- `libs/store/src/store/_postgres.py` — 6 new methods; `claim_alert` uses `make_interval(secs => %s)` for the TTL, `mark_alert_outcome` dispatches via a literal-per-branch if/elif (no SQL string built from the outcome value).
- `libs/store/src/store/_inmemory.py` — 6 new methods backed by a `_alert_state: dict[str, dict]`, timezone-aware throughout, `list_undigested_suppressed` sorts with NULLS-LAST parity to match Postgres's `ORDER BY pmesii ASC`.
- `tests/test_alerting_state_store.py` — new file, 23 tests (2 migration + 10 parametrized-over-both-stores behavior + 1 empty-sequence no-op + 1 raises + 1 concurrency; the `store` fixture parametrization is what proves D-02 parity across all behavior tests).
- `tests/test_store_integration.py` — `test_all_tables_exist`'s expected table set updated to include `alert_state` (Rule 1: pre-existing assertion invalidated by this plan's new migration, same pattern used when `ccir_vectors` was added in a prior phase).

## Decisions Made

- **Re-fire fully resets alert state.** A `claim_alert` call that lands beyond the TTL clears `suppressed`/`digested_at`/`delivered_at`/`dlx_at` to their fresh-claim defaults, so downstream throttle/digest code never has to special-case "was this dedupe_id previously suppressed/delivered."
- **`now` kept on `list_undigested_suppressed`/`mark_alerts_digested` for signature symmetry** even though the current query logic doesn't need it (digest-pending is a boolean/null check, not a time-window check) — reserved for plan 12-06's digest scheduler if it needs clock injection later.
- **Test-only raw-row helper (`_raw_row`)** reads state through `PostgresStore.cursor()` (already-public ad-hoc-SELECT API) for Postgres and the private `_alert_state` dict for InMemoryStore — the Store protocol deliberately exposes no full-row getter, so this was necessary to assert `suppressed`/`digested_at`/`delivered_at`/`dlx_at` after the re-fire reset (private-attribute test access is an established pattern in this suite, e.g. `tests/test_bus_consume.py`'s `bus._queues`).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] claim_alert's ON CONFLICT DO UPDATE omitted item_id/cnr_tier**
- **Found during:** Task 2 GREEN, first `make -f ops/Makefile test-safe` run against a live throwaway Postgres.
- **Issue:** the `DO UPDATE SET` clause refreshed `fired_at`/`alert_id`/`suppressed`/`digested_at`/`delivered_at`/`dlx_at` on a TTL-expired re-fire but never `item_id` or `cnr_tier` — a re-fire carrying a different item_id/cnr_tier would silently keep the stale values from the original claim. `InMemoryStore`'s dict `.update()` already updated these fields correctly, so the bug surfaced only as a PostgresStore/InMemoryStore parity mismatch under `db_live` — exactly the failure class this plan's D-02 parity requirement exists to catch (`test_claim_alert_beyond_ttl_refires_and_resets_state[postgres]` failed with `item_id` still `'item-1'` instead of `'item-2'`).
- **Fix:** added `item_id = EXCLUDED.item_id, cnr_tier = EXCLUDED.cnr_tier` to the `DO UPDATE SET` clause in `claim_alert`.
- **Files modified:** `libs/store/src/store/_postgres.py`
- **Verification:** `make -f ops/Makefile test-safe` — 720/0/0, including the `[postgres]` parametrization of the previously-failing test.
- **Committed in:** `0211a1e` (Task 2 GREEN commit)

**2. [Rule 1 - Bug] `tests/test_store_integration.py::test_all_tables_exist` invalidated by the new migration**
- **Found during:** Task 1, first `make -f ops/Makefile test-safe` run.
- **Issue:** this pre-existing test asserts an exact set of `infotriage.*` table names; adding `011-alert-state.sql` legitimately grows that set, so the assertion failed with `alert_state` as an unexpected extra table. Same pattern noted in prior session history when `ccir_vectors` was added.
- **Fix:** added `"alert_state"` to the `expected` set.
- **Files modified:** `tests/test_store_integration.py`
- **Verification:** `make -f ops/Makefile test-safe` — 720/0/0.
- **Committed in:** `79999da` (Task 1 commit)

**3. [mypy strictness, not a deviation rule but noted for completeness] count_alerts_in_window's fetchone() result needed a narrowing assert**
- **Found during:** Task 2 GREEN, `mypy libs/store/src/store/_postgres.py`.
- **Issue:** `psycopg`'s `fetchone()` return type is `dict | None`; mypy correctly flagged indexing a possibly-`None` value even though a `COUNT(*)` query always returns exactly one row.
- **Fix:** added `assert row is not None  # COUNT(*) always returns exactly one row` before the index access, matching the codebase's existing assert-based narrowing style (e.g. `assert self._conn is not None`).
- **Files modified:** `libs/store/src/store/_postgres.py`
- **Verification:** `mypy libs/store/src/store/_protocol.py libs/store/src/store/_postgres.py libs/store/src/store/_inmemory.py` → `Success: no issues found in 3 source files`.
- **Committed in:** `0211a1e` (Task 2 GREEN commit)

---

**Total deviations:** 2 auto-fixed (both Rule 1 bugs) + 1 type-narrowing fix.
**Impact on plan:** All fixes necessary for correctness/parity (item_1) and test-suite accuracy (item 2). No scope creep — no files touched outside what the migration/methods legitimately require.

## TDD Gate Compliance

Task 2 (`tdd="true"`) followed the RED→GREEN gate sequence: `cb6da82` (`test(12-02): ...`) landed 10 failing tests confirmed via `AttributeError: 'InMemoryStore' object has no attribute 'claim_alert'`, then `0211a1e` (`feat(12-02): ...`) made them pass. No REFACTOR commit was needed — the implementation converged directly to the final form (the one Rule-1 fix found during GREEN was folded into the GREEN commit, not a separate refactor pass).

## Issues Encountered

None beyond the two Rule-1 bugs documented above — both were caught by the plan's own verification gate (`make -f ops/Makefile test-safe` against a live throwaway Postgres), which is exactly what that gate is for.

## User Setup Required

None — no external service configuration required. This plan is pure Postgres schema + Store-layer code; no new environment variables.

## Next Phase Readiness

- `infotriage.alert_state` and all six Store methods are ready for plans 12-04 (dedupe) and 12-05 (throttle) to bind against directly — the plan's `key_links` note that these method signatures are the contract those plans consume.
- Plan 12-03 (Wave 2, ntfy Bearer-token wiring per STATE.md's open item) has no dependency on this plan and can proceed independently.
- No blockers. Baseline is 720 passed / 0 failed / 0 skipped-unexpectedly (db_live variants ran green under the throwaway Postgres in `make test-safe`; they skip cleanly without `INFOTRIAGE_TEST_DSN` set, which is the normal interactive-shell state).

---
*Phase: 12-cnr-alerting-dissemination*
*Completed: 2026-08-01*

## Self-Check: PASSED

All created/modified files verified present on disk; all 3 task commits (`79999da`, `cb6da82`, `0211a1e`) verified present in git history.
