---
phase: 05-triage-app
plan: 02
subsystem: messaging
tags: [aio-pika, rabbitmq, llm-prompting, tdd]

requires:
  - phase: 03-bus
    provides: RabbitMQBus with publish()/subscribe() drain-only consumer, DLX/DLQ topology, _queues keyed by routing_key
provides:
  - "RabbitMQBus.consume(routing_key, handler, prefetch_count=1) — persistent callback consumer reusing existing topology"
  - "triage_score.score_item() hot-reads ccir.md per call (no module-level cache)"
affects: [05-03-worker]

tech-stack:
  added: []
  patterns:
    - "Persistent AMQP consumer as a class method sibling to drain-only subscribe(); both share self._queues keyed by routing_key"
    - "Hot-read config pattern: load config file as local var inside the function that uses it, not at module import time"

key-files:
  created:
    - tests/test_triage_score_hotread.py
    - tests/test_bus_consume.py
  modified:
    - apps/triage/triage_score.py
    - libs/contracts/src/contracts/_bus_rabbitmq.py

key-decisions:
  - "consume() added as a new sibling method on RabbitMQBus, not on the BusClient Protocol (per RESEARCH Open Question 2) — subscribe() and the Protocol are untouched"
  - "consume() does not redeclare exchanges/queues; it looks up self._queues[routing_key] from the topology _ensure_connection already declared"

patterns-established:
  - "Hot-read-per-call: any operator-tunable file (ccir.md) must be read inside the function that uses it, never cached at module load"

requirements-completed: [R2, R3]

coverage:
  - id: D1
    description: "score_item() re-reads ccir.md on every call so operator edits take effect without a restart (D-5, D-02)"
    requirement: "R3"
    verification:
      - kind: unit
        ref: "tests/test_triage_score_hotread.py#test_ccir_hot_read"
        status: pass
      - kind: unit
        ref: "tests/test_score_parse.py"
        status: pass
    human_judgment: false
  - id: D2
    description: "RabbitMQBus.consume() registers a persistent consumer on a routing key's queue and delivers a live-published message to the handler"
    requirement: "R2"
    verification:
      - kind: integration
        ref: "tests/test_bus_consume.py#test_consume_delivers_message (live RabbitMQ :22001)"
        status: pass
      - kind: integration
        ref: "tests/test_bus_consume.py#test_consume_unknown_routing_key_raises"
        status: pass
    human_judgment: false

duration: 12min
completed: 2026-06-30
status: complete
---

# Phase 05 Plan 02: RabbitMQBus.consume() + triage_score.py ccir.md hot-read Summary

**Added a persistent AMQP consumer method to RabbitMQBus and fixed triage_score.py to re-read ccir.md on every score_item() call instead of caching it at import time.**

## Performance

- **Duration:** 12 min
- **Started:** 2026-06-30T21:09:00Z (approx)
- **Completed:** 2026-06-30T21:23:00Z
- **Tasks:** 2
- **Files modified:** 4 (2 created, 2 modified)

## Accomplishments
- `RabbitMQBus.consume(routing_key, handler, prefetch_count=1)` — a persistent callback
  consumer that reuses the existing `self._queues` (keyed by routing_key) and topology
  declared by `_ensure_connection`/`_declare_topology`; raises `ValueError` for an unknown
  routing key. Verified end-to-end against live RabbitMQ on `:22001`.
- `apps/triage/triage_score.py` now reads `ccir.md` fresh inside `score_item()` (local
  `ccir = load_ccir()`), removing the module-level `CCIR = load_ccir()` cache that silently
  shadowed file edits. The f-string now interpolates `{ccir}` instead of the stale `{CCIR}`.
  `score_item()`'s public signature and the `--sample` CLI are unchanged.

## Task Commits

Each task was committed atomically (TDD: test → feat, both tasks):

1. **Task 1: triage_score.py ccir.md hot-read fix (D-02) + regression test**
   - `e049a71` (test) — add failing `test_ccir_hot_read`, confirmed it failed against the
     pre-fix module-level cache
   - `a1e05e1` (feat) — remove module-level `CCIR`, add local `ccir = load_ccir()` in
     `score_item()`, switch f-string to `{ccir}`
2. **Task 2: Add RabbitMQBus.consume() persistent consumer + live smoke test**
   - `1d3b2db` (test) — add failing `test_bus_consume.py` (`AttributeError: no attribute
     'consume'` confirmed)
   - `260d7b5` (feat) — add `async def consume(...)` to `RabbitMQBus`

**Plan metadata:** (this commit)

## Files Created/Modified
- `apps/triage/triage_score.py` - removed module-level `CCIR = load_ccir()`; `score_item()` now loads `ccir` locally as its first statement and the prompt f-string uses `{ccir}`
- `libs/contracts/src/contracts/_bus_rabbitmq.py` - added `async def consume(self, routing_key, handler, prefetch_count=1)` after `subscribe()`
- `tests/test_triage_score_hotread.py` - new regression test `test_ccir_hot_read` (monkeypatches `CCIR_PATH` + `llm`, proves two `score_item()` calls separated by a file edit see different content)
- `tests/test_bus_consume.py` - new rabbitmq-marked tests `test_consume_delivers_message` and `test_consume_unknown_routing_key_raises`

## Decisions Made
- `consume()` placed as a new method on `RabbitMQBus` only, not added to the `BusClient`
  Protocol or `InMemoryBus` — matches the plan's directive (RESEARCH Open Question 2) since
  only the live worker (05-03) needs a persistent consumer; `subscribe()`'s drain-only
  contract stays the shared cross-implementation interface.
- Reused the existing `_queues` dict (keyed by routing_key) rather than introducing a new
  lookup table — avoids any topology drift between `subscribe()` and `consume()`.

## Deviations from Plan

None — plan executed exactly as written. Both tasks followed the prescribed TDD RED→GREEN
sequence; acceptance criteria match the plan's `<acceptance_criteria>` blocks verbatim.

## Issues Encountered

None. RabbitMQ was already running and reachable on `:22001` (`infotriage-rabbitmq` container),
so the live smoke test (`tests/test_bus_consume.py -m rabbitmq`) ran without additional setup.

## User Setup Required

None - no external service configuration required (RabbitMQ container was already running).

## Next Phase Readiness

Both interfaces 05-03 (triage worker) depends on are now in place:
- `RabbitMQBus.consume()` is ready for the worker to register its `item.ingested` handler.
- `score_item()`'s hot-read means the worker can score items with operator-tunable `ccir.md`
  edits taking effect immediately, no restart.

No blockers for 05-03.

---
*Phase: 05-triage-app*
*Completed: 2026-06-30*

## Self-Check: PASSED

All created files and commit hashes verified present in working tree / git log.
