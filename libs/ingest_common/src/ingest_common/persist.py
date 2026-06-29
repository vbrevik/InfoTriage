#!/usr/bin/env python3
"""persist.py — idempotent persist+publish helper for InfoTriage ingest adapters.

Implements RESEARCH Pattern 2 (get_item pre-check):
  - capture `existing = store.get_item(item.id)` BEFORE put_item
  - call `store.put_item(item)` unconditionally (upsert, last-write-wins)
  - if existing is None, publish to "item.ingested" and return True
  - else return False (no second publish — R6 idempotency)

Security: published payload exposes source, source_type, ts only — no DSN or
credentials ever flow through this path (T-04-01).
"""
from contracts import BusClient, Item
from store._protocol import Store


async def persist_and_publish(store: Store, bus: BusClient, item: Item) -> bool:
    """Upsert item and publish "item.ingested" exactly once for new items.

    Args:
        store:  Any Store-Protocol implementation (PostgresStore or InMemoryStore).
        bus:    Any BusClient-Protocol implementation (RabbitMQBus or InMemoryBus).
        item:   The Item to persist and optionally publish.

    Returns:
        True  — item was new (not previously stored); event was published.
        False — item already existed; no event published (R6 idempotency).

    Implementation note: store.get_item / store.put_item are synchronous methods
    on the Store Protocol — call them directly inside this async coroutine.
    Do NOT inspect put_item's return value for newness: put_item returns None
    (upsert semantics, last-write-wins). The pre-check on get_item is the sole
    newness signal (RESEARCH Finding 2 — the CONTEXT.md tuple-return description
    is stale and must not be used).
    """
    # RESEARCH Pattern 2: capture existing BEFORE put_item
    existing = store.get_item(item.id)

    # Unconditional upsert — last-write-wins (put_item returns None)
    store.put_item(item)

    if existing is None:
        # New item — publish to the ingest event stream
        await bus.publish(
            "item.ingested",
            item_id=item.id,
            payload={
                "source": item.source,
                "source_type": item.source_type,
                "ts": item.ts.isoformat(),
            },
        )
        return True

    # Duplicate — do NOT publish a second event (R6)
    return False
