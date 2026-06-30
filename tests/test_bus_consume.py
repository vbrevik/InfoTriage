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
import json
import os
import socket

import aio_pika
import pytest

from contracts import RabbitMQBus

AMQP_URL = os.environ.get(
    "INFOTRIAGE_AMQP_DSN", "amqp://infotriage:infotriage_rmq@127.0.0.1:22001"
)


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
        pytest.skip("RabbitMQ :22001 not available — run: docker compose up -d rabbitmq")


async def _fresh_bus() -> RabbitMQBus:
    """Return a connected RabbitMQBus with all queues purged for test isolation."""
    bus = RabbitMQBus(amqp_url=AMQP_URL)
    await bus._ensure_connection()
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
        try:
            rk = "item.ingested"
            item_id = "consume_test_001"
            payload = {"event": rk, "item_id": item_id, "n": 1}

            received = asyncio.Event()
            received_payload = {}

            async def _handler(msg: aio_pika.IncomingMessage) -> None:
                async with msg.process():
                    received_payload.update(json.loads(msg.body.decode()))
                    received.set()

            await bus.consume(rk, _handler, prefetch_count=1)
            await bus.publish(rk, item_id, payload)

            await asyncio.wait_for(received.wait(), timeout=5.0)
            assert received_payload.get("item_id") == item_id
        finally:
            await bus.close()

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
            async def _handler(msg: aio_pika.IncomingMessage) -> None:
                pass

            with pytest.raises(ValueError):
                await bus.consume("no.such.key", _handler)
        finally:
            await bus.close()

    asyncio.run(_run())
