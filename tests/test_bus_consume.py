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
    test_verdict_ready_fans_out_to_both_queues — one verdict.ready publish is
        delivered to a no-override consumer AND a queue_name-overridden consumer
        as independent copies (fan-out regression proof)
    test_consume_rejects_queue_not_bound_to_routing_key — consume() raises
        ValueError when queue_name names a queue bound to a different routing key
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
    "item.ingested": [f"{TEST_PREFIX}q.triage"],
    "verdict.ready": [f"{TEST_PREFIX}q.brief", f"{TEST_PREFIX}q.wiki"],
    "sab.published": [f"{TEST_PREFIX}q.notify"],
    "feed.unhealthy": [f"{TEST_PREFIX}q.ops"],
}
TEST_DLX_NAME = f"{TEST_PREFIX}infotriage.dlx"
TEST_DLQ_NAME = f"{TEST_PREFIX}infotriage.dlq"
TEST_DLQ_ROUTING_KEY = f"{TEST_PREFIX}dead"

# Flattened list of every declared test queue name, for cleanup and lookups keyed
# by queue name (bus._queues is keyed by queue name, not routing key).
TEST_QUEUE_NAMES = [
    q_name for q_names in TEST_ROUTING_KEY_TO_QUEUE.values() for q_name in q_names
]


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
            for q_name in TEST_QUEUE_NAMES + [TEST_DLQ_NAME]:
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
    for q_name, q in bus._queues.items():
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
                await bus._queues[TEST_ROUTING_KEY_TO_QUEUE[rk][0]].cancel(consumer_tag)
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


# ---------------------------------------------------------------------------
# Test 3: One verdict.ready event fans out to BOTH queues as independent copies
# ---------------------------------------------------------------------------


@pytest.mark.rabbitmq
def test_verdict_ready_fans_out_to_both_queues() -> None:
    """One published verdict.ready message is delivered to a no-override consumer
    (brief-equivalent) AND to a consumer overridden onto the wiki-equivalent queue —
    the direct inverse of the live-observed competing-consumer bug."""
    _skip_if_unavailable()

    async def _run() -> None:
        bus = await _fresh_bus()
        brief_tag: str | None = None
        wiki_tag: str | None = None
        try:
            rk = "verdict.ready"
            item_id = "fanout_test_001"
            payload = {"event": rk, "item_id": item_id, "n": 1}

            brief_received = asyncio.Event()
            brief_payload: dict = {}
            wiki_received = asyncio.Event()
            wiki_payload: dict = {}

            async def _brief_handler(
                msg: aio_pika.abc.AbstractIncomingMessage,
            ) -> None:
                async with msg.process():
                    brief_payload.update(json.loads(msg.body.decode()))
                    brief_received.set()

            async def _wiki_handler(
                msg: aio_pika.abc.AbstractIncomingMessage,
            ) -> None:
                async with msg.process():
                    wiki_payload.update(json.loads(msg.body.decode()))
                    wiki_received.set()

            # No override — proves the production brief call signature is untouched.
            brief_tag = await bus.consume(rk, _brief_handler, prefetch_count=1)
            # Explicit override onto the wiki-equivalent queue.
            wiki_tag = await bus.consume(
                rk,
                _wiki_handler,
                prefetch_count=1,
                queue_name=TEST_ROUTING_KEY_TO_QUEUE[rk][1],
            )

            await bus.publish(rk, item_id, payload)

            await asyncio.wait_for(
                asyncio.gather(brief_received.wait(), wiki_received.wait()),
                timeout=5.0,
            )
            assert brief_payload == payload
            assert wiki_payload == payload
        finally:
            if brief_tag is not None:
                await bus._queues[TEST_ROUTING_KEY_TO_QUEUE["verdict.ready"][0]].cancel(
                    brief_tag
                )
            if wiki_tag is not None:
                await bus._queues[TEST_ROUTING_KEY_TO_QUEUE["verdict.ready"][1]].cancel(
                    wiki_tag
                )
            await bus.close()

    with _patched_topology():
        asyncio.run(_run())


# ---------------------------------------------------------------------------
# Test 4: consume() rejects a queue not bound to the given routing key
# ---------------------------------------------------------------------------


@pytest.mark.rabbitmq
def test_consume_rejects_queue_not_bound_to_routing_key() -> None:
    """consume() raises ValueError when queue_name names a queue bound to a
    DIFFERENT routing key than the one requested."""
    _skip_if_unavailable()

    async def _run() -> None:
        bus = await _fresh_bus()
        try:

            async def _handler(msg: aio_pika.abc.AbstractIncomingMessage) -> None:
                pass

            with pytest.raises(ValueError):
                await bus.consume(
                    "verdict.ready",
                    _handler,
                    queue_name=TEST_ROUTING_KEY_TO_QUEUE["item.ingested"][0],
                )
        finally:
            await bus.close()

    with _patched_topology():
        asyncio.run(_run())
