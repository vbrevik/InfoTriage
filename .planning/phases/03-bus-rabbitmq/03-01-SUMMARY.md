---
phase: 03-bus-rabbitmq
plan: "01"
subsystem: bus
tags: [rabbitmq, aio-pika, amqp, event-bus, dlx, dlq, docker]
dependency_graph:
  requires: [02-04]
  provides: [RabbitMQBus, infotriage.events exchange, 4 routing keys, DLX/DLQ]
  affects: [libs/contracts, docker-compose.yml, apps/triage, apps/ingest, apps/brief]
tech_stack:
  added: [aio-pika>=9.0, rabbitmq:3.13-management]
  patterns: [topic exchange, dead-letter exchange, publisher confirms, connect_robust auto-reconnect]
key_files:
  created:
    - libs/contracts/src/contracts/_bus_rabbitmq.py
    - tests/test_bus_rabbitmq.py
  modified:
    - docker-compose.yml
    - libs/contracts/src/contracts/__init__.py (pre-existing)
    - requirements-dev.txt (pre-existing)
    - pyproject.toml (pre-existing)
decisions:
  - aio-pika async transport over pika blocking (connect_robust auto-reconnect mandatory for services)
  - DLX infotriage.dlx declared before primary queues (prevents 406 PRECONDITION_FAILED)
  - x-dead-letter-routing-key=dead on all primary queues (routes to infotriage.dlq via DLX)
  - Topology migration handler in _rebuild_topology() deletes+recreates conflicting queues on dev
  - Each test creates own asyncio.run() + bus instance to avoid event loop sharing
metrics:
  duration: "21m"
  completed: "2026-06-29"
  tasks_completed: 7
  files_modified: 5
status: complete
---

# Phase 03 Plan 01: Bus — RabbitMQ — Summary

RabbitMQ AMQP transport for the InfoTriage event bus. aio-pika `RabbitMQBus` implementing `BusClient` Protocol with infotriage.events topic exchange, 4 routing keys, durable queues, DLX/DLQ, publisher confirms, and topology migration handler for dev environment.

## What Was Built

### Task 1: docker-compose.yml — RabbitMQ 3.13 service with healthcheck

Added healthcheck (`rabbitmq-diagnostics -q ping`) to the existing RabbitMQ service definition. The service was already present from Phase 2 scaffolding but lacked the healthcheck block required by R1 and the plan's `must_haves`.

- Port 22001 (AMQP, localhost-only) and 22002 (management UI, localhost-only)
- `rabbitmq:3.13-management` image
- Healthcheck: `CMD-SHELL rabbitmq-diagnostics -q ping` (interval 10s, timeout 5s, retries 5)
- Commit: `6134edd`

### Task 2: `_bus_rabbitmq.py` — fixed DLX/DLQ topology bugs + topology migration

The implementation existed but had three critical topology bugs preventing correct dead-lettering:

1. **DLQ bind missing routing_key="dead"** — DLQ was bound to DLX but with no routing key, making it unreachable via dead-lettering
2. **Primary queue `x-dead-letter-routing-key` set to per-queue routing key** — should be `"dead"` for all queues so dead messages route to DLQ
3. **DLQ declared with wrong arg `dead_letter_exchange`** — DLQ is the terminal destination, should have no DLX args (prevents routing loops)

Also added `_rebuild_topology()` migration handler: if `_ensure_connection()` catches a 406 PRECONDITION_FAILED (queues declared with wrong args from old code), it deletes conflicting queues and redeclares with correct args. This fired automatically on first connection after the fix.

- Queue refs stored in `_queues: dict[str, Queue]` keyed by routing key for efficient `subscribe()`
- Dedup keyed on `(routing_key, item_id)` matching `InMemoryBus` behavior
- Commit: `bbe8dc3`

### Tasks 3, 4, 5: `__init__.py`, `requirements-dev.txt`, `pyproject.toml`

Pre-existing from prior work: `RabbitMQBus` exported, `aio-pika>=9.0` in requirements, `rabbitmq` pytest marker registered. Verified only.

### Task 6: `tests/test_bus_rabbitmq.py` — comprehensive smoke tests

Replaced minimal 3-test stub with 4 end-to-end smoke tests covering all R3 acceptance criteria:

| Test | What it verifies |
|------|-----------------|
| `test_rabbitmq_available` | :22001 reachable + full topology declared (R1) |
| `test_publish_consume_roundtrip` | All 4 event types publish/consume (R3) |
| `test_dedup` | Same (routing_key, item_id) → single message in queue |
| `test_dlq_poison` | NACK requeue=False → infotriage.dlq within 5s (R2.AC4) |

Each test creates its own bus + event loop (self-contained `asyncio.run()`), purges queues for isolation, skips gracefully when :22001 unreachable.

- Commit: `4882236`

### Task 7: Full test suite — no regressions

- Existing suite: **151 tests pass** (includes Phase 2 additions; plan said 87, which was the Phase 1 count)
- New RabbitMQ suite: **4 tests pass** (all markers rabbitmq)
- Total: 155 tests green

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed DLQ bind missing routing_key**
- **Found during:** Task 2 implementation review + live testing
- **Issue:** `await self._dlq.bind(self._dlx)` was missing `routing_key="dead"` — DLQ was declared but no messages could route to it via DLX
- **Fix:** Changed to `await self._dlq.bind(self._dlx, routing_key=DLQ_ROUTING_KEY)` where `DLQ_ROUTING_KEY = "dead"`
- **Files modified:** `libs/contracts/src/contracts/_bus_rabbitmq.py`
- **Commit:** bbe8dc3

**2. [Rule 1 - Bug] Fixed primary queue x-dead-letter-routing-key**
- **Found during:** Task 2 implementation review
- **Issue:** Primary queues were declaring `"x-dead-letter-routing-key": routing_key` (e.g., "item.ingested") — dead messages would be routed with the wrong key and never reach infotriage.dlq
- **Fix:** Changed to `"x-dead-letter-routing-key": "dead"` for all primary queues
- **Files modified:** `libs/contracts/src/contracts/_bus_rabbitmq.py`
- **Commit:** bbe8dc3

**3. [Rule 1 - Bug] Fixed DLQ declaration wrong arguments**
- **Found during:** Task 2 implementation review
- **Issue:** DLQ was declared with `arguments={"dead_letter_exchange": "infotriage.dlx"}` — wrong arg name (should be `x-dead-letter-exchange`) AND DLQ shouldn't have a DLX (it's the terminal destination; adding DLX would cause routing loops)
- **Fix:** Removed arguments from DLQ declaration entirely
- **Files modified:** `libs/contracts/src/contracts/_bus_rabbitmq.py`
- **Commit:** bbe8dc3

**4. [Rule 3 - Blocking] Added topology migration handler**
- **Found during:** Task 2 — first test run failed with 406 PRECONDITION_FAILED when new code tried to re-declare queues with corrected args
- **Issue:** Existing queues in running RabbitMQ had wrong `x-dead-letter-routing-key` values; new declaration args conflicted
- **Fix:** Added `_rebuild_topology()` that catches 406, opens fresh channel, deletes conflicting queues, redeclares from scratch
- **Files modified:** `libs/contracts/src/contracts/_bus_rabbitmq.py`
- **Commit:** bbe8dc3

**5. [Rule 3 - Blocking] Redesigned tests to avoid event loop sharing**
- **Found during:** Task 6 initial implementation — tests hung/failed when `fresh_bus` fixture created bus in one `asyncio.run()` and tests used it in another
- **Issue:** aio-pika connections are bound to their event loop; cross-loop use silently fails or hangs
- **Fix:** Each test is fully self-contained with its own `asyncio.run()` and bus lifecycle. Removed session-scoped `fresh_bus` fixture in favor of `_fresh_bus()` helper function called inside each test's coroutine
- **Files modified:** `tests/test_bus_rabbitmq.py`
- **Commit:** 4882236

**6. [Note] Test count deviation: plan said 87 existing, actual is 151**
- **Found during:** Task 7
- **Issue:** Plan's "87 existing tests" reflects the Phase 1 baseline; Phase 2 added 64 more tests. The 151 count is correct for the current codebase.
- **Impact:** None — all 151 pass

## Must-Haves Verification

| Must-Have | Status | Evidence |
|-----------|--------|----------|
| R1: RabbitMQ 3.13 container on :22001/:22002, healthcheck | PASS | docker compose config verified; healthcheck in place |
| R2: aio-pika BusClient with topic exchange, 4 routing keys, DLX/DLQ | PASS | topology declared, test_rabbitmq_available verifies |
| R2: DLX declared before primary queues (prevents 406) | PASS | _declare_topology order confirmed in code + R1-VERDICT pattern |
| R2: Publisher confirms via async exchange.publish() | PASS | implicit in aio-pika — awaiting publish() blocks until broker ack |
| R2: requeue=False dead-lettering to infotriage.dlq | PASS | test_dlq_poison passes — message in DLQ within 5s |
| R3: End-to-end smoke test for all 4 event types | PASS | test_publish_consume_roundtrip: all 4 routing keys pass |

## Threat Surface Scan

| Flag | File | Description |
|------|------|-------------|
| T-03-01: DSN logging | `_bus_rabbitmq.py` | DSN stored in `self.amqp_url`; WARNING log does NOT log DSN — safe |
| T-03-03: Reconnect backoff | `_bus_rabbitmq.py` | `_ensure_connection()` uses exponential backoff min(delay*2, 30s) — T-03-03 mitigated |

No new trust boundaries introduced beyond plan's threat model.

## Self-Check

- [x] docker-compose.yml has rabbitmq service with healthcheck: `docker compose config` passes
- [x] `from contracts import RabbitMQBus; isinstance(RabbitMQBus(), BusClient)` → True
- [x] `pytest tests/test_bus_rabbitmq.py -v -m rabbitmq` → 4 passed
- [x] `pytest tests/ -q -k "not db_live and not rabbitmq"` → 151 passed (no regressions)
- [x] All commits exist: 6134edd, bbe8dc3, 4882236

## Self-Check: PASSED
