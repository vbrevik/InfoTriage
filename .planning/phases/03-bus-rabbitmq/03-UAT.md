---
status: testing
phase: 03-bus-rabbitmq
source: [03-VERIFICATION.md]
started: 2026-06-29T08:25:00Z
updated: 2026-06-29T08:25:00Z
---

## Current Test

number: 1
name: Async/sync Protocol interchangeability at BusClient call site
expected: |
  A function typed `def process(bus: BusClient)` can call `bus.publish(rk, id, payload)` and
  `bus.subscribe(rk)` interchangeably on both InMemoryBus and RabbitMQBus with the same call site
  (no await required, identical return types, no coroutine leakage)
awaiting: user decision on fix path (option a/b/c below)

## Tests

### 1. Async/sync Protocol mismatch — BusClient interchangeability

expected: |
  RabbitMQBus is a drop-in for InMemoryBus at a `bus: BusClient`-typed call site.
  BusClient.publish() and BusClient.subscribe() are sync → any caller using the Protocol type
  without await must get correct values back, not coroutine objects.
result: [pending]

**Issue found by verifier:** `_bus.py` defines `def publish(...)` and `def subscribe(...)` (sync).
`RabbitMQBus` implements `async def publish(...)` and `async def subscribe(...)`.
`isinstance(RabbitMQBus(), BusClient)` returns `True` (runtime_checkable checks attribute presence
only, not coroutine status). Phase 5/6 callers using `bus: BusClient` without await will silently
get a coroutine object back from RabbitMQBus instead of None.

**Decision options:**

- **(a)** Update `BusClient` Protocol in `_bus.py` to `async def publish/subscribe` — all callers
  must await. Cleanest long-term; requires updating InMemoryBus + all future transports.
- **(b)** Add sync shim methods to `RabbitMQBus` that run the async internals via
  `asyncio.get_event_loop().run_until_complete(...)` — keeps Protocol sync, but can't be called
  from inside an existing event loop (breaks async callers).
- **(c)** Document that the BusClient Protocol is async-first (callers must always await) and
  update InMemoryBus to also use `async def` — consistent, no sync-async ambiguity.

**Recommended:** Option (c) — async-first Protocol, update InMemoryBus to match.

---

### 2. Publisher confirms — verify AMQP-level ack vs fire-and-forget

expected: |
  `exchange.publish()` blocks until the broker acks the message at the AMQP layer
  (not just socket write). Either `channel.confirm_delivery()` is called, or the channel
  is opened with `publisher_confirms=True`. Publishing to an unroutable key raises
  `UnroutableError` (requires confirm mode).
result: [pending]

**Issue found by verifier:** `channel.confirm_delivery()` is absent from `_bus_rabbitmq.py`.
Code comments claim aio-pika's `await exchange.publish()` provides implicit confirms, but in
aio-pika without explicit confirm mode, `exchange.publish()` completes after the socket write,
not after the broker ack. DLQ tests pass (dead-lettering works at broker level), but the
confirms guarantee (PLAN R2 must-have) is unverified.

**To verify interactively:**
```python
# In a Python shell with RabbitMQ running:
import asyncio
from libs.contracts.src.contracts._bus_rabbitmq import RabbitMQBus

async def test_confirm():
    bus = RabbitMQBus("amqp://guest:guest@localhost:22001/")
    await bus.connect()
    # Publish to a routing key with NO bound queue — should raise UnroutableError
    # if confirms are active; silently succeeds if fire-and-forget
    try:
        await bus.publish("nonexistent.key", "test-id", {"x": 1})
        print("FIRE-AND-FORGET — confirms NOT active")
    except Exception as e:
        print(f"ERROR raised: {e}")  # UnroutableError = confirms active
    await bus.disconnect()

asyncio.run(test_confirm())
```

If fire-and-forget: add `publisher_confirms=True` to `channel()` call in `_bus_rabbitmq.py`.

---

## Summary

total: 2
passed: 0
issues: 0
pending: 2
skipped: 0
blocked: 0

## Gaps
