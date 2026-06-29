"""contracts — InfoTriage shared schemas, codec, and bus interface.

Single source of truth for all InfoTriage apps:

    from contracts import Item
    from contracts import ItemIngested, VerdictReady, SabPublished, FeedUnhealthy
    from contracts import to_frontmatter, from_frontmatter
    from contracts import BusClient, InMemoryBus
"""
from ._item import Item
from ._events import ItemIngested, VerdictReady, SabPublished, FeedUnhealthy
from ._codec import to_frontmatter, from_frontmatter
from ._bus import BusClient, InMemoryBus
from ._bus_rabbitmq import RabbitMQBus

__all__ = [
    "Item",
    "ItemIngested",
    "VerdictReady",
    "SabPublished",
    "FeedUnhealthy",
    "to_frontmatter",
    "from_frontmatter",
    "BusClient",
    "InMemoryBus",
    "RabbitMQBus",
]
