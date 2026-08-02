---
phase: 12-cnr-alerting-dissemination
plan: 07
subsystem: database
tags: [pydantic, postgres, psycopg3, store-protocol, item-contract]

requires:
  - phase: 12-cnr-alerting-dissemination (plan 12-02)
    provides: infotriage.alert_state substrate in _postgres.py/_inmemory.py — this plan's
      edits land in the same two files without touching alert_state's additions
provides:
  - "Item.body: an optional string field on the shared Item contract, defaulting to None,
    documented as never-empty-string / no-size-cap, excluded from computed identity"
  - "PostgresStore.put_item/get_item body-aware write path: body column in the INSERT
    column list, VALUES tuple, and ON CONFLICT DO UPDATE clause; body in the get_item
    SELECT list and Item constructor"
  - "InMemoryStore.put_item parity: identical empty/whitespace-to-None coercion, applied
    to a copied Item rather than mutating the caller's object"
  - "tests/test_item_body_persistence.py: 15 parametrized cases (InMemoryStore always,
    PostgresStore under db_live) proving round-trip, NULL coercion, ON CONFLICT refresh/
    clear, and the >=1MB oversized-body backstop"
affects: [12-08 (seven ingest adapters set Item.body — one-line change per adapter),
  12-09 (alerting-path body-exclusion prohibition test)]

tech-stack:
  added: []
  patterns:
    - "Single choke-point normalization: the empty-string/whitespace-to-None coercion
      for body lives once in each store's put_item, not per-adapter — matches the
      existing pattern for other Item fields that need store-layer normalization"

key-files:
  created:
    - tests/test_item_body_persistence.py
  modified:
    - libs/contracts/src/contracts/_item.py
    - libs/store/src/store/_postgres.py
    - libs/store/src/store/_inmemory.py

key-decisions:
  - "body placed between summary and body_ref in both the contract field order and the
    SQL column order, per the plan's explicit ordering requirement"
  - "Coercion rule (None | '' | whitespace-only -> None) implemented identically in both
    stores rather than centralized in the contract, so Item itself stays free of
    store-layer normalization logic — matches D-04's narrow shape"
  - "list_items() in both stores intentionally NOT touched — the plan's artifact list
    scopes the SQL surface to put_item's INSERT/ON CONFLICT and get_item's SELECT only;
    list_items already existed before this plan and adding body there is out of this
    plan's stated scope"

patterns-established:
  - "Store-layer choke-point coercion: normalize once per store implementation at the
    write boundary, verified by a parity test across both implementations, rather than
    validating in the contract or leaving it to callers"

requirements-completed: [ADR-003]

coverage:
  - id: D1
    description: "Item contract carries an optional body field (default None) that does
      not affect item identity"
    requirement: "ADR-003"
    verification:
      - kind: unit
        ref: "tests/test_item_body_persistence.py#test_body_does_not_affect_item_identity"
        status: pass
      - kind: unit
        ref: "python -c field-order/default assertion (Task 1 <verify>)"
        status: pass
    human_judgment: false
  - id: D2
    description: "A body-bearing Item round-trips through put_item/get_item byte-identically
      on both InMemoryStore and PostgresStore, including a >=1MB oversized transcript with
      no truncation"
    requirement: "ADR-003"
    verification:
      - kind: unit
        ref: "tests/test_item_body_persistence.py#test_body_round_trips_byte_identical"
        status: pass
      - kind: integration
        ref: "tests/test_item_body_persistence.py#test_oversized_body_round_trips_with_no_truncation[postgres]"
        status: pass
    human_judgment: false
  - id: D3
    description: "Bodyless, empty-string, and whitespace-only Items all persist as SQL
      NULL (never empty string) on both store implementations, and re-putting with a
      changed/cleared body updates/clears the stored value"
    requirement: "ADR-003"
    verification:
      - kind: unit
        ref: "tests/test_item_body_persistence.py#test_bodyless_variants_persist_as_null"
        status: pass
      - kind: integration
        ref: "tests/test_item_body_persistence.py#test_reput_with_no_body_clears_to_null[postgres]"
        status: pass
    human_judgment: false

duration: ~15min
completed: 2026-08-01
status: complete
---

# Phase 12 Plan 07: Item.body contract + store write path Summary

**Optional `Item.body` field on the shared contract with a body-aware `put_item`/`get_item` write path in both stores, NULL-not-empty-string enforced at a single choke point, and a 15-case parity test suite including a >=1MB no-truncation backstop.**

## Performance

- **Duration:** ~15 min
- **Completed:** 2026-08-01T21:12:53Z
- **Tasks:** 2/2
- **Files modified:** 4 (1 created, 3 modified)

## Accomplishments

- Added `Item.body: Optional[str] = None` to `libs/contracts/src/contracts/_item.py`,
  positioned between `summary` and `body_ref`, documented as source-full-text /
  never-empty-string / no-size-cap, and confirmed not to participate in the computed
  `id` field (two Items differing only in body share the same id).
- `PostgresStore.put_item` now writes `body` into the INSERT column list, VALUES tuple,
  and `ON CONFLICT DO UPDATE` clause (positioned between `summary` and `body_ref`);
  `get_item` selects it and passes it to the `Item` constructor. The empty-string/
  whitespace-only-to-`None` coercion is applied once, immediately before binding — the
  single place SPEC R7's "never empty string" rule is enforced.
- `InMemoryStore.put_item` applies the identical coercion to a copied `Item`
  (`model_copy(update=...)`), never mutating the caller's object — parity with
  PostgresStore's observable behavior without duplicating SQL-shaped logic.
- `tests/test_item_body_persistence.py`: 15 cases parametrized over both store
  implementations (`db_live`-guarded for postgres), covering byte-identical round-trip,
  all three NULL-producing input variants (raw SQL `NULL` assertion for postgres via
  a direct cursor query), `ON CONFLICT DO UPDATE` refresh and clear semantics, the
  `>=1_100_000`-character oversized-body backstop (generated at test time, not
  committed to the repo), and identity independence from body.

## Task Commits

1. **Task 1: Add the optional body field to the Item contract** - `d95485c` (feat)
2. **Task 2: Body-aware put_item/get_item with parity and the oversized-body backstop** - `a529b8b` (feat)

**Plan metadata:** (this commit)

## Files Created/Modified

- `libs/contracts/src/contracts/_item.py` - added `body` field with locked-property docstring comment
- `libs/store/src/store/_postgres.py` - `body` in `put_item`'s INSERT/VALUES/ON CONFLICT DO UPDATE and `get_item`'s SELECT/constructor; empty/whitespace-to-None coercion before binding
- `libs/store/src/store/_inmemory.py` - identical coercion in `put_item`, applied to a copied `Item`
- `tests/test_item_body_persistence.py` - new 15-case parametrized persistence suite

## Decisions Made

- Coercion lives in each store's `put_item`, not in the `Item` contract itself — keeps
  the contract free of store-layer normalization concerns and matches the plan's stated
  rationale (one choke point beats seven adapter-level checks).
- `list_items()` was left untouched in both stores. The plan's "Modified SQL surface"
  section names only `put_item`'s INSERT/ON CONFLICT and `get_item`'s SELECT/constructor;
  `list_items` isn't in that list and isn't exercised by any of the plan's `<behavior>`
  assertions, so extending it was out of scope for this plan (scope boundary rule).
  Flagged here for visibility to plan 12-08/12-09 authors, not fixed.

## Deviations from Plan

None - plan executed exactly as written. Both tasks' `<verify>` commands and all
`<acceptance_criteria>` passed on the first implementation without needing a Rule 1-3
auto-fix.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required. No new env vars introduced.

## Verification

- `python -m pytest tests/test_item_body_persistence.py -x -q` — 8 passed, 7 skipped
  locally (no `INFOTRIAGE_TEST_DSN` in ambient shell); all 15 passed under
  `make -f ops/Makefile test-safe`'s throwaway Postgres.
- `make -f ops/Makefile test-safe` — **755 passed, 1 skipped, 0 failed** (740 baseline +
  15 new tests from this plan, 0 regressions; the 1 skip is the pre-existing
  `test_real_bearer_token_accepted` NTFY_TOKEN-not-in-ambient-env skip from 12-03,
  unchanged).
- `black --check` clean on all 4 files (test file was auto-reformatted once, then
  re-verified clean and re-run green).
- `mypy` clean on all 3 production files and the test file.
- Source-level checks: `EXCLUDED.body` present in the `ON CONFLICT DO UPDATE` clause; no
  `.body[` slicing and no HTML-stripping/sanitization calls in either store file (grep
  confirmed).

## Next Phase Readiness

- Plan 12-08 (seven ingest adapters) can now set `Item.body` and rely on the store layer
  to enforce NULL-not-empty-string with no per-adapter logic needed — the field and its
  write path are proven end-to-end on both store implementations.
- Plan 12-09's alerting-path body-exclusion prohibition test has a real column to assert
  against; `articles.body` is populated by `put_item` starting with this plan (previously
  always NULL per migration 009's own comment).
- No blockers carried forward.

## Self-Check: PASSED

- FOUND: tests/test_item_body_persistence.py
- FOUND: d95485c (Task 1 commit)
- FOUND: a529b8b (Task 2 commit)

---
*Phase: 12-cnr-alerting-dissemination*
*Completed: 2026-08-01*
