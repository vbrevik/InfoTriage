# ADR-007 — RabbitMQ event bus topology

**Status.** Accepted (2026-06-27). Source: Phase 0 spike R1 (`findings/R1-VERDICT.md`,
`.planning/phases/00-concept-spike/SPIKE-FINDINGS.md`). Continues the ADR lineage in
`docs/ARCHITECTURE.md` (ADR-001..004).

---

**Context.** The app-split re-architecture (2026-06-24) decouples the microservices (ADR-006) with an
asynchronous **event bus**. RabbitMQ was the chosen transport, but no bus code existed and the
**topology** (exchanges, routing keys for the 4 event types, dead-lettering) was unproven. R1 stood up
a throwaway broker and proved the design end-to-end.

---

**Decision.** Adopt the following AMQP topology, proven GO by R1 on RabbitMQ 3.13.

- **Main exchange:** `infotriage.events` — **topic** exchange, **durable**.
- **Routing keys (4 event types):**
  - `item.ingested` → `q.triage`
  - `verdict.ready` → `q.brief`
  - `sab.published` → `q.notify`
  - `feed.unhealthy` → `q.ops`
- **Dead-letter path:** a **direct, durable** DLX `infotriage.dlx` with a durable DLQ
  `infotriage.dlq` bound on routing key `dead`. Primary queues are declared with
  `x-dead-letter-exchange = infotriage.dlx`. A consumer nacks a poison message with
  **`requeue=False`** → broker routes it to the DLQ atomically (no application coordination, no
  requeue loop — mitigation T-00-R1-01).
- **Declaration order is mandatory: DLX-first.** Declaring a primary queue with
  `x-dead-letter-exchange` **before** the DLX exists raises `406 PRECONDITION_FAILED`. Declare
  `infotriage.dlx` + `infotriage.dlq` first, then `infotriage.events` and the primary queues.
- All queues + exchanges **durable**.

**Proof (raw numbers):** publish→consume round-trip on `item.ingested` PASS; all 4 routing keys
published with publisher confirms, all broker-acked (no `NackError`/`UnroutableError`); poison
message → `infotriage.dlq` with **queue depth = 1** within a 5-second poll window.

---

**Consequences.**

- **Client library — pika API note (spike) → aio-pika (production).** R1 ran on `pika==1.4.1` with a
  single-threaded `BlockingConnection`. Publisher confirms use `confirm_delivery()` +
  exception-on-failure from `basic_publish()`; **`wait_for_confirms()` does NOT exist in pika 1.4.1**
  (it appears in stale online examples). `BlockingConnection` is unsuitable for a long-running
  service — **Phase 3 implements the bus with `aio-pika` using `connect_robust()`** (auto-reconnect)
  + async consumer callbacks.

- **M3 fan-out (multiple consumers per event) is NOT tested (A4).** Adding a second subscriber
  requires a **separate queue per subscriber** bound to the same routing key, not a shared queue.
  Architecturally straightforward but to be exercised when M3 team fan-out is built.

- The topology is fixed for Phase 3; the 4 routing keys are the contract between ingest, triage,
  brief, and notify/ops services (ADR-006).
