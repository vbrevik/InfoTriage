# Phase 3: Bus — RabbitMQ — Specification

**Created:** 2026-06-28
**Ambiguity score:** 0.10 (gate: ≤ 0.20)
**Requirements:** 3 locked

## Goal

RabbitMQ AMQP broker (port 22001) serves as the event bus for InfoTriage, routing the four event types (item.ingested, verdict.ready, sab.published, feed.unhealthy) through topic exchange with dead-letter queue for poison messages.

## Background

The app-split re-architecture (ADR-006, 2026-06-24) requires an event bus to decouple microservices. Phase 0 R1 proved RabbitMQ topology (infotriage.events topic exchange, 4 routing keys, DLX/DLQ) with pika 1.4.1. Phase 3 implements the production bus client with aio-pika (async, robust reconnection) behind the `libs/contracts.BusClient` Protocol. Existing in-memory bus (`libs/contracts/_bus.py`) defines the contract; Phase 3 delivers AMQP transport.

## Requirements

1. **RabbitMQ container**: AMQP service runs on port 22001, management UI on port 22002.
   - Current: No RabbitMQ container in docker-compose.yml; only in-memory bus in `libs/contracts/_bus.py`.
   - Target: RabbitMQ 3.13 container exposing ports 22001 (AMQP) and 22002 (management UI), durable exchange and queues declared.
   - Acceptance: Docker container starts, port 22001 accepts AMQP connections, management UI at `http://localhost:22002` returns HTTP 200.

2. **AMQP bus client**: `libs/contracts.BusClient` Protocol implemented via aio-pika with topic exchange, 4 routing keys, durable queues, DLX/DLQ, publisher confirms, and requeue=False dead-lettering.
   - Current: BusClient Protocol and InMemoryBus exist; no AMQP transport.
   - Target: aio-pika implementation satisfies BusClient Protocol with: (a) infotriage.events topic exchange; (b) 4 routing keys (item.ingested, verdict.ready, sab.published, feed.unhealthy); (c) 4 durable queues (q.triage, q.brief, q.notify, q.ops) bound to exchange; (d) infotriage.dlx DLX and infotriage.dlq with routing key dead; (e) `x-dead-letter-exchange=infotriage.dlx` on primary queues; (f) publisher confirms with `requeue=False` on nack.
   - Acceptance: Publish to any routing key returns without `NackError`/`UnroutableError`; consume from any queue returns expected payload; poison message (nacked with requeue=False) appears in infotriage.dlq within 5 seconds.

3. **Publish/consume round-trip smoke test**: End-to-end message flow verified for all 4 event types.
   - Current: No end-to-end test exists; in-memory implementation tested only.
   - Target: One successful publish/consume cycle per routing key (item.ingested, verdict.ready, sab.published, feed.unhealthy) using actual RabbitMQ container, not in-memory.
   - Acceptance: Script runs, all 4 events publish with confirms, all 4 events consume successfully, no exceptions thrown.

## Boundaries

**In scope:**
- RabbitMQ 3.13 container in docker-compose.yml on port 22001 (AMQP) / 22002 (management)
- aio-pika bus client implementation satisfying BusClient Protocol
- infotriage.events topic exchange with 4 routing keys
- DLX infotriage.dlx and DLQ infotriage.dlq with dead-lettering
- Publisher confirms and requeue=False dead-lettering
- Port 22000–22099 band (no conflict with Phase 2 Postgres on 22000)

**Out of scope:**
- Consumer groups or multiple subscribers per queue (M3 multi-user team server feature, deferred)
- Message encryption (Phase 7 ops hardening)
- DLQ replay mechanism (deferred beyond Phase 3)
- RabbitMQ cluster (single broker, one Mac)
- Auth/TLS (host-only localhost access, no external exposure)
- Monitoring/healthcheck integration (Phase 7)

## Constraints

- Must use aio-pika (not pika) — production service needs async with `connect_robust()` auto-reconnect
- All queues and exchanges must be durable (durable=True)
- DLX must be declared before primary queues (prevents 406 PRECONDITION_FAILED)
- Port 22001 must not conflict with Phase 2 Postgres on 22000
- BusClient Protocol interface must not change; Phase 3 only changes transport implementation

## Acceptance Criteria

- [ ] RabbitMQ 3.13 container exposes ports 22001 (AMQP) and 22002 (management UI)
- [ ] aio-pika bus client implements BusClient Protocol with infotriage.events topic exchange, 4 routing keys, durable queues, DLX/DLQ
- [ ] Publisher confirms work: publish to any routing key returns without error (no NackError/UnroutableError)
- [ ] Dead-lettering works: nacking with requeue=False routes message to infotriage.dlq within 5 seconds
- [ ] End-to-end smoke test passes: publish/consume round-trip succeeds for all 4 event types

## Ambiguity Report

| Dimension          | Score | Min  | Status |
|--------------------|-------|------|--------|
| Goal Clarity       | 0.95  | 0.75 | ✓      |
| Boundary Clarity   | 0.90  | 0.70 | ✓      |
| Constraint Clarity | 0.85  | 0.65 | ✓      |
| Acceptance Criteria| 0.85  | 0.70 | ✓      |
| **Ambiguity**      | 0.10  | ≤0.20| ✓      |

## Interview Log

| Round | Perspective | Question summary | Decision locked |
|-------|-------------|------------------|-----------------|
| 1 | Researcher | What exists in codebase? | Only BusClient Protocol + InMemoryBus; no AMQP |
| 1 | Researcher | What's the delta to Phase 3? | Full event-driven architecture with RabbitMQ |
| 2 | Simplifier | Minimum viable Phase 3? | RabbitMQ container + aio-pika client + 4 events + DLQ |
| 3 | Boundary Keeper | What's NOT Phase 3? | Multi-subscriber queues, encryption, DLQ replay, clustering |
| 4 | Failure Analyst | What fails if requirements wrong? | Missing DLX-first declaration causes 406; no requeue=False causes requeue loop |

---

*Phase: 03-bus-rabbitmq*
*Spec created: 2026-06-28*
*Next step: /gsd-discuss-phase 3 — implementation decisions (Docker configuration, aio-pika client structure)*
