# R1 Verdict — RabbitMQ Topology Spike

**Verdict: GO**

**Date:** 2026-06-25
**ADR input:** ADR-007 (RabbitMQ event bus topology)

---

## Verdict Summary

The InfoTriage AMQP topology was proven end-to-end on the spike broker (localhost:22060, pika 1.4.1).
All three acceptance legs passed:

1. **Round-trip (publish → consume):** a message published by service A on routing key
   `item.ingested` was consumed by service B from queue `q.triage` with correct payload.
2. **4-event-type confirms:** all four event types (`item.ingested`, `verdict.ready`,
   `sab.published`, `feed.unhealthy`) were published with publisher confirms (pika
   `confirm_delivery()` + `basic_publish()` in confirm mode); all were broker-acked without
   `NackError` or `UnroutableError`.
3. **Dead-letter queue:** a poison-marker message nacked with `requeue=False` was routed via
   `infotriage.dlx` (routing key `dead`) into `infotriage.dlq`; queue depth confirmed = 1
   within the bounded 5-second poll window.

---

## Observed Facts

### Topology declared (DLX-first order confirmed)

| Order | Resource | Type | Notes |
|-------|----------|------|-------|
| 1 | `infotriage.dlx` | exchange (direct, durable) | Declared before any primary queue references it |
| 2 | `infotriage.dlq` | queue (durable) | Bound to `infotriage.dlx`, routing_key=`dead` |
| 3 | `infotriage.events` | exchange (topic, durable) | Main event bus |
| 4 | `q.triage` | queue (durable, DLX-wired) | Bound to `infotriage.events`, rk=`item.ingested` |
| 4 | `q.brief` | queue (durable, DLX-wired) | Bound to `infotriage.events`, rk=`verdict.ready` |
| 4 | `q.notify` | queue (durable, DLX-wired) | Bound to `infotriage.events`, rk=`sab.published` |
| 4 | `q.ops` | queue (durable, DLX-wired) | Bound to `infotriage.events`, rk=`feed.unhealthy` |

DLX-first ordering is mandatory: declaring a primary queue with `x-dead-letter-exchange` before
the DLX exchange exists raises a `406 PRECONDITION_FAILED` from the broker.

### Publisher confirms (pika 1.4.1 API)

In pika 1.4.1, publisher confirms are activated via `channel.confirm_delivery()`. The
`basic_publish()` call then returns `None` on broker-ack and raises `NackError`/`UnroutableError`
on broker-nack. All four event-type publishes returned without exception.

Note: the `wait_for_confirms()` method seen in some online examples does NOT exist in
pika 1.4.1; the correct pattern is exception-on-failure from `basic_publish()`.

### Dead-letter path

- Poison message payload: `{"id": "poison-001", "__poison__": True, "source": "NRK"}`
- Consumer detected `__poison__` marker → called `basic_nack(delivery_tag, requeue=False)`
- Broker routed message via `infotriage.dlx` (routing key `dead`) to `infotriage.dlq`
- Queue depth verified = 1 via `queue_declare(passive=True).method.message_count`
- No requeue loop: `requeue=False` is the correct T-00-R1-01 mitigation

### Runtime environment

| Parameter | Value |
|-----------|-------|
| Broker image | `rabbitmq:3.13-management` |
| Broker port | 22060 (AMQP), credentials spike/spike |
| Client library | `pika==1.4.1` |
| Python | 3.13.5 |
| Connection model | Single-threaded `BlockingConnection` per process |

---

## ADR-007 Decision Inputs

| Question | Finding |
|----------|---------|
| Does topic exchange + routing key design work for 4 event types? | YES — all 4 confirmed |
| Is pika BlockingConnection sufficient for spike and Phase 3 prototype? | YES for spike; for production, aio-pika preferred (auto-reconnect, async) |
| Does DLQ via DLX work without application-level coordination? | YES — nack with requeue=False is sufficient; broker handles routing atomically |
| Can the bus scale to M3 fan-out (multiple consumers per event)? | ASSUMED YES via additional queue_bind calls; not tested in this spike (A4) |

---

## Caveats and Open Items

- **M3 fan-out not tested (A4):** adding a second consumer queue bound to the same routing key
  (for M3 team fan-out) is architecturally straightforward but was not exercised in this spike.
  Record in ADR-007 that M3 fan-out requires a separate queue per subscriber, not a shared queue.
- **aio-pika for Phase 3:** `pika` BlockingConnection is single-threaded and not suitable for
  a long-running production service. Phase 3 bus implementation should use `aio-pika` with
  `connect_robust()` (auto-reconnect) and async consumer callbacks.
- **pika API surface deviation:** `wait_for_confirms()` is absent in pika 1.4.1; the correct
  pattern is `confirm_delivery()` + exception handling on `basic_publish()`. Document for Phase 3.

---

## Conclusion

**R1: GO.** The InfoTriage AMQP topology (topic exchange, 4 routing keys, DLX/DLQ) operates
exactly as designed on RabbitMQ 3.13. Proceed to ADR-007 with this topology confirmed.
