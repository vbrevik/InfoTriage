#!/usr/bin/env python3
"""_bus_rabbitmq.py — RabbitMQ bus transport for InfoTriage Phase 3.

Implements BusClient via aio-pika for async AMQP communication.
Uses durable topology with dead-letter queues (DLQ) for poison message handling.

Usage:
    from contracts import RabbitMQBus

    bus = RabbitMQBus("amqp://localhost:22001")
    await bus.publish("item.ingested", item_id="abc123", payload={"n": 1})
    messages = await bus.subscribe("item.ingested")
"""
import asyncio
import json
import logging
from typing import Any

import aio_pika
from aio_pika.abc import AbstractRobustConnection

from ._bus import BusClient

log = logging.getLogger(__name__)

RABBITMQ_DEFAULT_URL = "amqp://infotriage:infotriage_rmq@127.0.0.1:22001"


class RabbitMQBus:
    """Transport-swappable BusClient implementation using RabbitMQ.

    Dedup: keyed on (routing_key, item_id). Same as InMemoryBus.
    Topology:
        - infotriage.events (topic exchange, durable)
        - infotriage.dlx (direct exchange, durable) - dead-letter exchange
        - infotriage.dlq (queue, durable) - dead-letter queue
        - q.triage, q.brief, q.notify, q.ops (durable queues bound to events)

    Publisher confirms enabled, requeue=False for dead-lettering.
    """

    def __init__(self, amqp_url: str = RABBITMQ_DEFAULT_URL) -> None:
        self.amqp_url = amqp_url
        self._connection: AbstractRobustConnection | None = None
        self._channel: aio_pika.RobustChannel | None = None
        self._exchange: aio_pika.RobustExchange | None = None
        self._dedup_lock = asyncio.Lock()
        self._seen: set[tuple[str, str]] = set()

    async def _ensure_connection(self) -> None:
        """Establish or re-establish AMQP connection with exponential backoff."""
        if self._connection and not self._connection.is_closed:
            return

        max_delay = 30.0
        delay = 0.5

        while True:
            try:
                self._connection = await aio_pika.connect_robust(self.amqp_url)
                self._channel = await self._connection.channel()
                await self._channel.set_qos(prefetch_count=1)
                await self._declare_topology()
                break
            except Exception as e:
                log.warning(f"AMQP connection failed: {e}. Retrying in {delay:.1f}s")
                await asyncio.sleep(delay)
                delay = min(delay * 2, max_delay)

    async def _declare_topology(self) -> None:
        """Declare exchange/queue topology with DLX first to prevent 406 PRECONDITION_FAILED."""
        assert self._channel is not None

        # Declare DLX first (required by RabbitMQ)
        self._dlx = await self._channel.declare_exchange(
            "infotriage.dlx", aio_pika.ExchangeType.DIRECT, durable=True
        )
        self._dlq = await self._channel.declare_queue(
            "infotriage.dlq", durable=True, arguments={"dead_letter_exchange": "infotriage.dlx"}
        )
        await self._dlq.bind(self._dlx)

        # Declare main events exchange
        self._exchange = await self._channel.declare_exchange(
            "infotriage.events", aio_pika.ExchangeType.TOPIC, durable=True
        )

        # Declare and bind queues
        for queue_name, routing_key in [
            ("q.triage", "item.ingested"),
            ("q.brief", "verdict.ready"),
            ("q.notify", "sab.published"),
            ("q.ops", "feed.unhealthy"),
        ]:
            queue = await self._channel.declare_queue(
                queue_name,
                durable=True,
                arguments={
                    "x-dead-letter-exchange": "infotriage.dlx",
                    "x-dead-letter-routing-key": routing_key,
                },
            )
            await queue.bind(self._exchange, routing_key)

    async def publish(self, routing_key: str, item_id: str, payload: dict) -> None:
        """Publish payload to routing_key. Idempotent via dedup."""
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
        await self._exchange.publish(message, routing_key, mandatory=True)

    async def subscribe(self, routing_key: str) -> list[dict]:
        """Return all payloads for routing_key in FIFO order."""
        await self._ensure_connection()

        assert self._channel is not None
        queue_name = f"q.{routing_key.split('.')[-1]}"

        routing_key_to_queue = {
            "item.ingested": "q.triage",
            "verdict.ready": "q.brief",
            "sab.published": "q.notify",
            "feed.unhealthy": "q.ops",
        }
        queue_name = routing_key_to_queue.get(routing_key, queue_name)

        messages = []
        queue = await self._channel.get_queue(queue_name)

        async def on_message(msg: aio_pika.IncomingMessage) -> None:
            async with msg.process():
                body = json.loads(msg.body.decode())
                messages.append(body)

        await queue.consume(on_message)
        await asyncio.sleep(0.5)
        return messages

    async def close(self) -> None:
        """Close AMQP connection gracefully."""
        if self._connection:
            await self._connection.close()
