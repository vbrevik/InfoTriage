---
status: resolved
phase: 03-bus-rabbitmq
source: [03-VERIFICATION.md]
started: 2026-06-29T08:25:00Z
updated: 2026-06-29T08:40:00Z
---

## Current Test

(all resolved)

## Tests

### 1. Async/sync Protocol mismatch — BusClient interchangeability

expected: |
  RabbitMQBus is a drop-in for InMemoryBus at a `bus: BusClient`-typed call site.
  Both implementations use async def — callers always await, identical return types.
result: resolved

**Fix applied (commit 8fb94c8):** Option (c) — BusClient Protocol updated to `async def publish/subscribe`.
InMemoryBus updated to match. All 6 InMemoryBus tests converted to `@pytest.mark.asyncio`.
162/162 tests pass.

---

### 2. Publisher confirms — AMQP-level ack vs fire-and-forget

expected: |
  `exchange.publish()` blocks until broker acks at the AMQP layer.
  Channel opened with `publisher_confirms=True`.
result: resolved

**Fix applied (commit 8fb94c8):** Both `channel()` calls in `_ensure_connection()` and
`_rebuild_topology()` now pass `publisher_confirms=True`. Docstring updated to reflect
actual mechanism (not the incorrect "implicit" claim). 162/162 tests pass.

---

## Summary

total: 2
passed: 2
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps
