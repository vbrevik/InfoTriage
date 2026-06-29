---
status: complete
phase: 03-bus-rabbitmq
source: [03-SUMMARY.md]
started: 2026-06-29T10:55:00Z
updated: 2026-06-29T10:58:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Cold Start Smoke Test
expected: |
  Kill any running stack (docker compose down). Start fresh (docker compose up -d rabbitmq).
  RabbitMQ boots without errors, healthcheck passes (rabbitmq-diagnostics -q ping returns 0),
  and management UI loads at http://localhost:22002 (default guest/guest login).
result: pass

### 2. RabbitMQ ports accessible
expected: |
  AMQP port :22001 accepts connections (localhost-only).
  Management UI :22002 is reachable in browser. No other ports exposed.
result: pass

### 3. Publish/consume roundtrip — all 4 event types
expected: |
  Running: pytest tests/test_bus_rabbitmq.py -v -m rabbitmq
  test_publish_consume_roundtrip PASSES — all 4 routing keys (item.ingested, verdict.ready,
  sab.published, feed.unhealthy) publish and consume correctly.
  test_rabbitmq_available PASSES — topology declared successfully.
result: pass

### 4. DLQ dead-lettering
expected: |
  test_dlq_poison PASSES — a NACK'd message with requeue=False appears in infotriage.dlq
  within 5 seconds. Dead-letter routing is working correctly.
result: pass

### 5. Dedup behavior
expected: |
  test_dedup PASSES — publishing the same (routing_key, item_id) twice results in only
  one message in the queue (dedup keyed on composite key, matching InMemoryBus behavior).
result: pass

### 6. No regressions in existing suite
expected: |
  pytest tests/ -q -k "not db_live and not rabbitmq" → all pass (151+ tests green,
  no regressions from Phase 1/2 work).
result: pass

## Summary

total: 6
passed: 6
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

