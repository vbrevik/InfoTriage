"""store — InfoTriage persistence layer.

Exports the public API of the store package:
    Store         — @runtime_checkable typing.Protocol (R5)
    PostgresStore — psycopg3 + pgvector production implementation (R5, plan 03)
    InMemoryStore — dict-backed fake for tests (R5)
    render_atom   — pull-on-demand Atom projection, RSS/YT only (R7, D-04)

Usage:
    from store import Store, PostgresStore, InMemoryStore, render_atom
"""

from ._atom import render_atom
from ._inmemory import InMemoryStore
from ._postgres import PostgresStore
from ._protocol import Store

__all__ = [
    "Store",
    "PostgresStore",
    "InMemoryStore",
    "render_atom",
]
