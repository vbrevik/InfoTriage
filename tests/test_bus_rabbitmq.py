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
import contextlib
import json
import logging
import socket
import time
from unittest.mock import patch

import aio_pika
import pytest

log = logging.getLogger(__name__)

import sys

sys.path.insert(0, "/Users/vidarbrevik/projects/InfoTriage/libs/contracts/src")
from contracts import RabbitMQBus


AMQP_URL = "amqp://infotriage:infotriage_rmq@127.0.0.1:22001"

# Test-isolated topology names.  Prefixing queues/exchanges with "test." keeps
# the running triage/brief containers from consuming messages published by
# these tests, while still exercising the same _bus_rabbitmq.py code paths.
TEST_PREFIX = "test."
TEST_ROUTING_KEY_TO_QUEUE = {
    "item.ingested": f"{TEST_PREFIX}q.triage",
    "verdict.ready": f"{TEST_PREFIX}q.brief",
    "sab.published": f"{TEST_PREFIX}q.notify",
    "feed.unhealthy": f"{TEST_PREFIX}q.ops",
}
TEST_DLX_NAME = f"{TEST_PREFIX}infotriage.dlx"
TEST_DLQ_NAME = f"{TEST_PREFIX}infotriage.dlq"
TEST_DLQ_ROUTING_KEY = f"{TEST_PREFIX}dead"

ROUTING_KEYS = list(TEST_ROUTING_KEY_TO_QUEUE.keys())


@contextlib.contextmanager
def _patched_topology():
    """Patch RabbitMQBus topology globals to test-isolated names."""
    with patch.multiple(
        "contracts._bus_rabbitmq",
        ROUTING_KEY_TO_QUEUE=TEST_ROUTING_KEY_TO_QUEUE,
        DLX_NAME=TEST_DLX_NAME,
        DLQ_NAME=TEST_DLQ_NAME,
        DLQ_ROUTING_KEY=TEST_DLQ_ROUTING_KEY,
    ):
        yield


@pytest.fixture(scope="module", autouse=True)
def _cleanup_test_topology():
    """Yield to tests, then delete test-isolated RabbitMQ topology after the module."""
    yield
    if not _rabbitmq_reachable():
        return

    async def _delete() -> None:
        try:
            connection = await aio_pika.connect_robust(AMQP_URL)
            channel = await connection.channel()
            # Delete test queues first (queues must be removed before exchanges)
            for q_name in list(TEST_ROUTING_KEY_TO_QUEUE.values()) + [TEST_DLQ_NAME]:
                try:
                    queue = await channel.get_queue(q_name)
                    await queue.delete()
                except Exception as exc:  # pragma: no cover
                    log.debug("Could not delete test queue %s: %s", q_name, exc)
            # Delete test DLX (main exchange is shared with production and must stay)
            try:
                exchange = await channel.get_exchange(TEST_DLX_NAME)
                await exchange.delete()
            except Exception as exc:  # pragma: no cover
                log.debug("Could not delete test DLX %s: %s", TEST_DLX_NAME, exc)
            await channel.close()
            await connection.close()
        except Exception as exc:  # pragma: no cover
            log.warning("RabbitMQ test topology cleanup failed: %s", exc)

    asyncio.run(_delete())


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


def _skip_if_unavailable() -> None:
    """Skip the current test if RabbitMQ :22001 is not reachable."""
    if not _rabbitmq_reachable():
        pytest.skip(
            "RabbitMQ :22001 not available — run: docker compose up -d rabbitmq"
        )


async def _fresh_bus() -> RabbitMQBus:
    bus = RabbitMQBus(amqp_url=AMQP_URL)
    await bus._ensure_connection()
    # Purge all test-isolated queues for clean test isolation
    for rk, q in bus._queues.items():
        live_q = await bus._channel.get_queue(q.name)
        await live_q.purge()
    try:
        dlq = await bus._channel.get_queue(TEST_DLQ_NAME)
        await dlq.purge()
    except Exception:
        pass
    return bus


# ---------------------------------------------------------------------------
# Test 0: Publisher confirms enabled after connection (R2.AC3)
# ---------------------------------------------------------------------------


@pytest.mark.rabbitmq
def test_publisher_confirms_enabled() -> None:
    """After _ensure_connection(), channel must have publisher confirms active (R2.AC3).

    aio-pika enables confirms via channel.confirm_delivery(). The channel exposes
    this via _publisher_confirms == True on the underlying channel implementation.
    """
    _skip_if_unavailable()

    async def _check() -> None:
        bus = await _fresh_bus()
        try:
            assert (
                bus._channel is not None
            ), "_channel is None after _ensure_connection()"
            # aio-pika RobustChannel sets _publisher_confirms = True after confirm_delivery()
            assert (
                bus._channel.publisher_confirms is True
            ), f"Publisher confirms not enabled — publisher_confirms={bus._channel.publisher_confirms!r}"
        finally:
            await bus.close()

    with _patched_topology():
        asyncio.run(_check())


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
            assert set(bus._queues.keys()) == set(
                ROUTING_KEYS
            ), f"Queue keys mismatch: {set(bus._queues.keys())}"
        finally:
            await bus.close()

    with _patched_topology():
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
                "item.ingested": {
                    "event": "item.ingested",
                    "item_id": "rt_01",
                    "source": "NRK",
                },
                "verdict.ready": {
                    "event": "verdict.ready",
                    "item_id": "rt_02",
                    "score": 8,
                },
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
                assert (
                    len(messages) == 1
                ), f"Expected 1 message for {rk}, got {len(messages)}"
                assert (
                    messages[0] == expected
                ), f"Payload mismatch for {rk}: {messages[0]} != {expected}"
        finally:
            await bus.close()

    with _patched_topology():
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
            assert (
                len(messages) == 1
            ), f"Expected 1 message (dedup), got {len(messages)}: {messages}"
            assert messages[0]["n"] == 1
        finally:
            await bus.close()

    with _patched_topology():
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

            # Consume from test-isolated q.triage and NACK with requeue=False
            q_triage = await bus._channel.get_queue(
                TEST_ROUTING_KEY_TO_QUEUE["item.ingested"]
            )
            nacked = asyncio.Event()

            async def _consumer(msg: aio_pika.IncomingMessage) -> None:
                body = json.loads(msg.body.decode())
                if body.get("__poison__"):
                    await msg.nack(requeue=False)  # triggers dead-lettering
                    nacked.set()

            consumer_tag = await q_triage.consume(_consumer)
            try:
                await asyncio.wait_for(nacked.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                pytest.fail("Poison message was not consumed from q.triage within 5s")
            finally:
                await q_triage.cancel(consumer_tag)

            # Wait for dead-letter routing (up to 5s)
            dlq = await bus._channel.get_queue(TEST_DLQ_NAME)
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
            assert (
                dlq_payload.get("__poison__") is True
            ), f"DLQ payload unexpected: {dlq_payload}"
        finally:
            await bus.close()

    with _patched_topology():
        asyncio.run(_run())
