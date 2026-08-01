---
phase: 12-cnr-alerting-dissemination
plan: 04
subsystem: alerting
tags: [rabbitmq, aio-pika, sha256, dedupe, race-condition, ntfy, cnr]

# Dependency graph
requires:
  - phase: 12-01
    provides: apps/alerting tracer (emitter.py, outbox.py, deep_link.py, alerting_worker.py) bound to verdict.ready only
  - phase: 12-02
    provides: Postgres alert_state substrate — Store.claim_alert atomic INSERT-ON-CONFLICT check-and-set, InMemoryStore parity
provides:
  - apps/alerting/dedupe.py — compute_dedupe_id (SPEC R2 sha256 formula) and claim() wrapping Store.claim_alert
  - Dual-trigger emitter: handle_verdict_ready + handle_sab_published + _extract_cat_i_item_ids, sharing a single _emit_if_claimed path
  - sab.published now bound to q.alerting (ROUTING_KEY_TO_QUEUE second entry) alongside q.notify
  - run_consumer registers one shared handler for both routing keys on q.alerting, dispatching on the decoded event field
affects: [12-05, 12-06, 12-09]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Atomic claim-before-read: claim() is called before any Store read of item/enrichment — the claim itself is the entire race window, never a read-then-write guard"
    - "One handler per shared queue, dispatch on payload event field — two routing keys bound to the same queue must share one consumer callable, since RabbitMQ round-robins competing consumers on one queue"
    - "Back-compat shim for a superseded call shape — handle_trigger kept as a thin wrapper so an out-of-scope test file's direct calls survive a signature change unmodified"

key-files:
  created:
    - apps/alerting/dedupe.py
    - tests/test_alerting_dedupe.py
    - tests/test_alerting_emitter.py
  modified:
    - apps/alerting/emitter.py
    - libs/contracts/src/contracts/_bus_rabbitmq.py
    - tests/conftest.py

key-decisions:
  - "compute_dedupe_id extracted into dedupe.py as the single definition; emitter.build_alert_payload now imports it instead of inlining the sha256 call"
  - "build_alert_payload gained optional alert_id/dedupe_id keyword params (default to fresh generation) so the dual-trigger path can reuse the winning claim's identity while the tracer test's 4-positional-arg call keeps working unchanged"
  - "handle_trigger kept as a back-compat shim (not deleted) because tests/test_alerting_tracer.py — outside this plan's files_modified — calls it directly with the pre-12-04 (item_id, payload, store, client) shape; the shim delegates to the same _emit_if_claimed path so it stays behaviorally identical, just now claim-gated"
  - "stub_ntfy_server + _RecordingHandler extracted from test_alerting_tracer.py into tests/conftest.py per the plan's explicit direction; the tracer test's own local fixture definition was left untouched (harmless duplication, zero risk to an out-of-scope file)"

patterns-established:
  - "Pattern: shared-queue dual-routing-key consumer — bind two routing keys to one queue.consume() attaches per routing key, but wire the SAME handler function to both, and dispatch internally on the message's own discriminator field. Never rely on which consume() call delivered a message when both share a queue."

requirements-completed: [ADR-003]

coverage:
  - id: D1
    description: "compute_dedupe_id/claim in dedupe.py — reproducible 16-char sha256 identity, tier-sensitive, atomic Store-backed claim with TTL re-fire"
    requirement: "ADR-003"
    verification:
      - kind: unit
        ref: "tests/test_alerting_dedupe.py — 6 tests (stability, independent-hash equality, tier-sensitivity, claim True/False/True-after-TTL, no cross-suppression)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Dual-trigger exactly-once egress — verdict.ready and sab.published both bound to q.alerting, either order collapses to exactly one push via the atomic claim"
    requirement: "ADR-003"
    verification:
      - kind: unit
        ref: "tests/test_alerting_emitter.py::test_verdict_ready_then_sab_published_yields_exactly_one_request"
        status: pass
      - kind: unit
        ref: "tests/test_alerting_emitter.py::test_sab_published_then_verdict_ready_yields_exactly_one_request"
        status: pass
      - kind: unit
        ref: "tests/test_alerting_emitter.py::test_ttl_expired_identity_alerts_again"
        status: pass
    human_judgment: false
  - id: D3
    description: "Non-CAT-I / missing-cnr / missing-enrichment inputs produce zero egress on both event shapes, no exceptions"
    requirement: "ADR-003"
    verification:
      - kind: unit
        ref: "tests/test_alerting_emitter.py::test_sab_published_non_cat_i_refs_produce_zero_requests"
        status: pass
      - kind: unit
        ref: "tests/test_alerting_emitter.py::test_verdict_ready_non_cat_i_or_missing_cnr_produces_zero_requests_no_exception"
        status: pass
      - kind: unit
        ref: "tests/test_alerting_emitter.py::test_verdict_ready_cat_i_missing_enrichment_row_produces_zero_requests_and_warns"
        status: pass
    human_judgment: false
  - id: D4
    description: "Routing topology: sab.published binds to q.alerting as a second queue, q.notify remains first; existing topology tests unaffected"
    requirement: "ADR-003"
    verification:
      - kind: unit
        ref: "tests/test_alerting_emitter.py::test_routing_key_to_queue_binds_sab_published_to_q_alerting_second"
        status: pass
      - kind: unit
        ref: "tests/test_bus_rabbitmq.py, tests/test_bus_consume.py (full files)"
        status: pass
    human_judgment: false

duration: ~35min
completed: 2026-08-01
status: complete
---

# Phase 12 Plan 04: Dual-Trigger Dedupe/Throttle Wiring Summary

**Dual-trigger CAT I alerting now proven exactly-once via an atomic Store-backed claim: `verdict.ready` and `sab.published` both bind to `q.alerting`, and whichever fires second is collapsed before any ntfy egress, in either arrival order.**

## Performance

- **Duration:** ~35 min
- **Completed:** 2026-08-01T17:53:11Z
- **Tasks:** 2/2
- **Files modified:** 6 (2 created production, 1 modified production, 1 created test, 1 modified test, 1 shared test fixture file)

## Accomplishments
- `apps/alerting/dedupe.py`: `compute_dedupe_id(item_id, cnr_tier)` — the single sha256-truncated-to-16-hex definition of the dedupe identity (SPEC R2) — and `claim(store, ...)`, a thin no-read-before-write wrapper over `Store.claim_alert` from plan 12-02.
- `apps/alerting/emitter.py` split into `handle_verdict_ready` (CAT-I gate, reads `item_id` off the decoded event body) and `handle_sab_published` (fallback second look via `_extract_cat_i_item_ids` over `item_refs`, never reads the message header), both funneling through a shared `_emit_if_claimed` path that claims before ever reading the item/enrichment rows.
- `libs/contracts/src/contracts/_bus_rabbitmq.py`: `ROUTING_KEY_TO_QUEUE["sab.published"]` now `["q.notify", "q.alerting"]` — `q.notify` unchanged and still first, `q.alerting` appended (D-01).
- `run_consumer` registers a single shared handler for both `verdict.ready` and `sab.published` consume() calls on `q.alerting`, dispatching on the decoded event's own `"event"` field — not on which `consume()` call delivered the message, since RabbitMQ round-robins competing consumers attached to the same queue.
- 17 new tests (6 `test_alerting_dedupe.py` + 11 `test_alerting_emitter.py`) proving both trigger orders yield exactly one push, TTL re-fire after 25h (injected clock, no sleeping), non-CAT-I/missing-cnr/missing-enrichment produce zero egress with no exceptions, and a source-level check that `handle_sab_published` never indexes message headers.

## Task Commits

Each task was committed atomically:

1. **Task 1: dedupe.py — the reproducible identity and the atomic claim wrapper** - `29b486f` (feat)
2. **Task 2: Dual-trigger consumption with exactly-once egress** - `bc2e568` (feat)

**Plan metadata:** (this commit, following SUMMARY.md write)

## Files Created/Modified
- `apps/alerting/dedupe.py` - `compute_dedupe_id` + `claim`, the single dedupe-identity definition
- `apps/alerting/emitter.py` - `handle_verdict_ready`, `handle_sab_published`, `_extract_cat_i_item_ids`, `_emit_if_claimed`, `handle_trigger` (back-compat shim), `run_consumer` (dual registration)
- `libs/contracts/src/contracts/_bus_rabbitmq.py` - `sab.published` now bound to `["q.notify", "q.alerting"]`
- `tests/test_alerting_dedupe.py` - 6 tests: stability/16-char/tier-sensitivity/claim True-False-True-after-TTL/no cross-suppression
- `tests/test_alerting_emitter.py` - 11 tests: dual-trigger both orders, non-CAT-I both shapes, missing-enrichment, TTL re-fire, source check, routing-map check
- `tests/conftest.py` - extracted `stub_ntfy_server` fixture + `_RecordingHandler` from `tests/test_alerting_tracer.py`, shared with the new emitter test file

## Decisions Made
- **`compute_dedupe_id` moved into `dedupe.py`; `emitter.build_alert_payload` now imports it.** One definition of the identity in the tree, per the plan's explicit prohibition on a second sha256 call.
- **`build_alert_payload` gained optional `alert_id`/`dedupe_id` keyword params defaulting to fresh generation.** This lets the dual-trigger emit path reuse the winning `claim()` call's identity (so the payload and the stored `alert_state` row agree) while `tests/test_alerting_tracer.py`'s existing 4-positional-arg call (`build_alert_payload(item, enrichment, item_id, "I")`) keeps working byte-for-byte unchanged.
- **`handle_trigger` kept as a back-compat shim, not deleted.** `tests/test_alerting_tracer.py` — a file outside this plan's `files_modified` — calls `handle_trigger(item_id, payload, store, client)` directly with the pre-12-04 explicit-item_id shape. Rather than modify an out-of-scope test file, the shim delegates straight into the same `_emit_if_claimed` path the new handlers use, so it is now claim-gated too (correctly — a repeat `handle_trigger` call for the same item would also be suppressed) and remains a single source of truth for the emit logic.
- **`claim()` runs before any read of item/enrichment in `_emit_if_claimed`.** Matches the plan's explicit ordering: "no read of the item/enrichment happens before the claim." A CAT I `verdict.ready` for an item with no enrichment row still consumes its claim slot (logs a warning, zero egress) — this is the plan's specified order, not treated as a bug, since the alternative (peek at Store before claiming) would reintroduce a read-before-write race window.
- **`stub_ntfy_server` extracted to `tests/conftest.py`.** Matches the plan's explicit "(extract it to a shared fixture if it is not already one)" direction. `test_alerting_tracer.py`'s own local fixture of the same name was left in place unmodified — pytest resolves it locally within that file with no conflict, since fixture resolution is file-scoped before conftest.

## Deviations from Plan

None — plan executed exactly as written. The `handle_trigger` back-compat shim and the `build_alert_payload` optional-kwarg extension are both explicit consequences of the plan's own requirement that `tests/test_alerting_tracer.py` "must survive the refactor" (plan `<verification>` section) while that file sits outside `files_modified`; neither required an architectural decision (Rule 4) — they are the mechanical way to satisfy an explicit plan constraint.

## Issues Encountered
- Black reformatted `tests/test_alerting_dedupe.py` (Task 1's file) when run together with Task 2's new files — a trivial blank-line-after-docstring fix, carried into the Task 2 commit since it only surfaced once all touched files were formatted as a batch. No behavioral change; tests re-verified green after formatting.
- Initial TTL boundary test asserted suppression at exactly `now + 24h`, but `Store.claim_alert`'s documented semantics are boundary-inclusive re-fire (`fired_at <= now - ttl_seconds` re-fires, so exactly-24h-later already re-fires). Fixed the test to check suppression at `+23h` and re-fire at `+24h1s` (matching the acceptance criteria's own "24h + 1s" language) rather than changing Store semantics, which are correct per plan 12-02's contract.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Plan 12-05 (throttle wiring — volume caps across distinct items, per T-12-17's disposition note) can proceed: `claim()`/`dedupe.py` and the dual-trigger consumer are proven and available for it to build on.
- `run_consumer` now consumes both `verdict.ready` and `sab.published`; any operator restart of the `alerting` service picks up the new binding automatically via `_declare_topology()` (no manual queue surgery needed — the binding is additive, not a rename).
- `python -m pytest tests/test_alerting_tracer.py -q` reconfirmed green post-refactor (5 tests) — the tracer path from 12-01 is untouched behaviorally, just now claim-gated underneath `handle_trigger`.

---
*Phase: 12-cnr-alerting-dissemination*
*Completed: 2026-08-01*

## Self-Check: PASSED

All created/modified files verified present on disk; both task commits (`29b486f`, `bc2e568`) verified present in `git log --oneline --all`.
