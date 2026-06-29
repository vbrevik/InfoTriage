"""ingest_common — shared adapter toolkit for InfoTriage Phase 4 ingest containers.

Public API (Task 1):
    persist_and_publish(store, bus, item) -> bool
        Async. Idempotent persist + publish helper (RESEARCH Pattern 2).
        Returns True on new insert (event published), False on duplicate (no event).

Additional exports added by Task 2:
    make_trigger_app, build_store, build_bus
"""
from .persist import persist_and_publish

__all__ = [
    "persist_and_publish",
]
