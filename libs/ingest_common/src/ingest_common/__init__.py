"""ingest_common — shared adapter toolkit for InfoTriage Phase 4 ingest containers.

Public API:
    persist_and_publish(store, bus, item) -> bool
        Async. Idempotent persist + publish helper (RESEARCH Pattern 2).
        Returns True on new insert (event published), False on duplicate (no event).

    make_trigger_app(ingest_coro, *, name) -> fastapi.FastAPI
        Builds the POST /run + GET /health FastAPI app with a single-instance lock (D-01).

    build_store() -> PostgresStore
        Reads INFOTRIAGE_PG_DSN + INFOTRIAGE_BLOB_ROOT from env.

    build_bus() -> RabbitMQBus
        Reads INFOTRIAGE_AMQP_DSN from env (never logged — T-04-01).
"""
from .persist import persist_and_publish
from .trigger import make_trigger_app
from .runtime import build_store, build_bus

__all__ = [
    "persist_and_publish",
    "make_trigger_app",
    "build_store",
    "build_bus",
]
