"""test_dlq_depth_probe.py — gap-closure tests for apps/dlq_consumer depth probe.

Phase 7 07-02: the dlq_consumer now watches the live RabbitMQ management API
and emits a CRITICAL alert when queue depth exceeds the operator-tunable
threshold. The connectivity-failure path MUST NOT take down the consumer
loop (best-effort log-and-continue posture).

MUST be a unit test (NOT db_live) so it runs on every pytest invocation.
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch


def _make_mock_response(messages: int, messages_ready: int | None = None) -> MagicMock:
    """Build a MagicMock of httpx.Response for the depth probe's mgmt-API GET."""
    if messages_ready is None:
        messages_ready = messages
    resp = MagicMock()
    resp.json.return_value = {
        "messages": messages,
        "messages_ready": messages_ready,
    }
    resp.raise_for_status = MagicMock()
    return resp


def _run(coro):
    """Drive an async coroutine from a synchronous test (Python 3.12+ friendly).

    `asyncio.get_event_loop().run_until_complete(coro)` fails on 3.12+ because
    no event loop is auto-created in the main thread; `asyncio.run()` is the
    supported replacement and re-executes from the standard library at
    asyncio.runner's discretion.
    """
    return asyncio.run(coro)


def test_probe_below_threshold_is_silent():
    """A depth below the threshold logs INFO but does not raise or alert."""
    from apps.dlq_consumer.worker import DLQConsumer

    consumer = DLQConsumer(amqp_url="amqp://x:y@example.invalid/")
    consumer._events_exchange = MagicMock()
    with patch("apps.dlq_consumer.worker.httpx.AsyncClient") as Client:
        Client.return_value.__aenter__ = AsyncMock(
            return_value=MagicMock(get=AsyncMock(return_value=_make_mock_response(10)))
        )
        Client.return_value.__aexit__ = AsyncMock(return_value=None)
        with patch("apps.dlq_consumer.worker.log") as log_mock:
            _run(consumer._probe_queue_depth(threshold=50))
        log_mock.critical.assert_not_called()
        log_mock.error.assert_not_called()


def test_probe_at_threshold_emits_critical_and_feed_unhealthy():
    """A depth at or above the threshold fires CRITICAL + emits feed.unhealthy."""
    from apps.dlq_consumer.worker import DLQConsumer

    consumer = DLQConsumer(amqp_url="amqp://x:y@example.invalid/")
    exchange_mock = MagicMock()
    exchange_mock.publish = AsyncMock()
    consumer._events_exchange = exchange_mock

    with patch("apps.dlq_consumer.worker.httpx.AsyncClient") as Client:
        Client.return_value.__aenter__ = AsyncMock(
            return_value=MagicMock(get=AsyncMock(return_value=_make_mock_response(75)))
        )
        Client.return_value.__aexit__ = AsyncMock(return_value=None)
        with patch("apps.dlq_consumer.worker.log") as log_mock:
            _run(consumer._probe_queue_depth(threshold=50))

    log_mock.critical.assert_called()
    assert (
        exchange_mock.publish.await_count == 1
    ), "feed.unhealthy event must be emitted on threshold breach."
    # The published message body's reason must surface the depth value so the
    # downstream operator/consumer can grep for it.
    call = exchange_mock.publish.await_args
    msg = call.kwargs.get("message") or call.args[0]
    body = json.loads(msg.body.decode())
    assert body["event"] == "feed.unhealthy"
    assert (
        "75" in body["reason"] or "depth=75" in body["reason"]
    ), f"reason must include the depth value; got: {body['reason']!r}"


def test_probe_connectivity_failure_is_warning_only():
    """A network failure (RabbitMQ mgmt API down) logs WARNING and does not raise."""
    from apps.dlq_consumer.worker import DLQConsumer

    consumer = DLQConsumer(amqp_url="amqp://x:y@example.invalid/")
    consumer._events_exchange = MagicMock()

    with patch("apps.dlq_consumer.worker.httpx.AsyncClient") as Client:
        Client.return_value.__aenter__ = AsyncMock(
            return_value=MagicMock(
                get=AsyncMock(side_effect=ConnectionError("mgmt API down"))
            )
        )
        Client.return_value.__aexit__ = AsyncMock(return_value=None)
        with patch("apps.dlq_consumer.worker.log") as log_mock:
            # Must NOT raise — when the depth loop calls this, it catches and
            # logs WARNING itself; here we just verify the probe is well-behaved.
            _run(consumer._probe_queue_depth(threshold=50))

    log_mock.critical.assert_not_called()
    log_mock.warning.assert_called()


def test_probe_alerts_on_total_messages_not_just_ready():
    """Per the thinker verdict: 'messages' (total incl. unacked) is the right signal.

    A consumer reading via mgmt API that ignores unacked can hide a stuck
    process. The threshold check uses the 'messages' field; the response can
    have messages=50, messages_ready=10 (40 in unacked limbo) — we should
    still alert.
    """
    from apps.dlq_consumer.worker import DLQConsumer

    consumer = DLQConsumer(amqp_url="amqp://x:y@example.invalid/")
    exchange_mock = MagicMock()
    exchange_mock.publish = AsyncMock()
    consumer._events_exchange = exchange_mock

    # 50 total messages but only 5 ready (45 stuck unacked) — should still alert.
    with patch("apps.dlq_consumer.worker.httpx.AsyncClient") as Client:
        Client.return_value.__aenter__ = AsyncMock(
            return_value=MagicMock(
                get=AsyncMock(
                    return_value=_make_mock_response(messages=50, messages_ready=5)
                )
            )
        )
        Client.return_value.__aexit__ = AsyncMock(return_value=None)
        with patch("apps.dlq_consumer.worker.log") as log_mock:
            _run(consumer._probe_queue_depth(threshold=50))

    # Should ALERT (50 >= 50) even though messages_ready was only 5.
    log_mock.critical.assert_called()
    assert exchange_mock.publish.await_count == 1
