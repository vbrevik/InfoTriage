#!/usr/bin/env python3
"""dlq-consumer — InfoTriage dead-letter queue consumer (Phase 7).

Subscribes to ``infotriage.dlq``, logs each poison message at ERROR level,
emits a ``feed.unhealthy`` event, and supports a consecutive-message alert
plus a replay mode that republishes messages to their original
exchange/routing-key.

Run modes:
    python worker.py              # consume DLQ forever
    python worker.py --replay     # drain DLQ and republish to original queues

Environment:
    INFOTRIAGE_AMQP_DSN  AMQP URL (default: amqp://infotriage:infotriage_rmq@rabbitmq:5672)
    LOG_LEVEL              DEBUG/INFO/WARNING/ERROR/CRITICAL (default INFO)

Notes:
- The CRITICAL alert fires after 10 consecutive DLQ messages (not a live
  queue-depth probe). This satisfies the "after N consecutive errors" gate.
- Replay preserves the original ``x-death`` headers; downstream consumers
  should treat them as historical metadata.
"""
import argparse
import asyncio
import datetime
import json
import logging
import os
from collections import deque

import aio_pika
from contracts import FeedUnhealthy, RabbitMQBus, setup_logging

setup_logging("dlq-consumer")
log = logging.getLogger(__name__)

DLQ_NAME = "infotriage.dlq"
EVENTS_EXCHANGE = "infotriage.events"
DEFAULT_AMQP_URL = "amqp://infotriage:infotriage_rmq@rabbitmq:5672"


class DLQConsumer:
    """Consume, log, and optionally replay dead-lettered messages."""

    def __init__(self, amqp_url: str):
        self.amqp_url = amqp_url
        self._connection: aio_pika.RobustConnection | None = None
        self._channel: aio_pika.RobustChannel | None = None
        self._dlq: aio_pika.RobustQueue | None = None
        self._events_exchange: aio_pika.RobustExchange | None = None
        self._consecutive_errors = 0

    async def connect(self) -> None:
        self._connection = await aio_pika.connect_robust(self.amqp_url)
        self._channel = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=10)
        self._dlq = await self._channel.get_queue(DLQ_NAME)
        self._events_exchange = await self._channel.get_exchange(EVENTS_EXCHANGE)

    async def close(self) -> None:
        if self._connection and not self._connection.is_closed:
            await self._connection.close()

    async def consume_forever(self) -> None:
        """Consume DLQ messages until cancelled."""
        await self.connect()
        assert self._dlq is not None
        await self._dlq.consume(self._on_message)
        log.info("DLQ consumer started on %s", DLQ_NAME)
        await asyncio.Future()  # run forever

    async def _on_message(self, message: aio_pika.IncomingMessage) -> None:
        async with message.process():
            await self._handle_message(message)

    async def _handle_message(self, message: aio_pika.IncomingMessage) -> None:
        try:
            body = json.loads(message.body.decode())
        except Exception:
            body = {"raw": message.body.decode(errors="replace")}

        x_death = message.headers.get("x-death", [])
        original_exchange: str | None = None
        original_routing_key: str | None = None
        if x_death:
            first = x_death[0]
            original_exchange = first.get("exchange")
            routing_keys = first.get("routing-keys", [])
            original_routing_key = routing_keys[0] if routing_keys else None

        log.error(
            "DLQ message received",
            extra={
                "original_exchange": original_exchange,
                "original_routing_key": original_routing_key,
                "body": body,
            },
        )

        event_type = body.get("event") or original_routing_key
        if event_type:
            await self._emit_feed_unhealthy(str(event_type), original_routing_key, body)

        self._consecutive_errors += 1
        if self._consecutive_errors >= 10:
            log.critical(
                "DLQ consecutive error threshold reached: %d messages",
                self._consecutive_errors,
            )
            self._consecutive_errors = 0

    async def _emit_feed_unhealthy(
        self,
        event_type: str,
        routing_key: str | None,
        body: dict,
    ) -> None:
        """Emit a feed.unhealthy event using the existing channel."""
        if self._events_exchange is None:
            log.error("Cannot emit feed.unhealthy: events exchange not available")
            return

        payload = FeedUnhealthy(
            event="feed.unhealthy",
            feed_url=routing_key or "dlq",
            feed_name=event_type,
            reason=f"DLQ message for {event_type}",
            ts=datetime.datetime.now(tz=datetime.timezone.utc),
        )
        message = aio_pika.Message(
            body=json.dumps(payload.model_dump(mode="json")).encode(),
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        )
        await self._events_exchange.publish(message, routing_key="feed.unhealthy")
        log.debug("Emitted feed.unhealthy for %s", event_type)

    async def replay(self, count: int = 1000) -> int:
        """Drain up to ``count`` DLQ messages and republish to original queues.

        Returns the number of messages replayed.
        """
        await self.connect()
        assert self._dlq is not None
        assert self._events_exchange is not None

        replayed = 0
        for _ in range(count):
            message = await self._dlq.get(no_ack=False)
            if message is None:
                break
            async with message.process():
                x_death = message.headers.get("x-death", [])
                if not x_death:
                    log.error("Cannot replay message without x-death headers")
                    continue
                first = x_death[0]
                original_exchange = first.get("exchange")
                routing_keys = first.get("routing-keys", [])
                original_routing_key = routing_keys[0] if routing_keys else None

                if not original_routing_key:
                    log.error("Cannot replay message without original routing key")
                    continue

                await self._events_exchange.publish(
                    aio_pika.Message(
                        body=message.body,
                        content_type="application/json",
                        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                        headers=message.headers,
                    ),
                    routing_key=original_routing_key,
                )
                log.info(
                    "Replayed message to %s:%s",
                    original_exchange,
                    original_routing_key,
                )
                replayed += 1

        log.info("DLQ replay complete: %d messages replayed", replayed)
        return replayed


async def main() -> None:
    parser = argparse.ArgumentParser(description="InfoTriage DLQ consumer")
    parser.add_argument(
        "--replay",
        action="store_true",
        help="Drain DLQ and republish messages to their original queues",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=1000,
        help="Maximum number of messages to replay (default: 1000)",
    )
    args = parser.parse_args()

    amqp_url = os.environ.get("INFOTRIAGE_AMQP_DSN", DEFAULT_AMQP_URL)
    consumer = DLQConsumer(amqp_url)

    try:
        if args.replay:
            replayed = await consumer.replay(count=args.count)
            print(f"Replayed {replayed} DLQ messages")
        else:
            await consumer.consume_forever()
    finally:
        await consumer.close()


if __name__ == "__main__":
    asyncio.run(main())
