---
phase: 12-cnr-alerting-dissemination
plan: 06
subsystem: alerting
tags: [python, asyncio, httpx, rabbitmq, ntfy, retry, dead-letter, audit]

# Dependency graph
requires:
  - phase: 12-cnr-alerting-dissemination (plan 01)
    provides: "apps/alerting/outbox.py::NtfyClient — the single-POST delivery primitive this plan wraps"
  - phase: 12-cnr-alerting-dissemination (plan 02)
    provides: "Store.mark_alert_outcome / Store.audit_write — the durable outcome-recording surface this plan calls"
  - phase: 12-cnr-alerting-dissemination (plan 04)
    provides: "emitter.py's _emit_if_claimed shared emit path — the single call site this plan rewires"
  - phase: 12-cnr-alerting-dissemination (plan 05)
    provides: "the throttle-gated egress point deliver_with_retry now sits behind"
provides:
  - "libs/contracts/src/contracts/_bus_rabbitmq.py: ROUTING_KEY_TO_QUEUE['outbox.dlx'] -> ['outbox.dlx.queue'] — a dedicated alerting dead-letter destination, distinct from infotriage.dlq"
  - "apps/alerting/outbox.py: RETRY_SCHEDULE (1, 5), DLX_ROUTING_KEY, deliver_with_retry(client, store, bus, payload, *, item_id, item_title='') — 3 total attempts on the SPEC R4 schedule"
  - "apps/alerting/outbox.py: dead_letter(store, bus, payload, *, item_id, reason, attempts) — publish to outbox.dlx, write an alert_dead_lettered audit row, stamp dlx_at, in that order"
  - "apps/alerting/emitter.py: the shared emit path's single delivery call site now goes through deliver_with_retry; bus threaded as an optional kwarg through the whole handler chain"
affects: [12-09]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Fixed-schedule in-process retry as data, not a dependency: RETRY_SCHEDULE = (1, 5) is a two-element tuple constant, not a pip backoff library — SPEC R4 locks the exact schedule, so a generic retry package would be unjustified surface for a fixed two-step sequence (RESEARCH Don't Hand-Roll)."
    - "Ack-after-record: the durable outcome (delivered_at or dlx_at, plus the DLX publish and audit row on the failure path) is written and awaited to completion INSIDE deliver_with_retry/dead_letter, before that coroutine returns — so the caller's message.process() context has not yet acked when a crash could occur. This is the entire mechanism behind the total-outage no-loss guarantee; no local spool exists because none is needed."
    - "Dedicated alerting DLX, not the project-wide one: outbox.dlx.queue is declared as its own ROUTING_KEY_TO_QUEUE entry via the existing declare-and-bind loop, so alerting terminal failures are never mixed into infotriage.dlq's unrelated poison messages."
    - "Optional-bus threading for backward compatibility: _emit_if_claimed/handle_verdict_ready/handle_sab_published/handle_trigger all gained a bus=None keyword-only parameter rather than a new required positional — every pre-12-06 direct test caller keeps calling with its original 3/4-positional-arg shape, and bus is only ever dereferenced on the delivery-exhaustion path those callers' stub servers never trigger."

key-files:
  created:
    - tests/test_alerting_outbox.py
  modified:
    - libs/contracts/src/contracts/_bus_rabbitmq.py
    - apps/alerting/outbox.py
    - apps/alerting/emitter.py
    - apps/alerting/alerting_worker.py

key-decisions:
  - "deliver_with_retry catches (httpx.HTTPStatusError, httpx.RequestError) identically — a non-2xx response and a transport-level connection error (e.g. httpx.ConnectError) both count as one failed attempt on the same 3-attempt/1s-5s schedule, matching the plan's Test 5 requirement without a separate code path."
  - "item_title threaded as an additional optional keyword-only parameter on deliver_with_retry (not in the plan's literal signature list) — required to preserve the X-Title header behavior locked by the 12-01 checkpoint (item's own title, not sab_excerpt); omitting it would have been a silent regression."
  - "bus is a keyword-only parameter defaulting to None across the emitter.py handler chain, not a new required positional — this is what let tests/test_alerting_tracer.py's 4-positional-arg handle_trigger(...) call and tests/test_alerting_emitter.py's/test_alerting_throttle.py's 3-positional-arg handle_verdict_ready(...)/handle_sab_published(...) calls keep passing unmodified, since none of their stub-server scenarios ever reach the delivery-exhaustion branch that would dereference bus."
  - "alerting_worker.py needed no new construction-time wiring: run_consumer(bus, store, client) already received all three objects (unchanged since 12-01/12-04); only its module docstring's now-stale 'No retry/DLX yet — later expansion plan' line was corrected to describe the wiring that already reaches deliver_with_retry through the existing call chain."
  - "Process note (not a plan deviation): Task 2's implementation was drafted before its RED test, which would have made the RED gate trivially pass. Self-caught before any commit — recovered by capturing the draft implementation as a patch, reverting the three production files, confirming tests/test_alerting_outbox.py genuinely fails (ImportError) against pre-implementation code, committing that as the RED commit, then reapplying the captured implementation for the GREEN commit. Net result matches the mandated RED-then-GREEN sequence."

requirements-completed: [ADR-003]

coverage:
  - id: D1
    description: "A dedicated outbox.dlx -> outbox.dlx.queue destination exists in the bus topology, distinct from the project-wide infotriage.dlq, declared via the existing declare-and-bind loop with no new exchange or TTL/wait-queue chain"
    requirement: "ADR-003"
    verification:
      - kind: unit
        ref: "tests/test_bus_rabbitmq.py (full suite, unaffected by the new entry)"
        status: pass
      - kind: unit
        ref: "tests/test_bus_consume.py (full suite, unaffected by the new entry)"
        status: pass
      - kind: other
        ref: "python -c \"from contracts._bus_rabbitmq import ROUTING_KEY_TO_QUEUE; assert ROUTING_KEY_TO_QUEUE['outbox.dlx'] == ['outbox.dlx.queue']\""
        status: pass
    human_judgment: false
  - id: D2
    description: "A dead ntfy produces exactly 3 attempts on the 1s-then-5s locked schedule (both non-2xx and connection-error failures), then dead-letters with the full payload plus reason/attempt-count reconstructable from the queue alone"
    requirement: "ADR-003"
    verification:
      - kind: unit
        ref: "tests/test_alerting_outbox.py::test_always_500_yields_three_posts_one_dead_letter_one_audit_row"
        status: pass
      - kind: unit
        ref: "tests/test_alerting_outbox.py::test_retry_schedule_sleeps_one_then_five_only"
        status: pass
      - kind: unit
        ref: "tests/test_alerting_outbox.py::test_connection_error_on_every_attempt_dead_letters_like_always_500"
        status: pass
      - kind: unit
        ref: "tests/test_alerting_outbox.py::test_dead_letter_body_carries_full_payload_plus_reason_and_attempts"
        status: pass
    human_judgment: false
  - id: D3
    description: "A terminal failure writes exactly one audit row (op alert_dead_lettered, details carrying alert_id/dedupe_id/attempts) and one alert-state row update (dlx_at set, delivered_at not set) — no alert disappears silently"
    requirement: "ADR-003"
    verification:
      - kind: unit
        ref: "tests/test_alerting_outbox.py::test_dead_letter_audit_row_op_and_details"
        status: pass
      - kind: unit
        ref: "tests/test_alerting_outbox.py::test_always_500_yields_three_posts_one_dead_letter_one_audit_row"
        status: pass
    human_judgment: false
  - id: D4
    description: "A transient failure that succeeds on retry produces exactly one delivered outcome and zero dead-letter messages"
    requirement: "ADR-003"
    verification:
      - kind: unit
        ref: "tests/test_alerting_outbox.py::test_first_attempt_success_yields_one_post_and_delivered_outcome"
        status: pass
      - kind: unit
        ref: "tests/test_alerting_outbox.py::test_500_then_200_yields_two_posts_delivered_zero_dead_letters"
        status: pass
    human_judgment: false
  - id: D5
    description: "The trigger message is acked only after the outcome is durably recorded — a failure to record the outcome propagates rather than being swallowed, so a crash mid-flight leaves the message unacked for broker redelivery"
    requirement: "ADR-003"
    verification:
      - kind: unit
        ref: "tests/test_alerting_outbox.py::test_ack_after_record_propagates_on_outcome_recording_failure"
        status: pass
      - kind: integration
        ref: "tests/test_alerting_outbox.py::test_ack_after_record_propagates_via_emit_path_not_swallowed"
        status: pass
    human_judgment: false
  - id: D6
    description: "Pre-12-06 direct callers of the emitter handler chain (tracer/emitter/throttle test suites) keep working unchanged after deliver_with_retry replaces the bare single-attempt POST"
    requirement: "ADR-003"
    verification:
      - kind: unit
        ref: "tests/test_alerting_tracer.py (full suite)"
        status: pass
      - kind: unit
        ref: "tests/test_alerting_emitter.py (full suite)"
        status: pass
      - kind: unit
        ref: "tests/test_alerting_throttle.py (full suite)"
        status: pass
      - kind: other
        ref: "make -f ops/Makefile test-safe (full project suite, throwaway Postgres port 22062)"
        status: pass
    human_judgment: false

duration: ~35min
completed: 2026-08-02
status: complete
---

# Phase 12 Plan 06: Outbox retry-then-dead-letter with an audit trail Summary

**apps/alerting/outbox.py now retries a failed ntfy push on the SPEC R4-locked 1s/5s schedule (3 attempts total), then durably dead-letters to a dedicated outbox.dlx.queue with an audit row before the trigger message is ever acked — closing the last silent-loss window in the egress path.**

## Performance

- **Duration:** ~35 min
- **Completed:** 2026-08-02T15:20:00Z
- **Tasks:** 2/2 completed
- **Files modified:** 5 (1 modified in libs/contracts, 3 modified in apps/alerting, 1 test file created)

## Accomplishments

- `libs/contracts/src/contracts/_bus_rabbitmq.py`'s `ROUTING_KEY_TO_QUEUE` gained
  `"outbox.dlx": ["outbox.dlx.queue"]`, reusing `_declare_topology`'s existing
  declare-and-bind loop wholesale — no new exchange, no TTL/wait-queue chain. Deliberately
  a queue distinct from the project-wide `infotriage.dlq`, per SPEC R4 and the RESEARCH
  anti-pattern note that burying alerting failures among unrelated poison messages is a
  failure nobody finds.
- `apps/alerting/outbox.py` gained `RETRY_SCHEDULE = (1, 5)` (data, not a pip backoff
  dependency), `DLX_ROUTING_KEY = "outbox.dlx"`, `deliver_with_retry(client, store, bus,
  payload, *, item_id, item_title="")` (3 total attempts: initial + 1s + 5s, treating a
  non-2xx response and a transport-level connection error identically), and
  `dead_letter(store, bus, payload, *, item_id, reason, attempts)` (publish the full
  payload plus reason/attempts to `outbox.dlx` → write an `alert_dead_lettered` audit row
  → stamp `dlx_at` on the alert-state row, in that order, all durably awaited before
  returning).
- `apps/alerting/emitter.py`'s single delivery call site in `_emit_if_claimed` now goes
  through `deliver_with_retry` instead of the bare single-attempt POST. `bus` is threaded
  as an optional (`None`-default) keyword-only parameter through
  `handle_verdict_ready`/`handle_sab_published`/`handle_trigger`/`_emit_if_claimed`, and
  `run_consumer`'s handler now passes its own `bus` through — every pre-12-06 direct test
  caller kept working unchanged, since none of them exercise the delivery-exhaustion path
  that would dereference a `None` bus.
- `apps/alerting/alerting_worker.py`'s module docstring corrected — the stale "No
  retry/DLX yet — that is a later expansion plan" line is now inaccurate and was removed;
  `run_consumer(bus, store, client)` already threaded `store` and `bus` all the way to the
  new call site, so no runtime construction change was needed.
- `tests/test_alerting_outbox.py` — 9 new tests: a configurable stub ntfy server whose
  response-code sequence each test controls, a real-ECONNREFUSED dead-port URL for the
  connection-error case, a `FakeBus` recording every publish, `InMemoryStore`, and a patched
  `outbox.asyncio.sleep` asserting the exact `[1, 5]` delay sequence.

## Task Commits

Each task was committed atomically:

1. **Task 1: Declare the alerting dead-letter destination in the bus topology** - `768ba68` (feat)
2. **Task 2 RED: failing tests for retry-then-dead-letter delivery** - `d17019a` (test)
2. **Task 2 GREEN: retry-then-dead-letter delivery with an audit trail** - `2bdc4ac` (feat)

**Plan metadata:** (this commit)

## Files Created/Modified

- `libs/contracts/src/contracts/_bus_rabbitmq.py` - `ROUTING_KEY_TO_QUEUE["outbox.dlx"]` entry + rationale comment
- `apps/alerting/outbox.py` - `RETRY_SCHEDULE`, `DLX_ROUTING_KEY`, `deliver_with_retry`, `dead_letter`
- `apps/alerting/emitter.py` - single delivery call site rewired to `deliver_with_retry`; `bus` threaded through the handler chain
- `apps/alerting/alerting_worker.py` - module docstring correction only (no runtime wiring change needed)
- `tests/test_alerting_outbox.py` - new file, 9 tests

## Decisions Made

- **Both failure classes retried identically.** `deliver_with_retry` catches
  `(httpx.HTTPStatusError, httpx.RequestError)` in the same `except` clause — a non-2xx
  response and any transport-level connection error (including `httpx.ConnectError`) are
  indistinguishable failures on the same schedule, matching the plan's explicit Test 5
  requirement without a separate code path.
- **`item_title` added as an extra optional keyword param**, beyond the plan's literal
  `deliver_with_retry(client, store, bus, payload, *, item_id)` signature text — required
  to preserve the 12-01-checkpoint-verified `X-Title` behavior (the item's own title, not
  `sab_excerpt`); dropping it silently would have regressed a previously human-verified
  behavior.
- **`bus` is keyword-only with a `None` default**, not a new required positional, across
  the whole `emitter.py` handler chain — the mechanism that kept every pre-12-06 direct
  test caller (`test_alerting_tracer.py`'s 4-positional `handle_trigger(...)`,
  `test_alerting_emitter.py`'s/`test_alerting_throttle.py`'s 3-positional
  `handle_verdict_ready(...)`/`handle_sab_published(...)`) passing unmodified.
- **No construction-time change needed in `alerting_worker.py`.** `run_consumer(bus,
  store, client)` already received all three objects since 12-01/12-04; the plan's "pass
  the Store and the bus into the outbox at construction" language is satisfied by that
  pre-existing wiring — only the module docstring needed correcting to stop describing
  retry/DLX as unbuilt.

## Deviations from Plan

### Auto-fixed Issues

**1. [Process self-correction, not a Rule 1-4 deviation] TDD execution order corrected before any commit**
- **Found during:** Task 2, before committing anything
- **Issue:** The `deliver_with_retry`/`dead_letter` implementation was drafted in
  `apps/alerting/outbox.py`/`emitter.py`/`alerting_worker.py` before `tests/test_alerting_outbox.py`
  was written, which would have made the mandated RED gate trivially pass against
  already-correct code rather than genuinely failing first.
- **Fix:** Captured the draft implementation as a patch (`git diff` on the three files),
  reverted them (`git checkout --`), wrote and ran `tests/test_alerting_outbox.py` against
  the pre-implementation code to confirm a genuine `ImportError` failure, committed that as
  the RED commit, then reapplied the captured implementation (`git apply`) for the GREEN
  commit. End state matches the mandated RED-then-GREEN sequence; no test or plan content
  was affected by the reordering.
- **Files modified:** none beyond the plan's own `files_modified` list — this was a commit
  ordering correction, not a code change.
- **Verification:** `python -m pytest tests/test_alerting_outbox.py -x -q` failed with
  `ImportError: cannot import name 'DLX_ROUTING_KEY' from 'outbox'` before the GREEN patch
  was reapplied; passed 9/9 after.
- **Committed in:** `d17019a` (RED), `2bdc4ac` (GREEN)

---

**Total deviations:** 0 Rule 1-4 auto-fixes; 1 process self-correction (TDD ordering), documented above.
**Impact on plan:** None on shipped behavior — the plan's design (retry schedule, dead-letter
ordering, audit fields, back-compat threading) was implemented exactly as specified. No scope
creep.

## Issues Encountered

None beyond the process self-correction documented above.

## User Setup Required

None — no external service configuration required. This plan only extends the existing
`outbox.py`/`emitter.py`/`_bus_rabbitmq.py` modules and the already-provisioned RabbitMQ/ntfy
services from 12-01/12-03.

## Next Phase Readiness

- The egress path is now lossless end to end: dedupe (12-04) → throttle/digest (12-05) →
  retry-then-dead-letter (this plan). Every terminal failure lands on `outbox.dlx.queue` with
  an audit row and a stamped alert-state row; every crash before that point leaves the trigger
  message unacked for broker redelivery.
- **Phase 12 Plan 09** (prohibitions P1-P5 structural guards, AC8 isolation, ADR-015
  reconciliation, operator UAT) is the last open plan per the phase's 5-wave map, and depends
  on this plan per the wave ordering (W5 blocked on W4, now unblocked).
- `apps/alerting/outbox.py`'s strict-ASCII `X-Title` header handling (flagged as a latent gap
  since 12-01, reconfirmed in 12-05's SUMMARY) is still unaddressed — this plan's own
  `deliver_with_retry` inherits the same `NtfyClient.deliver` header path and does not change
  it; a real alert title containing non-ASCII characters would still need whichever future
  plan owns `outbox.py` to fix it. Not fixed here (out of this plan's `files_modified` scope
  and no `<behavior>`/acceptance criterion named it).

## Self-Check: PASSED

All created/modified files confirmed present on disk (`libs/contracts/src/contracts/_bus_rabbitmq.py`,
`apps/alerting/outbox.py`, `apps/alerting/emitter.py`, `apps/alerting/alerting_worker.py`,
`tests/test_alerting_outbox.py`, this SUMMARY). All three task commits (`768ba68`, `d17019a`,
`2bdc4ac`) confirmed present in `git log --oneline --all`.

---
*Phase: 12-cnr-alerting-dissemination*
*Completed: 2026-08-02*
