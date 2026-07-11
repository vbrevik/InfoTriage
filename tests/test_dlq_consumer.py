"""Tests for apps/dlq_consumer/worker.py."""
import datetime
import json
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
