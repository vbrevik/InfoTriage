#!/usr/bin/env python3
"""tests/test_bus_consume.py — RabbitMQBus.consume() persistent-consumer smoke test (R2).

Tests require RabbitMQ running on :22001. They skip gracefully when the broker
is not reachable. Start the container before running:

    docker compose up -d rabbitmq

Then run the suite:

    pytest tests/test_bus_consume.py -v -m rabbitmq

Tests:
    test_consume_delivers_message — a message published to item.ingested is
        delivered to a consume()-registered handler (R2)
    test_consume_unknown_routing_key_raises — consume() raises ValueError for
        a routing key with no declared queue
"""
import asyncio
import contextlib
import json
import logging
import os
import socket

import aio_pika
import pytest
from unittest.mock import patch

from contracts import RabbitMQBus

log = logging.getLogger(__name__)

AMQP_URL = "amqp://infotriage:infotriage_rmq@127.0.0.1:22001"

# Test-isolated topology prefix. Must match test_bus_rabbitmq.py so the same
# cleanup fixture can remove queues/exchanges created here.
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


def _rabbitmq_reachable() -> bool:
    """Return True if RabbitMQ AMQP port is reachable on 127.0.0.1:22001."""
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
            assert channel is not None
            for q_name in list(TEST_ROUTING_KEY_TO_QUEUE.values()) + [TEST_DLQ_NAME]:
                try:
                    queue = await channel.get_queue(q_name)
                    await queue.delete()
                except Exception as exc:  # pragma: no cover
                    log.debug("Could not delete test queue %s: %s", q_name, exc)
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


async def _fresh_bus() -> RabbitMQBus:
    """Return a connected RabbitMQBus with all queues purged for test isolation."""
    bus = RabbitMQBus(amqp_url=AMQP_URL)
    await bus._ensure_connection()
    assert bus._channel is not None
    for rk, q in bus._queues.items():
        live_q = await bus._channel.get_queue(q.name)
        await live_q.purge()
    return bus


# ---------------------------------------------------------------------------
# Test 1: consume() delivers a published message to the registered handler
# ---------------------------------------------------------------------------


@pytest.mark.rabbitmq
def test_consume_delivers_message() -> None:
    """A message published to item.ingested is delivered to a consume() handler (R2)."""
    _skip_if_unavailable()

    async def _run() -> None:
        bus = await _fresh_bus()
        consumer_tag: str | None = None
        try:
            rk = "item.ingested"
            item_id = "consume_test_001"
            payload = {"event": rk, "item_id": item_id, "n": 1}

            received = asyncio.Event()
            received_payload = {}

            async def _handler(msg: aio_pika.abc.AbstractIncomingMessage) -> None:
                async with msg.process():
                    received_payload.update(json.loads(msg.body.decode()))
                    received.set()

            consumer_tag = await bus.consume(rk, _handler, prefetch_count=1)
            await bus.publish(rk, item_id, payload)

            await asyncio.wait_for(received.wait(), timeout=5.0)
            assert received_payload.get("item_id") == item_id
        finally:
            if consumer_tag is not None:
                await bus._queues[rk].cancel(consumer_tag)
            await bus.close()

    with _patched_topology():
        asyncio.run(_run())


# ---------------------------------------------------------------------------
# Test 2: consume() raises ValueError for an unknown routing key
# ---------------------------------------------------------------------------


@pytest.mark.rabbitmq
def test_consume_unknown_routing_key_raises() -> None:
    """consume() raises ValueError when routing_key has no declared queue."""
    _skip_if_unavailable()

    async def _run() -> None:
        bus = await _fresh_bus()
        try:

            async def _handler(msg: aio_pika.abc.AbstractIncomingMessage) -> None:
                pass

            with pytest.raises(ValueError):
                await bus.consume("no.such.key", _handler)
        finally:
            await bus.close()

    with _patched_topology():
        asyncio.run(_run())
