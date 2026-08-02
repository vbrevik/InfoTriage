#!/usr/bin/env python3
"""alerting_worker.py — CAT I verdict.ready/sab.published -> authenticated
ntfy push, gated by dedupe (12-04) and the sliding-window throttle (12-05),
with an hourly PMESII-grouped digest of anything the throttle suppressed.

bus -> q.alerting -> emitter (claim, throttle) -> Store -> 7-field payload ->
authenticated POST to the ntfy cnr-cat-i topic, plus a third coroutine
(`run_digest_tick`) that ticks hourly in-process and publishes a grouped
digest when suppressed rows exist. No retry/DLX yet — that is a later
expansion plan.

Usage:
    python apps/alerting/alerting_worker.py --dsn ... --amqp-dsn ...
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

from contracts import RabbitMQBus, setup_logging
from store import PostgresStore

from digest import DEFAULT_DIGEST_INTERVAL, run_digest_tick
from emitter import run_consumer
from outbox import NtfyClient

setup_logging("alerting")
log = logging.getLogger(__name__)

HEALTH_HOST = "0.0.0.0"
HEALTH_PORT = 22050


# ---------------------------------------------------------------------------
# Health server (copied verbatim from apps/wiki/wiki_worker.py)
# ---------------------------------------------------------------------------


async def _handle_health(
    reader: asyncio.StreamReader, writer: asyncio.StreamWriter
) -> None:
    """Serve a liveness-only GET /health -> 200."""
    await reader.read(1024)
    body = b"OK"
    response = (
        b"HTTP/1.1 200 OK\r\n"
        b"Content-Length: " + str(len(body)).encode() + b"\r\n"
        b"Connection: close\r\n\r\n" + body
    )
    writer.write(response)
    await writer.drain()
    writer.close()


async def run_health_server(host: str = HEALTH_HOST, port: int = HEALTH_PORT) -> None:
    """Serve the liveness-only /health endpoint forever."""
    server = await asyncio.start_server(_handle_health, host, port)
    async with server:
        await server.serve_forever()


# ---------------------------------------------------------------------------
# CLI / entrypoint
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="InfoTriage CNR alerting worker")
    parser.add_argument(
        "--dsn",
        default=os.environ.get("INFOTRIAGE_PG_DSN"),
        help="Postgres DSN (default INFOTRIAGE_PG_DSN)",
    )
    parser.add_argument(
        "--amqp-dsn",
        default=os.environ.get(
            "INFOTRIAGE_AMQP_DSN", "amqp://infotriage:infotriage_rmq@127.0.0.1:22001"
        ),
        help="RabbitMQ DSN",
    )
    parser.add_argument(
        "--ntfy-url",
        default=os.environ.get("NTFY_URL", "http://ntfy:80"),
        help="ntfy base URL (default NTFY_URL)",
    )
    parser.add_argument(
        "--digest-interval",
        type=int,
        default=int(
            os.environ.get(
                "INFOTRIAGE_ALERTING_DIGEST_INTERVAL", DEFAULT_DIGEST_INTERVAL
            )
        ),
        help="Hourly digest tick interval in seconds (default 3600, D-03)",
    )
    parser.add_argument(
        "--health-host",
        default=os.environ.get("INFOTRIAGE_ALERTING_HEALTH_HOST", HEALTH_HOST),
        help="Health server host",
    )
    parser.add_argument(
        "--health-port",
        type=int,
        default=int(os.environ.get("INFOTRIAGE_ALERTING_HEALTH_PORT", HEALTH_PORT)),
        help="Health server port",
    )
    return parser


async def _run_async_mode(args: argparse.Namespace, ntfy_token: str) -> None:
    """Open the Store + bus + ntfy client and gather health server + consumer."""
    blob_root = Path(os.environ.get("INFOTRIAGE_BLOB_ROOT", "/data/blobs"))
    topic = os.environ.get("NTFY_TOPIC_PREFIX", "cnr-cat-i")

    with PostgresStore(dsn=args.dsn, blob_root=blob_root) as store:
        client = NtfyClient(args.ntfy_url, ntfy_token, topic)
        bus = RabbitMQBus(amqp_url=args.amqp_dsn)
        tasks = [
            run_health_server(host=args.health_host, port=args.health_port),
            run_consumer(bus, store, client),
            run_digest_tick(store, client, interval=args.digest_interval),
        ]
        try:
            await asyncio.gather(*tasks)
        finally:
            await bus.close()


def main() -> None:
    args = _build_parser().parse_args()

    # Fail-closed startup (SPEC R6): DSN, AMQP DSN, and NTFY_TOKEN are all
    # required before any connection is opened.
    if not args.dsn:
        print("ERROR: --dsn or INFOTRIAGE_PG_DSN required", file=sys.stderr)
        sys.exit(1)

    if not args.amqp_dsn:
        print(
            "ERROR: --amqp-dsn or INFOTRIAGE_AMQP_DSN required",
            file=sys.stderr,
        )
        sys.exit(1)

    ntfy_token = os.environ.get("NTFY_TOKEN", "").strip()
    if not ntfy_token:
        print(
            "ERROR: NTFY_TOKEN required (bearer token for cnr-cat-i publish)",
            file=sys.stderr,
        )
        sys.exit(1)

    asyncio.run(_run_async_mode(args, ntfy_token))


if __name__ == "__main__":
    main()
