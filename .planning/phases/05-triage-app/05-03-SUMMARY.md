---
phase: 05-triage-app
plan: 03
subsystem: triage-worker
tags: [asyncio, aio-pika, pgvector, mE5-large, qwen36, event-driven]

requires:
  - phase: 05-01
    provides: put_enrichment/get_enrichment/put_embedding/find_near_duplicate on Store Protocol, PostgresStore, InMemoryStore
  - phase: 05-02
    provides: RabbitMQBus.consume(routing_key, handler, prefetch_count=1); triage_score.score_item() ccir.md hot-read
provides:
  - "apps/triage/worker.py — D-01 entry point: consumes item.ingested, dedups via mE5-large embeddings, scores against ccir.md, persists enrichment, publishes verdict.ready"
  - "process_item() async testable core (item_id, store, bus, *, embed, score) — injectable callables, no live infra needed for unit tests"
  - "stdlib /health liveness server (D-04) running alongside the consumer under asyncio.gather (D-03)"
affects: [05-04, 05-05]

tech-stack:
  added: []
  patterns:
    - "asyncio.to_thread per blocking call (store I/O, embedding HTTP, LLM HTTP) inside an async core, rather than wrapping the whole core in one to_thread call — keeps bus.publish() on the calling event loop (avoids aio-pika cross-event-loop object reuse) while still freeing the health server's loop during a long LLM call"
    - "raw vocabulary stored, mapped vocabulary published: enrichment rows keep score_item's raw cnr (none|I|II) / bucket (read|maybe|skip); map_cnr/map_bucket convert only at VerdictReady construction time"
    - "dedup-before-scoring: embed() and find_near_duplicate() always run; score() is skipped entirely on a dedup hit, but put_embedding() still runs for every processed item (duplicates and originals alike)"

key-files:
  created:
    - tests/test_triage_worker.py
    - tests/test_triage_health.py
  modified:
    - apps/triage/worker.py

key-decisions:
  - "process_item() is async (not sync-run-via-to_thread-as-a-whole) so bus.publish() always executes on the same event loop that owns the RabbitMQBus's aio-pika connection/channel objects — calling aio-pika methods from a different event loop (e.g. one created via asyncio.run() inside a worker thread) breaks aio-pika's internal loop-bound Futures/Locks. Each blocking call inside process_item (get_item, embed, find_near_duplicate, score, put_enrichment, put_embedding) is individually wrapped in asyncio.to_thread instead, which keeps the health server's loop responsive without ever touching bus.publish from the wrong loop."
  - "run_health_server's connection handler was extracted to a module-level _handle_health(reader, writer) coroutine (not nested) so the test can drive it directly via asyncio.start_server(_handle_health, ...) on an ephemeral port, matching the 05-PATTERNS.md health-server test pattern exactly"
  - "Task 3's run_health_server implementation was written during Task 2 (it was simple enough to do alongside main()'s asyncio.gather wiring) — Task 3 then added only the test plus the _handle_health extraction for testability. See Deviations below."

patterns-established:
  - "Pattern: async core with per-call asyncio.to_thread, not a single outer to_thread wrapper, when the core also needs to call an async bus/transport object — avoids event-loop affinity bugs with aio-pika (or any asyncio-native transport)"

requirements-completed: [R2, R3, R4, R5, R7, ADR-004, ccir.md]

coverage:
  - id: D1
    description: "Worker consumes item.ingested, reads the article via store.get_item, scores it, writes enrichment, and publishes verdict.ready"
    requirement: "R2"
    verification:
      - kind: unit
        ref: "tests/test_triage_worker.py#test_verdict_ready_fields"
        status: pass
      - kind: unit
        ref: "tests/test_triage_worker.py#test_dedup_distinct"
        status: pass
    human_judgment: false
  - id: D2
    description: "A missing article (get_item returns None) is logged and acked — does not crash the worker"
    requirement: "R2"
    verification:
      - kind: unit
        ref: "tests/test_triage_worker.py#test_missing_article_acks"
        status: pass
    human_judgment: false
  - id: D3
    description: "If store.put_enrichment raises, the exception propagates (message nacked, not acked) and no verdict.ready is published"
    requirement: "R2"
    verification:
      - kind: unit
        ref: "tests/test_triage_worker.py#test_enrichment_failure_nacks"
        status: pass
      - kind: unit
        ref: "tests/test_triage_worker.py#test_no_verdict_on_enrichment_failure"
        status: pass
    human_judgment: false
  - id: D4
    description: "Malformed LLM output produces a fallback enrichment row (ccir=none, cnr=Routine via mapping, score=0, bucket=skip) — never a crash"
    requirement: "R3"
    verification:
      - kind: unit
        ref: "tests/test_triage_worker.py#test_malformed_llm_fallback"
        status: pass
    human_judgment: false
  - id: D5
    description: "score is clamped to 0..10 before put_enrichment so the CHECK constraint never rejects a stored verdict"
    requirement: "R3"
    verification:
      - kind: unit
        ref: "tests/test_triage_worker.py#test_score_clamped"
        status: pass
    human_judgment: false
  - id: D6
    description: "Before LLM scoring the worker computes a mE5-large embedding and, on a >= threshold cosine match, marks bucket=skip with why containing 'duplicate' and makes NO LLM call; an embedding is still written for every processed article"
    requirement: "R4"
    verification:
      - kind: unit
        ref: "tests/test_triage_worker.py#test_dedup_skip"
        status: pass
    human_judgment: false
  - id: D7
    description: "verdict.ready carries item_id, ccir, cnr (I|II|Routine), score (0-10), bucket (keep|maybe|skip), why, ts; cnr 'none' maps to 'Routine' and bucket 'read' maps to 'keep'"
    requirement: "R5"
    verification:
      - kind: unit
        ref: "tests/test_triage_worker.py#test_verdict_ready_fields"
        status: pass
    human_judgment: false
  - id: D8
    description: "GET /health returns 200 (liveness only); health server logic is testable independent of run_health_server's binding"
    requirement: "R7"
    verification:
      - kind: unit
        ref: "tests/test_triage_health.py#test_health_200"
        status: pass
    human_judgment: false
  - id: D9
    description: "BACKSTOP: two consumers racing on q.triage are serialized by prefetch_count=1; an LLM/embedding timeout falls back rather than poison-looping forever — both require held-out/live infra, not unit-testable here"
    requirement: "R2/R3 concurrency edges"
    verification: []
    human_judgment: true
    rationale: "Plan explicitly flags these as BACKSTOP items needing a held-out test against live RabbitMQ/oMLX — out of scope for this plan's InMemoryStore/fake-bus unit tests. T-05-05 in the threat model accepts this risk for the single-worker M1 deployment."

duration: 22min
completed: 2026-06-30
status: complete
---

# Phase 5 Plan 03: Triage Worker (apps/triage/worker.py) Summary

**Event-driven worker.py: item.ingested -> mE5-large dedup -> qwen3.6/80b score_item() against ccir.md -> enrichment persist -> verdict.ready, with a stdlib /health liveness server running alongside the consumer**

## Performance

- **Duration:** 22 min
- **Started:** 2026-06-30T21:18:00Z (approx)
- **Completed:** 2026-06-30T21:40:00Z
- **Tasks:** 3 completed
- **Files modified:** 3 (2 created, 1 created-then-modified)

## Accomplishments
- `apps/triage/worker.py` — the full D-01 entry point: `get_embedding` (oMLX/Spark `/embeddings`, mirrors `triage_score.llm()`'s env-var pattern, ADR-004 compliant — no cloud host), `map_cnr`/`map_bucket` (raw score_item vocabulary -> VerdictReady vocabulary), `clamp_score` (safe coercion to `[0,10]`), `process_item` (the async testable core), `on_message` (RabbitMQ ack/nack wiring), `run_consumer` (persistent `prefetch_count=1` consumer), `_handle_health`/`run_health_server` (D-04 liveness server), `main()` (D-03 `asyncio.gather` under `asyncio.run`).
- `process_item`: get_item -> build `title + " " + summary[:512]` text -> embed -> `find_near_duplicate` -> on a dedup hit, skip the LLM entirely and write a `bucket=skip`/`why="duplicate of <id>"` enrichment row; otherwise call `score_item()`, clamp its score, and write the raw-vocabulary enrichment row -> `put_embedding` (always, dup or not) -> construct `VerdictReady` (mapped vocabulary) -> `await bus.publish("verdict.ready", ...)`. Enrichment write happens before publish in every code path; an enrichment-write failure propagates the exception with zero publishes.
- 9/9 new tests green (`tests/test_triage_worker.py` x8, `tests/test_triage_health.py` x1); 219 tests green project-wide (no regressions).

## Task Commits

Each task was committed atomically (TDD: test -> feat, with a follow-on test for the already-implemented health server):

1. **Task 1: Write failing worker behavior tests (R2, R3, R4, R5)** - `519ea87` (test) — RED: `ModuleNotFoundError: No module named 'worker'`
2. **Task 2: Implement worker.py core (consumer, dedup, scoring, enrichment, publish)** - `30d1baa` (feat) — GREEN: 8/8 tests pass
3. **Task 3: Add stdlib /health server (D-04) + health test (R7)** - `db3d714` (test) — extracted `_handle_health` for testability + added `test_health_200`; 9/9 pass

## Files Created/Modified
- `apps/triage/worker.py` - full worker entry point: embedding call, vocabulary mappers, score clamp, async `process_item` core, `on_message`/`run_consumer` RabbitMQ wiring, `_handle_health`/`run_health_server` liveness server, `main()`
- `tests/test_triage_worker.py` - 8 behavior tests against `InMemoryStore` + a fake async bus, no live infra
- `tests/test_triage_health.py` - 1 test driving `_handle_health` directly via `asyncio.start_server` on an ephemeral port

## Decisions Made
- **process_item is async with per-call `asyncio.to_thread`, not a sync function run as a whole via `asyncio.to_thread`.** The plan's task action text described `on_message` running "the blocking pipeline (process_item) via asyncio.to_thread," which read literally would make `process_item` a plain sync function called once via `asyncio.to_thread` from `on_message`. That design breaks in production: `bus.publish()` on `RabbitMQBus` is an aio-pika call, and aio-pika's connection/channel objects are bound to the event loop they were created on (in `run_consumer`'s loop). Running the entire pipeline — including the publish — inside a worker thread would require either calling the async `bus.publish` from a non-owning thread (impossible without its own event loop) or spinning up a fresh `asyncio.run()` inside that thread, which creates a *second* event loop and would raise on any aio-pika object accessed from across loops. Instead, `process_item` stays async, runs on the consumer's existing event loop, and wraps each individual blocking call (`store.get_item`, `embed`, `store.find_near_duplicate`, `score`, `store.put_enrichment`, `store.put_embedding`) in its own `asyncio.to_thread`. This achieves the plan's actual intent (R7: the health server's loop is never starved during a long LLM/embedding call) without the cross-event-loop correctness bug, and keeps `process_item` directly callable as a plain coroutine in tests (`asyncio.run(process_item(...))`) — matching how the existing `tests/test_bus_consume.py` already drives async code in this codebase (no `pytest-asyncio` marker dependency added).
- **`_handle_health` extracted to module level instead of nested inside `run_health_server`.** 05-PATTERNS.md's example test calls `asyncio.start_server(handle, "127.0.0.1", 0)` directly with the handler function — that's only possible if the handler is importable. Extracting it changes nothing about `run_health_server`'s external behavior (still binds host/port, still serves forever, still liveness-only).
- Enrichment rows always store the *raw* `score_item` vocabulary (`cnr` in `none|I|II`, `bucket` in `read|maybe|skip`); `map_cnr`/`map_bucket` run only when constructing the `VerdictReady` payload — matches the plan's `key_links` note about Phase 5 plan 05's shadow-run needing the raw buckets for equality checks.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] process_item built as a per-call-threaded async function instead of a sync-function-run-via-to_thread**
- **Found during:** Task 2 (worker.py core implementation)
- **Issue:** A literal reading of the plan's `on_message` description ("run the blocking pipeline (process_item) via asyncio.to_thread") would make `process_item` synchronous and have `on_message` call it as `await asyncio.to_thread(process_item, ...)`. Since `process_item` must also call `await bus.publish(...)` (an aio-pika coroutine bound to the consumer's event loop), running the whole function inside a separate `asyncio.to_thread` worker thread would force calling that aio-pika coroutine from a different event loop than the one its connection/channel objects were created on — a real correctness bug that would surface only against live RabbitMQ (not against the unit tests' fake bus, which has no loop-affinity).
- **Fix:** Made `process_item` an async function that runs on the calling (consumer) event loop directly, with each individual blocking step wrapped in its own `asyncio.to_thread` call. `bus.publish()` is awaited normally, on the correct loop. `on_message` simply `await`s `process_item(...)` inside `async with message.process():`.
- **Files modified:** `apps/triage/worker.py`
- **Verification:** All 8 `test_triage_worker.py` tests pass with this design (tests call `process_item` via plain `asyncio.run(process_item(...))`, exercising the exact same code path the live consumer uses); the design avoids a class of cross-event-loop bug that unit tests alone could not have caught since the fake bus has no event-loop affinity.
- **Committed in:** `30d1baa` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug-prevention / architectural-correctness fix, applied during initial implementation rather than discovered post-hoc)
**Impact on plan:** The deviation only affects internal threading structure, not the public `process_item(item_id, store, bus, *, embed, score)` signature, the enrichment-before-publish ordering, or any of the plan's `must_haves`. All acceptance criteria for Tasks 1-3 are met. No scope creep.

## Issues Encountered
None. `rtk` (the project's local CLI proxy) summarizes pytest output to a one-line pass/fail count by default; full tracebacks were retrieved from `~/Library/Application Support/rtk/tee/*.log` when confirming the RED state in Task 1.

## User Setup Required
None - no external service configuration required. Worker requires `INFOTRIAGE_PG_DSN`, `INFOTRIAGE_BLOB_ROOT`, `INFOTRIAGE_AMQP_DSN`, and the existing `LLM_BASE_URL`/`LLM_API_KEY`/`LLM_MODEL` env vars at runtime (container wiring is plan 05-04's scope, not this plan's `files_modified`).

## Next Phase Readiness
- `apps/triage/worker.py` is feature-complete per this plan's `must_haves`: consumes `item.ingested`, dedups, scores, persists enrichment, publishes `verdict.ready`, and serves `/health`.
- Plan 05-04 (Dockerfile/requirements.txt/docker-compose wiring, per 05-PATTERNS.md) can now containerize this worker — `worker.py`'s `main()` already assumes the env vars that plan will wire via `docker-compose.yml`.
- Plan 05-05 (shadow-run comparison script) can rely on enrichment rows holding the *raw* `score_item` vocabulary (not the mapped `VerdictReady` vocabulary) for equality checks against re-scored items.
- BACKSTOP items (T-05-05: prefetch_count=1 concurrency serialization; LLM/embedding timeout fallback) remain unverified against live infra — flagged as `human_judgment: true` in this summary's coverage block, consistent with the plan's own "needs held-out test" framing.

---
*Phase: 05-triage-app*
*Completed: 2026-06-30*
