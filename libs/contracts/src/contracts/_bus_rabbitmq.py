#!/usr/bin/env python3
"""_bus_rabbitmq.py — RabbitMQ bus transport for InfoTriage Phase 3.

Implements BusClient via aio-pika for async AMQP communication.
Uses durable topology with dead-letter queues (DLQ) for poison message handling.

Topology (declared in this order — DLX first is mandatory to avoid 406):
    1. infotriage.dlx  (direct, durable) — dead-letter exchange
    2. infotriage.dlq  (durable)         — dead-letter queue, bound to dlx with key "dead"
    3. infotriage.events (topic, durable) — main event exchange
    4. q.triage / q.brief / q.notify / q.ops (durable) — primary queues, DLX-wired

Usage:
    from contracts import RabbitMQBus

    async def main():
        bus = RabbitMQBus("amqp://infotriage:infotriage_rmq@127.0.0.1:22001")
        await bus._ensure_connection()
        await bus.publish("item.ingested", item_id="abc123", payload={"n": 1})
        messages = await bus.subscribe("item.ingested")
        await bus.close()

Security: DSN must be supplied by the caller from INFOTRIAGE_AMQP_DSN (never hard-coded in
production). The default here is a dev-only fallback; never log the DSN (T-03-01).
"""
import asyncio
import json
import logging
from typing import Any

import aio_pika
from aio_pika.abc import AbstractRobustConnection

from ._bus import BusClient  # noqa: F401 (imported for Protocol type annotations)

log = logging.getLogger(__name__)

# Dev-only default DSN — production overrides via INFOTRIAGE_AMQP_DSN
RABBITMQ_DEFAULT_URL = "amqp://infotriage:infotriage_rmq@127.0.0.1:22001"

# Routing-key → queue name mapping (single source of truth)
ROUTING_KEY_TO_QUEUE: dict[str, str] = {
    "item.ingested": "q.triage",
    "verdict.ready": "q.brief",
    "sab.published": "q.notify",
    "feed.unhealthy": "q.ops",
}

# Dead-letter configuration
DLX_NAME = "infotriage.dlx"
DLQ_NAME = "infotriage.dlq"
DLQ_ROUTING_KEY = "dead"


class RabbitMQBus:
    """Transport-swappable BusClient implementation using RabbitMQ + aio-pika.

    Dedup: keyed on (routing_key, item_id). Same as InMemoryBus.
    Reconnect: connect_robust() auto-reconnects on connection loss (exponential backoff, max 30s).
    Dead-lettering: primary queues declare x-dead-letter-exchange=infotriage.dlx,
        x-dead-letter-routing-key=dead. Nacked messages (requeue=False) route to infotriage.dlq.
    Publisher confirms: channel opened with publisher_confirms=True. exchange.publish() blocks
        until broker acks; NackError/UnroutableError raised on rejection.
    """

    def __init__(self, amqp_url: str = RABBITMQ_DEFAULT_URL) -> None:
        # DSN: caller must pass from env (T-03-01 — never logged)
        self.amqp_url = amqp_url
        self._connection: AbstractRobustConnection | None = None
        self._channel: aio_pika.RobustChannel | None = None
        self._exchange: aio_pika.RobustExchange | None = None
        self._dlx: aio_pika.RobustExchange | None = None
        self._dlq: aio_pika.RobustQueue | None = None
        self._queues: dict[str, aio_pika.RobustQueue] = {}   # routing_key → queue
        self._dedup_lock = asyncio.Lock()
        self._seen: set[tuple[str, str]] = set()

    async def _ensure_connection(self) -> None:
        """Establish AMQP connection with exponential backoff (T-03-03 rate-limit)."""
        if self._connection and not self._connection.is_closed:
            return

        max_delay = 30.0
        delay = 0.5

        while True:
            try:
                self._connection = await aio_pika.connect_robust(self.amqp_url)
                self._channel = await self._connection.channel(publisher_confirms=True)
                await self._channel.set_qos(prefetch_count=10)
                await self._declare_topology()
                break
            except Exception as e:
                # Check for topology mismatch (406 PRECONDITION_FAILED) before generic retry
                if "406" in str(e) or "PRECONDITION_FAILED" in str(e):
                    log.warning("Topology mismatch detected — rebuilding (migration): %s", e)
                    try:
                        await self._rebuild_topology()
                        break
                    except Exception as rebuild_err:
                        log.error("Topology rebuild failed: %s", rebuild_err)
                log.warning("AMQP connection failed: %s. Retrying in %.1fs", e, delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, max_delay)

    async def _rebuild_topology(self) -> None:
        """Delete all topology queues and redeclare from scratch.

        Called when existing queues have conflicting arguments (dev/migration scenario).
        This is safe in dev because queues are durable and messages are ephemeral in tests.
        In production, coordinate with ops before running.
        """
        assert self._connection is not None
        # Open a fresh channel (prior one closed after 406)
        ch = await self._connection.channel()
        for q_name in [DLQ_NAME, "q.triage", "q.brief", "q.notify", "q.ops"]:
            try:
                await ch.queue_delete(q_name)
                log.info("Deleted queue %s for topology rebuild", q_name)
            except Exception as e:
                log.debug("Could not delete queue %s (may not exist): %s", q_name, e)
        await ch.close()
        # Now open the real channel and declare fresh
        self._channel = await self._connection.channel(publisher_confirms=True)
        await self._channel.set_qos(prefetch_count=10)
        await self._declare_topology()

    async def _declare_topology(self) -> None:
        """Declare exchange/queue topology in safe order.

        ORDER IS MANDATORY:
        1. infotriage.dlx (DLX exchange) — must exist before primary queues reference it
        2. infotriage.dlq — terminal dead-letter destination
        3. infotriage.events — main topic exchange
        4. Primary queues with x-dead-letter-exchange=infotriage.dlx, x-dead-letter-routing-key=dead

        Failing to declare DLX first raises 406 PRECONDITION_FAILED from the broker.
        """
        assert self._channel is not None

        # 1. Dead-letter exchange — MUST be first
        self._dlx = await self._channel.declare_exchange(
            DLX_NAME, aio_pika.ExchangeType.DIRECT, durable=True
        )

        # 2. Dead-letter queue — terminal destination, no DLX on it (avoid routing loops)
        self._dlq = await self._channel.declare_queue(DLQ_NAME, durable=True)
        await self._dlq.bind(self._dlx, routing_key=DLQ_ROUTING_KEY)

        # 3. Main events exchange
        self._exchange = await self._channel.declare_exchange(
            "infotriage.events", aio_pika.ExchangeType.TOPIC, durable=True
        )

        # 4. Primary queues — bound to events exchange, wired to DLX for dead-lettering
        #    x-dead-letter-routing-key=dead routes nacked messages to infotriage.dlq
        self._queues = {}
        for rk, q_name in ROUTING_KEY_TO_QUEUE.items():
            # rk = "item.ingested", q_name = "q.triage", etc.
            queue = await self._channel.declare_queue(
                q_name,
                durable=True,
                arguments={
                    "x-dead-letter-exchange": DLX_NAME,
                    "x-dead-letter-routing-key": DLQ_ROUTING_KEY,   # "dead" for all queues
                },
            )
            await queue.bind(self._exchange, rk)
            self._queues[rk] = queue

    async def publish(self, routing_key: str, item_id: str, payload: dict) -> None:
        """Publish payload to routing_key. Idempotent: same (routing_key, item_id) → no-op.

        Publisher confirms active (publisher_confirms=True on channel).
        NackError/UnroutableError raised on broker rejection.
        Security: payload is JSON-serialized; DSN never logged (T-03-01).
        """
        await self._ensure_connection()

        async with self._dedup_lock:
            key = (routing_key, item_id)
            if key in self._seen:
                return
            self._seen.add(key)

        assert self._exchange is not None
        message = aio_pika.Message(
            body=json.dumps(payload).encode(),
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            headers={"routing_key": routing_key, "item_id": item_id},
        )
        # mandatory=True triggers UnroutableError if no queue is bound to routing_key
        await self._exchange.publish(message, routing_key, mandatory=True)

    async def subscribe(self, routing_key: str) -> list[dict]:
        """Return all currently-queued payloads for routing_key in FIFO order.

        Uses a short-lived consumer (500ms window) to drain pending messages.
        Auto-acks each message after deserialization.
        Returns [] if the queue is empty or routing_key is unknown.
        """
        await self._ensure_connection()
        assert self._channel is not None

        queue_name = ROUTING_KEY_TO_QUEUE.get(routing_key)
        if not queue_name:
            log.warning("Unknown routing key: %s", routing_key)
            return []

        queue = await self._channel.get_queue(queue_name)
        messages: list[dict] = []

        async def _on_message(msg: aio_pika.IncomingMessage) -> None:
            async with msg.process():
                messages.append(json.loads(msg.body.decode()))

        consumer_tag = await queue.consume(_on_message)
        await asyncio.sleep(0.5)   # drain window — consume pending messages
        await queue.cancel(consumer_tag)
        return messages

    async def close(self) -> None:
        """Close AMQP connection gracefully."""
        if self._connection and not self._connection.is_closed:
            await self._connection.close()
