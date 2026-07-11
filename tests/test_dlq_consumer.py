"""Tests for apps/dlq_consumer/worker.py."""
import datetime
import json
import logging
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.dlq_consumer import worker as dlq_worker


@pytest.fixture(autouse=True)
def _patch_aio_pika_connect():
    """Prevent DLQ consumer tests from touching a real RabbitMQ broker."""
    with patch("apps.dlq_consumer.worker.aio_pika.connect_robust") as mock_connect:
        mock_conn = AsyncMock()
        mock_connect.return_value = mock_conn
        yield mock_connect


class _FakeMessage:
    """Minimal aio-pika IncomingMessage stand-in."""

    def __init__(self, body: bytes, headers: dict):
        self.body = body
        self.headers = headers

    @asynccontextmanager
    async def process(self):
        yield self


@pytest.fixture
def consumer():
    return dlq_worker.DLQConsumer("amqp://test")


@pytest.mark.asyncio
async def test_replay_republishs_to_original_routing_key(consumer):
    """Replay reads x-death headers and republishes to the original routing key."""
    consumer._channel = MagicMock()
    consumer._events_exchange = AsyncMock()

    message = _FakeMessage(
        body=json.dumps({"event": "verdict.ready", "item_id": "abc"}).encode(),
        headers={
            "x-death": [
                {
                    "exchange": "infotriage.events",
                    "routing-keys": ["verdict.ready"],
                }
            ]
        },
    )
    consumer._dlq = AsyncMock()
    consumer._dlq.get = AsyncMock(return_value=message)
    consumer.connect = AsyncMock()

    replayed = await consumer.replay(count=1)

    assert replayed == 1
    consumer._events_exchange.publish.assert_awaited_once()
    args, kwargs = consumer._events_exchange.publish.call_args
    published_message = args[0]
    routing_key = kwargs["routing_key"]
    assert routing_key == "verdict.ready"
    assert published_message.body == message.body


@pytest.mark.asyncio
async def test_replay_skips_message_without_x_death(consumer):
    """Replay skips messages that lack x-death headers."""
    consumer._channel = MagicMock()
    consumer._events_exchange = AsyncMock()

    message = _FakeMessage(
        body=json.dumps({"event": "verdict.ready"}).encode(),
        headers={},
    )
    consumer._dlq = AsyncMock()
    consumer._dlq.get = AsyncMock(return_value=message)
    consumer.connect = AsyncMock()

    replayed = await consumer.replay(count=1)

    assert replayed == 0
    consumer._events_exchange.publish.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_message_logs_and_emits_feed_unhealthy(consumer):
    """A DLQ message is logged and emits a feed.unhealthy event."""
    consumer._events_exchange = AsyncMock()

    message = _FakeMessage(
        body=json.dumps({"event": "verdict.ready", "item_id": "abc"}).encode(),
        headers={
            "x-death": [
                {
                    "exchange": "infotriage.events",
                    "routing-keys": ["verdict.ready"],
                }
            ]
        },
    )

    with patch("apps.dlq_consumer.worker.log") as mock_log:
        await consumer._handle_message(message)

    mock_log.error.assert_called_once()
    consumer._events_exchange.publish.assert_awaited_once()
    args, kwargs = consumer._events_exchange.publish.call_args
    assert kwargs["routing_key"] == "feed.unhealthy"


@pytest.mark.asyncio
async def test_handle_message_without_x_death_still_emits_feed_unhealthy(consumer):
    """A DLQ message without x-death headers is still logged and emits feed.unhealthy."""
    consumer._events_exchange = AsyncMock()

    message = _FakeMessage(
        body=json.dumps({"event": "verdict.ready", "item_id": "abc"}).encode(),
        headers={},
    )

    with patch("apps.dlq_consumer.worker.log") as mock_log:
        await consumer._handle_message(message)

    mock_log.error.assert_called_once()
    consumer._events_exchange.publish.assert_awaited_once()
    args, kwargs = consumer._events_exchange.publish.call_args
    assert kwargs["routing_key"] == "feed.unhealthy"


@pytest.mark.asyncio
async def test_handle_message_critical_after_threshold(consumer):
    """After 10 consecutive DLQ messages, a CRITICAL log is emitted."""
    consumer._events_exchange = AsyncMock()

    message = _FakeMessage(
        body=json.dumps({"event": "verdict.ready", "item_id": "abc"}).encode(),
        headers={},
    )

    with patch("apps.dlq_consumer.worker.log") as mock_log:
        for _ in range(10):
            await consumer._handle_message(message)

        mock_log.critical.assert_called_once()
        assert "threshold" in mock_log.critical.call_args[0][0].lower()

    # After the threshold, the counter resets and the next message does not immediately CRITICAL
    with patch("apps.dlq_consumer.worker.log") as mock_log:
        await consumer._handle_message(message)
        mock_log.critical.assert_not_called()


@pytest.mark.asyncio
async def test_emit_feed_unhealthy_skips_validation_error(consumer, caplog):
    """`apps/dlq_consumer/worker.py::_emit_feed_unhealthy` is constructed on
    every DLQ message + every depth-breach tick. The `reason` field is
    `f"DLQ message for {event_type}"` -- bounded in practice, but if
    `event_type` carries an absurdly-long value (1KB routing key from
    upstream, or a depth label from the depth-probe that grew past 120 chars),
    `Field(max_length=120)` will fail validation. With the inner guard
    (mirror of 44f8b9d Option B), the emit is logged-and-skipped via
    `log.error("Discarding feed.unhealthy event ...")`, and the consumer loop
    survives -- the DLQ process MUST stay alive. Without the guard, the
    ValidationError propagates out of `_on_message`'s `message.process()`
    context and re-NACKs the message back onto DLQ -> infinite nack-cycle.

    This test pins post-44f8b9d runtime behavior for the dlq consumer:
    when emit body is malformed, `_emit_feed_unhealthy` does NOT raise +
    does NOT publish + DOES log the discard at ERROR.
    """
    consumer._events_exchange = MagicMock()
    consumer._events_exchange.publish = AsyncMock()

    # 4-char prefix + 200-char depth number = 226 chars, well past max_length=120.
    long_event_type = "dlq.depth.critical:depth=" + ("9" * 200)

    with caplog.at_level(logging.ERROR):
        # Must NOT raise -- the inner guard catches ValidationError.
        await consumer._emit_feed_unhealthy(
            event_type=long_event_type,
            routing_key="dlq.depth",
            body={},
        )

    # Inner guard prevented the publish (log-and-skip pattern).
    consumer._events_exchange.publish.assert_not_called()
    # + an ERROR-severity `Discarding feed.unhealthy event` log line was emitted.
    discard_logs = [
        rec for rec in caplog.records
        if rec.levelno >= logging.ERROR
        and "Discarding feed.unhealthy event" in rec.message
    ]
    assert len(discard_logs) >= 1, (
        "inner guard must emit a Discarding ERROR log line; got 0 "
        "(ValidationError would propagate uncaught, triggering a dlq nack-cycle)"
    )
