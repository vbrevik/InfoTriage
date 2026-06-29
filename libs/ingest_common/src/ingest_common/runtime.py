#!/usr/bin/env python3
"""runtime.py — env-driven store and bus construction helpers.

Provides two factory functions that read credentials from environment variables
and return production-ready store/bus instances. No credentials are hard-coded
or logged (T-04-01, NF-6).

Environment variables consumed:
    INFOTRIAGE_PG_DSN       — PostgreSQL libpq connection string (required)
    INFOTRIAGE_BLOB_ROOT    — filesystem root for blob storage (default: data/blobs)
    INFOTRIAGE_AMQP_DSN     — AMQP URL for RabbitMQ (required; never logged)

Usage:
    from ingest_common import build_store, build_bus

    store = build_store()   # returns PostgresStore
    bus   = build_bus()     # returns RabbitMQBus
"""
import os
from pathlib import Path

from contracts import RabbitMQBus
from store import PostgresStore


def build_store() -> PostgresStore:
    """Construct a PostgresStore from environment variables.

    Reads:
        INFOTRIAGE_PG_DSN     — libpq connection string (required).
        INFOTRIAGE_BLOB_ROOT  — blob root directory (default: data/blobs).

    Returns:
        PostgresStore instance. Caller is responsible for using as a context
        manager (``with build_store() as store: ...``).

    Raises:
        KeyError: if INFOTRIAGE_PG_DSN is not set in the environment.
    """
    dsn = os.environ["INFOTRIAGE_PG_DSN"]
    blob_root = Path(os.environ.get("INFOTRIAGE_BLOB_ROOT", "data/blobs"))
    return PostgresStore(dsn=dsn, blob_root=blob_root)


def build_bus() -> RabbitMQBus:
    """Construct a RabbitMQBus from environment variables.

    Reads:
        INFOTRIAGE_AMQP_DSN — AMQP URL for RabbitMQ (required).

    Security: the DSN is read and passed directly to RabbitMQBus; it is never
    logged or written to any output (T-04-01, T-03-01).

    Returns:
        RabbitMQBus instance ready for async use.

    Raises:
        KeyError: if INFOTRIAGE_AMQP_DSN is not set in the environment.
    """
    amqp_url = os.environ["INFOTRIAGE_AMQP_DSN"]
    # Never emit this value to any logger — T-04-01 (contains credentials)
    return RabbitMQBus(amqp_url=amqp_url)
