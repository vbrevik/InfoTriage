---
phase: 00-concept-spike
plan: "02"
subsystem: messaging
tags: [rabbitmq, pika, amqp, dlq, dlx, topic-exchange, publisher-confirms]

requires:
  - "00-01 (spike broker on 22060/22061, pika installed)"

provides:
  - "Declared InfoTriage AMQP topology: infotriage.events (topic) + infotriage.dlx/dlq (DLX) + 4 primary queues"
  - "Proven publish→consume round-trip: service A (item.ingested) → service B (q.triage)"
  - "Proven dead-letter path: basic_nack(requeue=False) → infotriage.dlq depth=1"
  - "Publisher confirms verified for all 4 event types via pika confirm_delivery()"
  - "findings/R1-VERDICT.md: GO verdict for ADR-007"

affects:
  - "ADR-007 (RabbitMQ topology — decision input complete)"
  - "00-07-PLAN.md (closeout — R1 verdict present)"

tech-stack:
  added: []
  patterns:
    - "DLX-first declaration order: DLX exchange → DLQ queue → main exchange → primary queues (406 PRECONDITION_FAILED if reversed)"
    - "pika 1.4.1 confirm mode: channel.confirm_delivery() + basic_publish() raises NackError/UnroutableError on rejection (no wait_for_confirms())"
    - "basic_nack(requeue=False) for poison messages — atomic dead-letter routing via broker, no app-side coordination"
    - "queue_declare(passive=True).method.message_count for queue depth verification"
    - "Single BlockingConnection per process (pika thread-safety constraint)"

key-files:
  created:
    - .planning/phases/00-concept-spike/findings/R1-VERDICT.md
  ephemeral-created:
    - .spike/r1_rabbit/r1_topology.py
    - .spike/r1_rabbit/r1_publisher.py
    - .spike/r1_rabbit/r1_consumer.py

key-decisions:
  - "R1: GO — InfoTriage AMQP topology (topic exchange, 4 routing keys, DLX/DLQ) proven on RabbitMQ 3.13"
  - "pika 1.4.1 wait_for_confirms() does not exist; correct confirm pattern is confirm_delivery() + exception-on-nack from basic_publish()"
  - "Phase 3 bus must use aio-pika (connect_robust, async callbacks) not pika BlockingConnection"
  - "M3 fan-out: add queue_bind per subscriber; no exchange change needed (A4 — not tested, noted for ADR-007)"

metrics:
  duration: "~6 min"
  completed: "2026-06-25"
  tasks: 2
  files_committed: 1
  files_ephemeral: 3

status: complete
---

# Phase 00 Plan 02: R1 RabbitMQ Topology Spike Summary

**InfoTriage AMQP topology (topic exchange + DLX/DLQ) proven on pika 1.4.1: publish→consume round-trip confirmed, all 4 event-type publisher confirms pass, poison nack dead-letters to infotriage.dlq with depth=1 — R1 verdict GO.**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-06-25T07:23:39Z
- **Completed:** 2026-06-25T07:29:14Z
- **Tasks:** 2
- **Files committed:** 1 (`findings/R1-VERDICT.md`)
- **Ephemeral files created:** 3 (`.spike/r1_rabbit/r1_topology.py`, `r1_publisher.py`, `r1_consumer.py`)

## Accomplishments

### Task 1: Topology + Round-Trip (DLX-first)

The full InfoTriage AMQP topology was declared on the spike broker using the correct DLX-first
ordering required by RabbitMQ:

1. `infotriage.dlx` (direct, durable) — declared first so primary queues can reference it
2. `infotriage.dlq` (durable) — bound to `infotriage.dlx`, routing_key=`dead`
3. `infotriage.events` (topic, durable) — main event bus
4. Four primary queues (each durable, DLX-wired): `q.triage`, `q.brief`, `q.notify`, `q.ops`

The `--smoke` flag published one `item.ingested` and consumed it from `q.triage` — payload matched,
exit 0. All four event types confirmed by the broker via `channel.confirm_delivery()`.

### Task 2: Poison Test + R1 Verdict

The `--poison-test` flag published a poison-marker message to `item.ingested`, which was consumed
from `q.triage`, detected, and `basic_nack(requeue=False)` called. The broker routed the message
via `infotriage.dlx` into `infotriage.dlq`; queue depth was verified = 1 within the bounded
5-second poll window. `findings/R1-VERDICT.md` was written with a GO verdict.

## Task Commits

1. **Tasks 1 + 2** (combined — .spike/ files gitignored, no separate Task 1 commit) — `39711a0`
   - `feat(00-02): add poison-test DLQ path + R1 verdict`
   - R1-VERDICT.md created; spike scripts are ephemeral on disk only

## R1 Acceptance Results

| Acceptance Criterion | Result |
|----------------------|--------|
| DLX-first ordering in r1_topology.py | PASS — DLX exchange at step 1, primary queues at step 4 |
| --smoke round-trip item.ingested → q.triage | PASS — payload matched, exit 0 |
| All 4 event-type publisher confirms | PASS — all 4 returned without NackError/UnroutableError |
| infotriage.dlq depth=1 after --poison-test | PASS — depth=1 verified via passive declare |
| R1-VERDICT.md with go/no-go/partial line | PASS — "Verdict: GO" written |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] pika 1.4.1 does not have `channel(confirm_delivery=True)` constructor arg**
- **Found during:** Task 1 verification (`--smoke`)
- **Issue:** RESEARCH.md code examples used `conn.channel(confirm_delivery=True)` which does not
  exist in pika 1.4.1. The `BlockingConnection.channel()` method does not accept that keyword.
- **Fix:** Changed to `ch = conn.channel(); ch.confirm_delivery()` (method call on the channel).
- **Files modified:** `.spike/r1_rabbit/r1_publisher.py`, `.spike/r1_rabbit/r1_consumer.py`
- **Verification:** Publisher confirmed; --smoke passed.

**2. [Rule 1 - Bug] pika 1.4.1 does not have `wait_for_confirms()` method**
- **Found during:** Task 1 verification (`--smoke`)
- **Issue:** RESEARCH.md code examples used `ch.wait_for_confirms()` which does not exist in
  pika 1.4.1. The correct pattern is that `basic_publish()` raises on rejection and returns
  `None` on success when in confirm mode.
- **Fix:** Removed `wait_for_confirms()` calls; added comments explaining the actual API contract.
- **Files modified:** `.spike/r1_rabbit/r1_publisher.py`, `.spike/r1_rabbit/r1_consumer.py`
- **Verification:** Publisher confirmed for all 4 event types.

**3. [Rule 1 - Bug] Poison test consumed leftover non-poison message first**
- **Found during:** Task 2 verification (`--poison-test`)
- **Issue:** The `--all` publisher run left a non-consumed `item.ingested` message in `q.triage`.
  The poison-test callback stopped consuming after the first (non-poison) message, asserting 1
  nacked message when 0 had been nacked.
- **Fix:** Changed callback to ack non-poison messages and continue consuming until poison marker
  is found (with a MAX_DRAIN=20 safety cap). This makes `--poison-test` idempotent regardless
  of leftover queue state.
- **Files modified:** `.spike/r1_rabbit/r1_consumer.py`
- **Verification:** `--poison-test` passed; DLQ depth=1 confirmed.

**Total deviations:** 3 auto-fixed (Rule 1 — pika API surface mismatch from RESEARCH.md examples
+ queue state isolation bug). No behavioral changes to the intended topology or test semantics.

## Notes for ADR-007

The following findings are direct inputs to ADR-007:

- **Topology: GO** — use topic exchange `infotriage.events` with the 4 routing keys as designed.
- **DLX: GO** — `infotriage.dlx` (direct) + `infotriage.dlq` (durable) with DLX-first ordering.
- **Publisher confirms in pika 1.4.1:** use `confirm_delivery()` method + exception-on-failure pattern.
- **Phase 3 client:** use `aio-pika` (not `pika`) — `connect_robust()` for auto-reconnect, async
  consumer callbacks for long-running services.
- **M3 fan-out (assumption A4):** architecturally straightforward (additional `queue_bind` per
  subscriber), not tested in this spike. Note in ADR-007.

## Threat Surface Scan

No new network endpoints, auth paths, or schema changes introduced. All files are:
- `.spike/` (gitignored, ephemeral) — spike broker on localhost:22060/spike creds only
- `.planning/findings/` (committed, read-only docs) — no executable code

T-00-R1-01 (poison requeue loop) mitigated: `requeue=False` proven effective; DLQ depth=1 verified.
T-00-R1-02 (prod stack mutation) mitigated: spike connected exclusively to port 22060 with spike/spike creds.

## Self-Check: PASSED

- [x] `findings/R1-VERDICT.md` exists and contains "Verdict: GO"
- [x] Commit `39711a0` exists in git log
- [x] `.spike/r1_rabbit/r1_topology.py`, `r1_publisher.py`, `r1_consumer.py` exist on disk
- [x] All 3 acceptance criteria (round-trip, 4-confirms, DLQ depth=1) passed in shell output
