#!/usr/bin/env python3
"""_bus.py — transport-swappable bus interface and in-memory implementation.

Defines BusClient as a typing.Protocol (structural subtyping — no inheritance
required) and InMemoryBus as a concrete implementation for in-process use.
The real AMQP transport (aio-pika) will be added in Phase 3; it only needs
to satisfy the BusClient Protocol.

Usage:
    from contracts import BusClient, InMemoryBus

    bus = InMemoryBus()
    bus.publish("item.ingested", item_id="abc123", payload={"n": 1})
    msgs = bus.subscribe("item.ingested")
    # [{"n": 1}]
"""
from typing import Protocol, runtime_checkable


@runtime_checkable
class BusClient(Protocol):
    """Transport-swappable bus interface. In-memory now; AMQP (Phase 3) later.

    Any class with matching publish/subscribe signatures satisfies this Protocol
    without explicit inheritance (PEP 544 structural subtyping).
    """

    def publish(self, routing_key: str, item_id: str, payload: dict) -> None:
        """Publish payload to routing_key. Idempotent: re-publishing same item_id is a no-op."""
        ...

    def subscribe(self, routing_key: str) -> list[dict]:
        """Return all payloads for routing_key in FIFO order. Returns [] if queue is empty."""
        ...


class InMemoryBus:
    """Concrete BusClient implementation for in-process use.

    Thread-safety: NOT thread-safe. Phase 1 scope only; Phase 3 replaces with
    aio-pika which handles concurrent access via asyncio event loop.

    Dedup: keyed on item_id (which equals Item.id — SHA-256 of source_type+url+title).
    A second publish with the same item_id is silently dropped.

    FIFO: messages are appended to a per-routing-key list and returned in order.
    """

    def __init__(self) -> None:
        self._queues: dict[str, list[dict]] = {}
        self._seen: set[str] = set()

    def publish(self, routing_key: str, item_id: str, payload: dict) -> None:
        if item_id in self._seen:
            return                                # dedup: same item_id → no-op
        self._seen.add(item_id)
        self._queues.setdefault(routing_key, []).append(payload)

    def subscribe(self, routing_key: str) -> list[dict]:
        return list(self._queues.get(routing_key, []))  # empty queue → [] (no-op)
