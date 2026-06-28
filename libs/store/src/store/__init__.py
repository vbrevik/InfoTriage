"""store — InfoTriage persistence layer.

Exports the public API of the store package:
    Store       — @runtime_checkable typing.Protocol (R5)
    InMemoryStore — dict-backed fake for tests (R5)
    render_atom — pull-on-demand Atom projection, RSS/YT only (R7, D-04)

PostgresStore is intentionally not exported here — it is added by plan 03
when _postgres.py exists.

Usage:
    from store import Store, InMemoryStore, render_atom
"""
from ._atom import render_atom
from ._inmemory import InMemoryStore
from ._protocol import Store

__all__ = [
    "Store",
    "InMemoryStore",
    "render_atom",
    # PostgresStore: added by plan 03 (_postgres.py)
]
