#!/usr/bin/env python3
"""dlq-consumer — InfoTriage dead-letter queue consumer (Phase 7).

Subscribes to ``infotriage.dlq``, logs each poison message at ERROR level,
emits a ``feed.unhealthy`` event, and supports two threshold policies:

1. **Consecutive-message**: after 10 consecutive DLQ messages, log CRITICAL
   and reset (per-message rate signal — Phase 7 07-01).
2. **Live queue-depth**: periodic GET of the RabbitMQ Management API
   (``/api/queues/{vhost}/{queue}``). When ``messages`` >= ``DLQ_DEPTH_CRITICAL_N``
   (default 50), log CRITICAL + emit ``feed.unhealthy`` (queue-load signal —
   Phase 7 07-02). Connectivity failures log WARNING and continue; never take
   down the consumer.

Run modes:
    python worker.py              # consume DLQ + depth probe forever
    python worker.py --replay     # drain DLQ and republish to original queues

Environment:
    INFOTRIAGE_AMQP_DSN              AMQP URL (default amqp://infotriage:infotriage_rmq@rabbitmq:5672)
    RABBITMQ_MGMT_URL                HTTP mgmt URL (default derived from *_AMQP_DSN)
    RABBITMQ_MGMT_USER               mgmt-API basic-auth user (default $RABBITMQ_DEFAULT_USER = infotriage)
    RABBITMQ_MGMT_PASS               mgmt-API basic-auth password
    RABBITMQ_MGMT_VHOST              vhost (default "/")
    DLQ_DEPTH_PROBE_INTERVAL_S       probe cadence in seconds (default 30)
    DLQ_DEPTH_CRITICAL_N             threshold in messages (default 50)
    LOG_LEVEL                       DEBUG/INFO/WARNING/ERROR/CRITICAL (default INFO)
"""
import argparse
import asyncio
import datetime
import json
import logging
import os
from urllib.parse import quote as _quote_vhost, urlparse

import aio_pika
import httpx
from contracts import FeedUnhealthy, RabbitMQBus, setup_logging
from pydantic import ValidationError

setup_logging("dlq-consumer")
log = logging.getLogger(__name__)

DLQ_NAME = "infotriage.dlq"
EVENTS_EXCHANGE = "infotriage.events"
DEFAULT_AMQP_URL = "amqp://infotriage:infotriage_rmq@rabbitmq:5672"
DEPTH_PROBE_DEFAULT_INTERVAL_S = 30
DEPTH_PROBE_DEFAULT_THRESHOLD_N = 50
MGMT_API_DEFAULT_PORT = 15672


def _default_mgmt_url(amqp_url: str) -> str:
    """Derive the mgmt-API URL from the AMQP URL (host-only — port becomes 15672)."""
    parsed = urlparse(amqp_url)
    if not parsed.hostname:
        return "http://rabbitmq:15672"
    return f"http://{parsed.hostname}:{MGMT_API_DEFAULT_PORT}"


class DLQConsumer:
    """Consume, log, optionally replay, and live-probe rabbitmq DLQ depth."""

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
        """Consume the DLQ + run a periodic depth probe; runs until cancelled.

        Both run concurrently via asyncio.gather:
        - The consumer is "live" via aio_pika.RobustQueue.consume(); the
          sentinel future in gather keeps the coroutine alive without polling.
        - The depth probe runs on a fixed interval (best-effort; never raises).
        """
        await self.connect()
        assert self._dlq is not None
        await self._dlq.consume(self._on_message)
        log.info("DLQ consumer started on %s (depth probe enabled)", DLQ_NAME)
        await asyncio.gather(
            asyncio.Future(),          # sentinel — the consumer stays attached
            self._depth_probe_loop(),
        )

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

        # Inner try/except ValidationError (Option B, mirror of 44f8b9d fix): the
        # canonical `FeedUnhealthy` model enforces `Field(max_length=120)` on `reason`.
        # If `event_type` is unusually long (e.g.
        # `f"dlq.depth.critical:depth={"9"*200}"` from a runaway depth probe, or
        # a 1KB routing key from upstream), `reason=f"DLQ message for {event_type}"`
        # exceeds 120 chars, and the unguarded construction would propagate
        # ValidationError out of `_handle_message` -> `_on_message` ->
        # `message.process()` nacks the DLQ message (default requeue=False
        # -> aio_pika's `process()` nack path), causing a silent nack-cycle where
        # the bad message keeps coming back to DLQ. Trap the ValidationError
        # locally so the consumer loop stays alive + the bad-reason event is
        # logged-and-skipped.
        try:
            payload = FeedUnhealthy(
                event="feed.unhealthy",
                feed_url=routing_key or "dlq",
                feed_name=event_type,
                reason=f"DLQ message for {event_type}",
                ts=datetime.datetime.now(tz=datetime.timezone.utc),
            )
        except ValidationError as e:
            log.error(
                "Discarding feed.unhealthy event for event_type=%s due to schema "
                "validation failure (reason > 120 chars? malformed ts?): %s",
                event_type, e,
            )
            return
        message = aio_pika.Message(
            body=json.dumps(payload.model_dump(mode="json")).encode(),
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        )
        await self._events_exchange.publish(message, routing_key="feed.unhealthy")
        log.debug("Emitted feed.unhealthy for %s", event_type)

    # ---- Live queue-depth probe (Phase 7 07-02) --------------------------------
    async def _depth_probe_loop(self) -> None:
        """Periodic best-effort probe of the live RabbitMQ-mgmt API.

        Each probe is self-contained: catches its own connectivity errors
        and logs WARNING; the loop just sleeps. RabbitMQ transient outages
        must NOT take down the consumer.
        """
        interval_s = int(
            os.environ.get(
                "DLQ_DEPTH_PROBE_INTERVAL_S",
                str(DEPTH_PROBE_DEFAULT_INTERVAL_S),
            )
        )
        while True:
            await self._probe_queue_depth()
            await asyncio.sleep(interval_s)

    async def _probe_queue_depth(
        self,
        *,
        threshold: int | None = None,
        mgmt_url: str | None = None,
        mgmt_user: str | None = None,
        mgmt_pass: str | None = None,
        mgmt_vhost: str | None = None,
    ) -> None:
        """Probe one mgmt-API cycle and emit alerts on breach.

        Logs INFO on every successful probe; emits CRITICAL + ``feed.unhealthy``
        when ``messages >= threshold``. Connectivity failures are absorbed with
        a WARNING log so the consumer loop keeps running. Never raises.
        """
        threshold = int(
            threshold
            if threshold is not None
            else os.environ.get(
                "DLQ_DEPTH_CRITICAL_N", str(DEPTH_PROBE_DEFAULT_THRESHOLD_N)
            )
        )
        mgmt_url = mgmt_url or os.environ.get(
            "RABBITMQ_MGMT_URL",
            _default_mgmt_url(self.amqp_url),
        )
        mgmt_user = mgmt_user or os.environ.get(
            "RABBITMQ_MGMT_USER",
            os.environ.get("RABBITMQ_DEFAULT_USER", "infotriage"),
        )
        mgmt_pass = mgmt_pass or os.environ.get(
            "RABBITMQ_MGMT_PASS",
            os.environ.get("RABBITMQ_DEFAULT_PASS", "infotriage_rmq"),
        )
        mgmt_vhost = mgmt_vhost or os.environ.get("RABBITMQ_MGMT_VHOST", "/")

                # The default vhost "/" MUST be URL-encoded as %2F per the RabbitMQ
        # mgmt-API contract; an unencoded literal "/" yields the malformed
        # path `/api/queues///<queue>` and a 404. Use safe='' so every char
        # is encoded (no slashes leak through). (Phase 7 07-03 fix.)
        full_url = f"{mgmt_url.rstrip('/')}/api/queues/{_quote_vhost(mgmt_vhost, safe='')}/{DLQ_NAME}"
        auth = (mgmt_user, mgmt_pass)

        try:
            async with httpx.AsyncClient(timeout=5.0, auth=auth) as client:
                resp = await client.get(full_url)
                resp.raise_for_status()
                data = resp.json()
                # Use "messages" (total incl. unacked) — THINKER Q5: alerting on
                # messages_ready would hide a stuck consumer holding messages in
                # unacked limbo.
                depth = int(data.get("messages", 0))
        except Exception as exc:
            log.warning(
                "DLQ depth probe failed: %s: %s",
                type(exc).__name__,
                str(exc)[:200],
            )
            return

        log.info(
            "DLQ depth: %d messages (threshold %d, queue %s)",
            depth, threshold, DLQ_NAME,
        )

        if depth >= threshold:
            log.critical(
                "DLQ depth threshold breached: %d >= %d on %s",
                depth, threshold, DLQ_NAME,
            )
            # Surface the depth value in the event_type so the FeedUnhealthy
            # `reason` field (which embeds event_type) carries the breach count
            # for grep-ability: "DLQ message for dlq.depth.critical:depth=75".
            await self._emit_feed_unhealthy(
                event_type=f"dlq.depth.critical:depth={depth}",
                routing_key="dlq.depth",
                body={"queue": DLQ_NAME, "depth": depth, "threshold": threshold},
            )

    # ---- Replay --------------------------------------------------------------
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
