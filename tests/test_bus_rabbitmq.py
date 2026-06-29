#!/usr/bin/env python3
"""test_bus_rabbitmq.py — Smoke tests for RabbitMQ bus transport (Phase 3).

Tests require RabbitMQ running on :22001. They skip gracefully when the broker
is not reachable. Start the container before running:

    docker compose up -d rabbitmq

Then run the suite:

    pytest tests/test_bus_rabbitmq.py -v -m rabbitmq

Tests:
    test_rabbitmq_available      — connectivity + topology declared correctly (R1)
    test_publish_consume_roundtrip — all 4 event types end-to-end (R3)
    test_dedup                   — same (routing_key, item_id) deduped (single message)
    test_dlq_poison              — NACK requeue=False routes to infotriage.dlq (R2.AC4)
"""
import asyncio
import json
import socket
import subprocess
import time

import pytest
import aio_pika

from contracts import RabbitMQBus

AMQP_URL = "amqp://infotriage:infotriage_rmq@127.0.0.1:22001"

ROUTING_KEYS = [
    "item.ingested",
    "verdict.ready",
    "sab.published",
    "feed.unhealthy",
]


def _rabbitmq_reachable() -> bool:
    """Return True if RabbitMQ AMQP port is reachable."""
    try:
        s = socket.socket()
        s.settimeout(2)
        s.connect(("127.0.0.1", 22001))
        s.close()
        return True
    except OSError:
        return False


def _wait_for_rabbitmq(timeout: int = 30) -> bool:
    """Poll until :22001 is reachable or timeout (seconds)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _rabbitmq_reachable():
            return True
        time.sleep(1)
    return False


def _skip_if_unavailable() -> None:
    """Skip the current test if RabbitMQ :22001 is not reachable."""
    if not _rabbitmq_reachable():
        pytest.skip("RabbitMQ :22001 not available — run: docker compose up -d rabbitmq")


async def _fresh_bus() -> RabbitMQBus:
    """Return a connected RabbitMQBus with all queues purged for test isolation."""
    bus = RabbitMQBus(amqp_url=AMQP_URL)
    await bus._ensure_connection()
    # Purge all queues for clean test isolation
    for rk, q in bus._queues.items():
        live_q = await bus._channel.get_queue(q.name)
        await live_q.purge()
    try:
        dlq = await bus._channel.get_queue("infotriage.dlq")
        await dlq.purge()
    except Exception:
        pass
    return bus


# ---------------------------------------------------------------------------
# Test 1: Connectivity + topology check (R1)
# ---------------------------------------------------------------------------

@pytest.mark.rabbitmq
def test_rabbitmq_available() -> None:
    """RabbitMQ :22001 is reachable and AMQP topology is declared correctly (R1)."""
    _skip_if_unavailable()

    async def _check() -> None:
        bus = await _fresh_bus()
        try:
            assert bus._connection is not None, "No connection"
            assert not bus._connection.is_closed, "Connection is closed"
            # Verify topology declared
            assert bus._exchange is not None, "events exchange not declared"
            assert bus._dlx is not None, "DLX not declared"
            assert bus._dlq is not None, "DLQ not declared"
            assert set(bus._queues.keys()) == set(ROUTING_KEYS), (
                f"Queue keys mismatch: {set(bus._queues.keys())}"
            )
        finally:
            await bus.close()

    asyncio.run(_check())


# ---------------------------------------------------------------------------
# Test 2: Publish/consume round-trip for all 4 event types (R3)
# ---------------------------------------------------------------------------

@pytest.mark.rabbitmq
def test_publish_consume_roundtrip() -> None:
    """Publish all 4 event types and consume each from its queue (R3 end-to-end)."""
    _skip_if_unavailable()

    async def _run() -> None:
        bus = await _fresh_bus()
        try:
            payloads = {
                "item.ingested": {"event": "item.ingested", "item_id": "rt_01", "source": "NRK"},
                "verdict.ready": {"event": "verdict.ready", "item_id": "rt_02", "score": 8},
                "sab.published": {
                    "event": "sab.published",
                    "item_id": "rt_03",
                    "snapshot_day": "2026-06-29",
                },
                "feed.unhealthy": {
                    "event": "feed.unhealthy",
                    "item_id": "rt_04",
                    "feed_url": "http://nrk.no/rss",
                },
            }

            # Publish all 4
            for rk, payload in payloads.items():
                await bus.publish(rk, payload["item_id"], payload)

            # Small wait for broker to route
            await asyncio.sleep(0.2)

            # Consume and verify each
            for rk, expected in payloads.items():
                messages = await bus.subscribe(rk)
                assert len(messages) == 1, (
                    f"Expected 1 message for {rk}, got {len(messages)}"
                )
                assert messages[0] == expected, (
                    f"Payload mismatch for {rk}: {messages[0]} != {expected}"
                )
        finally:
            await bus.close()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Test 3: Dedup — same (routing_key, item_id) is no-op
# ---------------------------------------------------------------------------

@pytest.mark.rabbitmq
def test_dedup() -> None:
    """Re-publishing same (routing_key, item_id) is a no-op (single message in queue)."""
    _skip_if_unavailable()

    async def _run() -> None:
        bus = await _fresh_bus()
        try:
            rk = "item.ingested"
            item_id = "dedup_test_001"
            payload = {"event": rk, "item_id": item_id, "n": 1}

            # Publish twice — second should be silently dropped (dedup)
            await bus.publish(rk, item_id, payload)
            await bus.publish(rk, item_id, payload)

            await asyncio.sleep(0.2)
            messages = await bus.subscribe(rk)
            assert len(messages) == 1, (
                f"Expected 1 message (dedup), got {len(messages)}: {messages}"
            )
            assert messages[0]["n"] == 1
        finally:
            await bus.close()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Test 4: Dead-letter queue — NACK requeue=False routes poison to infotriage.dlq
# ---------------------------------------------------------------------------

@pytest.mark.rabbitmq
def test_dlq_poison() -> None:
    """NACK with requeue=False routes message to infotriage.dlq within 5s (R2.AC4)."""
    _skip_if_unavailable()

    async def _run() -> None:
        bus = await _fresh_bus()
        try:
            rk = "item.ingested"
            item_id = "poison_test_001"
            poison_payload = {"event": rk, "item_id": item_id, "__poison__": True}

            # Publish poison message
            await bus.publish(rk, item_id, poison_payload)
            await asyncio.sleep(0.2)

            # Consume from q.triage and NACK with requeue=False
            q_triage = await bus._channel.get_queue("q.triage")
            nacked = asyncio.Event()

            async def _consumer(msg: aio_pika.IncomingMessage) -> None:
                body = json.loads(msg.body.decode())
                if body.get("__poison__"):
                    await msg.nack(requeue=False)   # triggers dead-lettering
                    nacked.set()

            consumer_tag = await q_triage.consume(_consumer)
            try:
                await asyncio.wait_for(nacked.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                pytest.fail("Poison message was not consumed from q.triage within 5s")
            finally:
                await q_triage.cancel(consumer_tag)

            # Wait for dead-letter routing (up to 5s)
            dlq = await bus._channel.get_queue("infotriage.dlq")
            dlq_payload = None
            deadline = time.monotonic() + 5.0

            while time.monotonic() < deadline:
                msg = await dlq.get(fail=False, timeout=1)
                if msg:
                    async with msg.process():
                        dlq_payload = json.loads(msg.body.decode())
                    break
                await asyncio.sleep(0.2)

            assert dlq_payload is not None, "DLQ empty after 5s — dead-lettering failed"
            assert dlq_payload.get("__poison__") is True, (
                f"DLQ payload unexpected: {dlq_payload}"
            )
        finally:
            await bus.close()

    asyncio.run(_run())
