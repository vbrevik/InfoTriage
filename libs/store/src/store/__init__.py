"""store — InfoTriage persistence layer.

Exports the public API of the store package. PostgresStore is intentionally
not exported here — it is added by plan 03 when _postgres.py exists.

render_atom is added by Task 3 of this plan when _atom.py is authored.

Usage:
    from store import Store, InMemoryStore, render_atom
"""
from ._inmemory import InMemoryStore
from ._protocol import Store

__all__ = [
    "Store",
    "InMemoryStore",
    # render_atom: added by Task 3 (_atom.py)
    # PostgresStore: added by plan 03 (_postgres.py)
]
