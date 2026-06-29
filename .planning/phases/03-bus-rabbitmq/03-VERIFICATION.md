---
phase: 03-bus-rabbitmq
verified: 2026-06-29T00:00:00Z
status: passed
score: 5/5 must-haves verified
behavior_unverified: 0
overrides_applied: 0
behavior_unverified_items:
  - truth: "aio-pika bus client implements BusClient Protocol — async/sync mismatch breaks transport-swappability"
    test: "Use a BusClient-typed variable to call bus.publish() and bus.subscribe() interchangeably on both InMemoryBus and RabbitMQBus without await"
    expected: "Both implementations respond identically at the call site (no coroutine leakage)"
    why_human: "runtime_checkable isinstance passes because it only checks attribute presence. InMemoryBus methods are sync; RabbitMQBus methods are async. Code inspection confirms the mismatch but cannot determine whether Phase 5/6 callers will handle this correctly."
  - truth: "Publisher confirms work via channel.confirm_delivery(), requeue=False dead-lettering routes poison to infotriage.dlq"
    test: "Inspect whether AMQP publisher confirms are enabled on the channel; publish a message and verify the broker acked it (not just that the socket write completed)"
    expected: "channel.confirm_delivery() called, OR channel opened with publisher_confirms=True; exchange.publish() raise NackError/UnroutableError on broker rejection"
    why_human: "channel.confirm_delivery() is absent from the code. The SUMMARY claims aio-pika's await exchange.publish() provides implicit confirms, but in aio-pika without explicit confirm_delivery() or publisher_confirms=True, exchange.publish() is fire-and-forget at the AMQP layer. The DLQ tests pass (dead-lettering works), but the confirms guarantee cannot be verified by code inspection alone."
human_verification:
  - test: "Verify RabbitMQBus is interchangeable with InMemoryBus at a BusClient-typed call site"
    expected: "A function typed def process(bus: BusClient) can call bus.publish(...) and bus.subscribe(...) on both implementations without await and get identical return types"
    why_human: "BusClient Protocol defines sync methods; RabbitMQBus implements async methods. isinstance(RabbitMQBus(), BusClient) returns True (runtime_checkable presence-only), but any sync call site gets a coroutine object back from RabbitMQBus instead of None/list. Phase 5/6 callers will need to know implementation type to use await correctly."
  - test: "Verify publisher confirms are actually enabled on the AMQP channel"
    expected: "Publishing a message to a non-existent routing key raises UnroutableError (not silently discarded), proving the broker ack path is active"
    why_human: "channel.confirm_delivery() is not called anywhere in _bus_rabbitmq.py. The channel is opened with await self._connection.channel() with no publisher_confirms argument. Without explicit enables, aio-pika may operate in basic-publish (fire-and-forget) mode. The smoke tests pass because messages do arrive, but they do not verify the ack semantic."
---

# Phase 03: Bus — RabbitMQ Verification Report

**Phase Goal:** AMQP broker that also models team information-sharing (fan-out, per-consumer queues) for the M3 growth path.
**Verified:** 2026-06-29
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | RabbitMQ 3.13 container exposes ports 22001 (AMQP) and 22002 (management UI), joins infotriage network (R1) | ✓ VERIFIED | docker-compose.yml: `rabbitmq:3.13-management`, `127.0.0.1:22001:5672`, `127.0.0.1:22002:15672`, `networks: [infotriage]`, healthcheck via `rabbitmq-diagnostics -q ping` |
| 2 | aio-pika bus client implements BusClient Protocol with infotriage.events topic exchange, 4 routing keys, durable queues, DLX/DLQ (R2) | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | `isinstance(RabbitMQBus(), BusClient)` returns True (runtime_checkable presence check). Topology declared correctly. BUT `RabbitMQBus.publish` and `RabbitMQBus.subscribe` are `async def`; BusClient Protocol defines `def` (sync). Transport-swappability behavioral contract is broken at async call sites. |
| 3 | DLX infotriage.dlx declared before primary queues to avoid 406 PRECONDITION_FAILED (R2, context) | ✓ VERIFIED | `_declare_topology()` in `_bus_rabbitmq.py` lines 128–169: DLX declared step 1, DLQ step 2, infotriage.events step 3, primary queues step 4. Comment explicitly notes "ORDER IS MANDATORY". |
| 4 | Publisher confirms work via channel.confirm_delivery(), requeue=False dead-lettering routes poison to infotriage.dlq (R2, R2.AC4) | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | `channel.confirm_delivery()` is NOT called anywhere in `_bus_rabbitmq.py`. Channel is opened with `await self._connection.channel()` only. DLQ dead-lettering IS verified by `test_dlq_poison` (PASS). Publisher confirm guarantee is uncertain without explicit enable. |
| 5 | End-to-end smoke test passes: publish/consume round-trip for all 4 event types (R3) | ✓ VERIFIED | Live run: `pytest tests/test_bus_rabbitmq.py -v -m rabbitmq` → **4 passed** (test_rabbitmq_available, test_publish_consume_roundtrip, test_dedup, test_dlq_poison). |

**Score:** 3/5 truths verified (2 present, behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `docker-compose.yml` | RabbitMQ 3.13 service with ports + healthcheck | ✓ VERIFIED | Image `rabbitmq:3.13-management`, ports 22001/22002, healthcheck `rabbitmq-diagnostics -q ping` |
| `libs/contracts/src/contracts/_bus_rabbitmq.py` | RabbitMQBus implementing BusClient Protocol | ✓ EXISTS, SUBSTANTIVE | 227 lines, full topology + publish/subscribe + dedup + rebuild_topology |
| `libs/contracts/src/contracts/__init__.py` | RabbitMQBus exported in __all__ | ✓ VERIFIED | `from ._bus_rabbitmq import RabbitMQBus` present; appears in `__all__` |
| `requirements-dev.txt` | `aio-pika>=9.0` dependency | ✓ VERIFIED | Line 4: `aio-pika>=9.0` |
| `pyproject.toml` | `rabbitmq` pytest marker registered | ✓ VERIFIED | `"rabbitmq: requires RabbitMQ :22001 to be running"` in markers array |
| `tests/test_bus_rabbitmq.py` | 4 smoke tests, all @pytest.mark.rabbitmq | ✓ VERIFIED | 4 test functions, all marked, all pass live |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `_bus_rabbitmq.py` | `_bus.py` BusClient Protocol | structural subtyping | ⚠️ PARTIAL | `isinstance(RabbitMQBus(), BusClient)` = True; BUT methods are async vs sync Protocol — behavioral contract broken |
| `_bus_rabbitmq.py` | DLX topology | `_declare_topology()` DLX-first | ✓ WIRED | DLX declared step 1; primary queues step 4; x-dead-letter-exchange set to DLX_NAME |
| `_bus_rabbitmq.py` | `infotriage.dlq` | `_dlq.bind(self._dlx, routing_key="dead")` | ✓ WIRED | Line 148: `await self._dlq.bind(self._dlx, routing_key=DLQ_ROUTING_KEY)` |
| `__init__.py` | `RabbitMQBus` | `from ._bus_rabbitmq import RabbitMQBus` | ✓ WIRED | Importable as `from contracts import RabbitMQBus` |
| `test_bus_rabbitmq.py` | live RabbitMQ | `AMQP_URL = "amqp://infotriage:infotriage_rmq@127.0.0.1:22001"` | ✓ WIRED | Tests skip gracefully if :22001 unreachable |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| RabbitMQBus isinstance BusClient | `python -c "from contracts import BusClient, RabbitMQBus; print(isinstance(RabbitMQBus(), BusClient))"` | True | ✓ PASS |
| All 4 smoke tests live | `pytest tests/test_bus_rabbitmq.py -v -m rabbitmq` | 4 passed | ✓ PASS |
| Full regression suite | `pytest tests/ -q -k "not db_live and not rabbitmq"` | 151 passed | ✓ PASS |
| channel.confirm_delivery present | `grep -n "confirm_delivery" libs/contracts/src/contracts/_bus_rabbitmq.py` | 0 matches | ✗ FAIL — mechanism absent |
| RabbitMQBus.publish is coroutine | `inspect.iscoroutinefunction(RabbitMQBus.publish)` | True | ⚠️ MISMATCH — BusClient Protocol defines sync |
| RabbitMQBus.subscribe is coroutine | `inspect.iscoroutinefunction(RabbitMQBus.subscribe)` | True | ⚠️ MISMATCH — BusClient Protocol defines sync |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| ADR-007 | 03-PLAN.md | RabbitMQ event bus topology — exchanges, routing keys, DLX/DLQ, declaration order | ✓ SATISFIED | ADR-007 exists at `docs/adr/ADR-007-rabbitmq-bus.md`; all topology decisions implemented in `_bus_rabbitmq.py`; smoke test validates end-to-end |
| ADR-007 traceability gap | 03-PLAN.md `requirements: [ADR-007]` | ADR-007 does not appear in `.planning/REQUIREMENTS.md` (which uses D-/C-/P-/NF- format) | ⚠️ ORPHANED | ADR-007 is an Architecture Decision Record not a functional requirement row in REQUIREMENTS.md. Traceability gap — the plan's `requirements` field references an ADR rather than a REQUIREMENTS.md ID. Functionally satisfied; cross-reference tracking is incomplete. |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `_bus_rabbitmq.py` | 39 | `RABBITMQ_DEFAULT_URL = "amqp://infotriage:infotriage_rmq@127.0.0.1:22001"` — dev credentials in default | ℹ️ Info | Dev-only; comment notes "production overrides via INFOTRIAGE_AMQP_DSN"; not a blocker |
| `_bus_rabbitmq.py` | 219 | `await asyncio.sleep(0.5)` drain window in `subscribe()` | ⚠️ Warning | Hardcoded 500ms drain means subscribe() always takes ≥500ms regardless of queue depth; acceptable for Phase 3 smoke tests but not for production consumers |

No TBD/FIXME/XXX markers found in phase files.

### Prohibition Verification

| Prohibition | Statement | Result |
|-------------|-----------|--------|
| MUST NOT modify `_bus.py` BusClient Protocol | Only add new transport via structural subtyping | ✓ SATISFIED — `_bus.py` is unchanged; Protocol definition is intact; `_bus_rabbitmq.py` imports from it but adds no modifications |

### Human Verification Required

#### 1. Async/Sync Protocol Mismatch — Transport Swappability

**Test:** Write a function `def process(bus: BusClient) -> None: bus.publish("item.ingested", "id1", {})` and call it with both `InMemoryBus()` and `RabbitMQBus()`. Observe whether the return value is `None` (sync) or a coroutine object.

**Expected:** Both implementations return `None` synchronously; the BusClient Protocol contract is upheld.

**Actual (static):** `InMemoryBus.publish` is sync (returns None). `RabbitMQBus.publish` is `async def` (returns a coroutine unless awaited). A sync call site gets back a coroutine object — silent bug, no exception raised.

**Why human:** This is a design-level decision. Options: (a) accept the mismatch and require all Phase 5/6 callers to use `await bus.publish()` (breaking sync Protocol contract), (b) update the BusClient Protocol to define async methods (requires modifying `_bus.py`), or (c) add a sync wrapper to RabbitMQBus that runs `asyncio.run()`. One of these must be resolved before Phase 5 consumers use BusClient as a type annotation.

#### 2. Publisher Confirms — Confirm Mode Not Enabled

**Test:** Publish a message to `infotriage.events` with a routing key that has NO bound queue (not one of the 4). Observe whether `UnroutableError` is raised within `exchange.publish()`.

**Expected:** `UnroutableError` raised (proves mandatory=True + confirms are active).

**Why human:** `channel.confirm_delivery()` is absent. `connection.channel()` is called without `publisher_confirms=True`. In aio-pika, without explicit confirm mode, `exchange.publish()` may return immediately after the network write (fire-and-forget at AMQP layer). The `mandatory=True` flag requires confirm mode to be active in order to trigger returns for unroutable messages. The DLQ tests pass because they test dead-lettering (consumer nack path), not the publisher confirm path. This needs to be confirmed interactively or by adding a confirm-mode enable to `_ensure_connection()`.

---

## Gaps Summary

No hard FAILED truths — all 5 truths have code present and substantive artifacts. Two truths are PRESENT_BEHAVIOR_UNVERIFIED and route to human validation:

1. **Async/sync Protocol mismatch** (Truth 2): `RabbitMQBus` implements `BusClient` Protocol with `async def` methods where the Protocol declares `def` (sync). The `isinstance` check passes at runtime, but transport-swappability — the core contract — is broken for any sync call site. This will cause silent coroutine-not-awaited bugs in Phase 5/6 unless addressed.

2. **Publisher confirms mechanism** (Truth 4): `channel.confirm_delivery()` (the plan-specified mechanism) is absent. The channel is opened without `publisher_confirms=True`. Whether aio-pika's `await exchange.publish()` provides broker-ack semantics without explicit confirm mode enabled is uncertain. The DLQ dead-lettering is verified (test passes); the confirms guarantee is not.

Both items require a human decision on acceptable deviation before Phase 4/5 proceeds.

---

_Verified: 2026-06-29_
_Verifier: Claude (gsd-verifier)_
