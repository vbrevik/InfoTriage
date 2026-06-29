#!/usr/bin/env python3
"""test_bus_rabbitmq.py — Smoke tests for RabbitMQ bus transport (Phase 3).

These tests require RabbitMQ running on :22001.
Run with: pytest tests/test_bus_rabbitmq.py -v -m rabbitmq
"""
import asyncio

import pytest
from contracts import RabbitMQBus


@pytest.mark.rabbitmq
def test_rabbitmq_connection() -> None:
    """Verify RabbitMQ :22001 connection works."""
    async def test():
        bus = RabbitMQBus()
        await bus._ensure_connection()
        assert bus._connection is not None
        assert not bus._connection.is_closed
        await bus.close()

    asyncio.run(test())


@pytest.mark.rabbitmq
def test_publish_consume() -> None:
    """Test publish/consume cycle."""
    async def test():
        bus = RabbitMQBus()
        await bus._ensure_connection()

        await bus.publish("item.ingested", "test_id_123", {"n": 42})
        await asyncio.sleep(0.5)

        messages = await bus.subscribe("item.ingested")
        assert len(messages) == 1, f"Expected 1 message, got {len(messages)}"
        assert messages[0]["n"] == 42

        await bus.close()

    asyncio.run(test())


@pytest.mark.rabbitmq
def test_dedup() -> None:
    """Same (routing_key, item_id) should be deduped."""
    async def test():
        bus = RabbitMQBus()
        await bus._ensure_connection()

        await bus.publish("item.ingested", "same_id", {"n": 1})
        await bus.publish("item.ingested", "same_id", {"n": 1})

        messages = await bus.subscribe("item.ingested")
        assert len(messages) == 1, f"Expected 1 message, got {len(messages)}"
        assert messages[0]["n"] == 1

        await bus.close()

    asyncio.run(test())
