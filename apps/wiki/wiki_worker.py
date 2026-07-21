#!/usr/bin/env python3
"""wiki_worker.py — periodic/event-driven auto-wiki worker (Phase 10 Wave 1).

Generates/updates standing Obsidian wiki pages for the most-linked canonical
entities. Can run once, on a schedule, or in response to ``verdict.ready`` events.

Usage:
    python apps/wiki/wiki_worker.py --mode once          # generate once and exit
    python apps/wiki/wiki_worker.py --mode periodic      # regenerate every hour (default)
    python apps/wiki/wiki_worker.py --mode events         # regenerate on verdict.ready
"""
from __future__ import annotations

import argparse
import asyncio
import datetime
import logging
import os
import sys
from pathlib import Path
from typing import Callable

from contracts import RabbitMQBus, setup_logging
from generator import WikiGenerator
from store import PostgresStore

setup_logging("wiki")
log = logging.getLogger(__name__)

HEALTH_HOST = "0.0.0.0"
HEALTH_PORT = 22040
DEFAULT_INTERVAL = 3600
DEFAULT_TOP_N = 10


# ---------------------------------------------------------------------------
# Target selection
# ---------------------------------------------------------------------------


def _top_entities(store, *, top_n: int = DEFAULT_TOP_N, since=None):
    """Return the top-N active canonical entities for wiki generation."""
    kwargs: dict = {"limit": top_n}
    if since is not None:
        kwargs["since"] = since
    entities = store.get_active_entities(**kwargs)
    return [e["name"] for e in entities if e.get("name")]


# ---------------------------------------------------------------------------
# Page generation
# ---------------------------------------------------------------------------


def run_once(
    store,
    vault_path: Path,
    *,
    top_n: int = DEFAULT_TOP_N,
    since=None,
    embed=None,
    llm=None,
) -> list[Path]:
    """Generate wiki pages for the top-N active entities.

    Returns the list of paths written.
    """
    generator = WikiGenerator(store, vault_path, embed=embed, llm=llm)
    subjects = _top_entities(store, top_n=top_n, since=since)
    written: list[Path] = []
    for subject in subjects:
        try:
            path = generator.generate_page(subject)
            log.info("wiki page written: %s", path)
            written.append(path)
        except Exception as exc:
            log.error("failed to generate wiki page for %s: %s", subject, exc)
    return written


# ---------------------------------------------------------------------------
# Periodic driver
# ---------------------------------------------------------------------------


async def run_periodic(
    store,
    vault_path: Path,
    *,
    interval: int = DEFAULT_INTERVAL,
    top_n: int = DEFAULT_TOP_N,
    embed=None,
    llm=None,
) -> None:
    """Generate wiki pages periodically forever."""
    while True:
        try:
            since = datetime.datetime.now(
                tz=datetime.timezone.utc
            ) - datetime.timedelta(seconds=interval)
            await asyncio.to_thread(
                run_once,
                store,
                vault_path,
                top_n=top_n,
                since=since,
                embed=embed,
                llm=llm,
            )
        except Exception as exc:
            log.error("wiki worker iteration failed: %s", exc)
        log.info("sleeping for %ds before next wiki generation", interval)
        await asyncio.sleep(interval)


# ---------------------------------------------------------------------------
# Event-driven driver (verdict.ready)
# ---------------------------------------------------------------------------


async def _on_verdict_ready(
    message,
    store,
    vault_path: Path,
    *,
    top_n: int = DEFAULT_TOP_N,
    embed=None,
    llm=None,
) -> None:
    """Handle a single verdict.ready event by refreshing the active wiki pages.

    The event payload is JSON with an ``item_id`` header. Rather than regenerating
    only the affected item's entities (which requires extra store queries), the
    worker refreshes the top-N active entities. This keeps the event handler
    simple and deterministic while still ensuring new verdicts are reflected in
    the standing wiki pages.
    """
    async with message.process():
        item_id = message.headers["item_id"]
        log.info("verdict.ready item_id=%s — refreshing wiki pages", item_id)
        try:
            await asyncio.to_thread(
                run_once, store, vault_path, top_n=top_n, embed=embed, llm=llm
            )
        except Exception as exc:
            log.error("failed to refresh wiki pages for item_id=%s: %s", item_id, exc)


async def run_consumer(
    bus: RabbitMQBus,
    store,
    vault_path: Path,
    *,
    top_n: int = DEFAULT_TOP_N,
    embed=None,
    llm=None,
) -> None:
    """Consume verdict.ready events and refresh wiki pages for each verdict."""
    await bus._ensure_connection()

    async def _handler(message) -> None:
        await _on_verdict_ready(
            message, store, vault_path, top_n=top_n, embed=embed, llm=llm
        )

    await bus.consume("verdict.ready", _handler, prefetch_count=1)
    await asyncio.Future()  # run forever


# ---------------------------------------------------------------------------
# Health server
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
    parser = argparse.ArgumentParser(description="InfoTriage auto-wiki worker")
    parser.add_argument(
        "--mode",
        choices=["once", "periodic", "events"],
        default=os.environ.get("INFOTRIAGE_WIKI_MODE", "periodic"),
        help="Run mode: once, periodic (default), or events",
    )
    parser.add_argument(
        "--once",
        dest="once_flag",
        action="store_true",
        help="Deprecated alias for --mode once",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=int(os.environ.get("INFOTRIAGE_WIKI_INTERVAL", DEFAULT_INTERVAL)),
        help=f"Seconds between generations in periodic mode (default {DEFAULT_INTERVAL})",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=DEFAULT_TOP_N,
        help=f"Number of top entities to generate pages for (default {DEFAULT_TOP_N})",
    )
    parser.add_argument(
        "--vault-path",
        type=Path,
        default=Path(os.environ.get("INFOTRIAGE_VAULT_PATH", "data/obsidian")),
        help="Obsidian vault root path (default INFOTRIAGE_VAULT_PATH or data/obsidian)",
    )
    parser.add_argument(
        "--dsn",
        default=os.environ.get("INFOTRIAGE_PG_DSN"),
        help="Postgres DSN (default INFOTRIAGE_PG_DSN)",
    )
    parser.add_argument(
        "--blob-root",
        type=Path,
        default=Path(os.environ.get("INFOTRIAGE_BLOB_ROOT", "/data/blobs")),
        help="Blob storage root (default INFOTRIAGE_BLOB_ROOT or /data/blobs)",
    )
    parser.add_argument(
        "--amqp-dsn",
        default=os.environ.get(
            "INFOTRIAGE_AMQP_DSN", "amqp://infotriage:infotriage_rmq@127.0.0.1:22001"
        ),
        help="RabbitMQ DSN for events mode",
    )
    parser.add_argument(
        "--health-host",
        default=os.environ.get("INFOTRIAGE_WIKI_HEALTH_HOST", HEALTH_HOST),
        help="Health server host",
    )
    parser.add_argument(
        "--health-port",
        type=int,
        default=int(os.environ.get("INFOTRIAGE_WIKI_HEALTH_PORT", HEALTH_PORT)),
        help="Health server port",
    )
    return parser


async def _run_async_mode(args) -> None:
    """Run the chosen async mode (periodic or events)."""
    if not args.dsn:
        print("ERROR: --dsn or INFOTRIAGE_PG_DSN required", file=sys.stderr)
        sys.exit(1)

    if args.mode == "events" and not args.amqp_dsn:
        print(
            "ERROR: --amqp-dsn or INFOTRIAGE_AMQP_DSN required for events mode",
            file=sys.stderr,
        )
        sys.exit(1)

    with PostgresStore(dsn=args.dsn, blob_root=args.blob_root) as store:
        tasks = [run_health_server(host=args.health_host, port=args.health_port)]
        if args.mode == "periodic":
            tasks.append(
                run_periodic(
                    store,
                    args.vault_path,
                    interval=args.interval,
                    top_n=args.top_n,
                )
            )
        elif args.mode == "events":
            bus = RabbitMQBus(amqp_url=args.amqp_dsn)
            tasks.append(
                run_consumer(
                    bus,
                    store,
                    args.vault_path,
                    top_n=args.top_n,
                )
            )
        try:
            await asyncio.gather(*tasks)
        finally:
            if args.mode == "events":
                await bus.close()


def main() -> None:
    args = _build_parser().parse_args()

    # Backward compatibility: --once maps to --mode once
    if args.once_flag:
        args.mode = "once"

    if args.mode == "once":
        if not args.dsn:
            print("ERROR: --dsn or INFOTRIAGE_PG_DSN required", file=sys.stderr)
            sys.exit(1)
        with PostgresStore(dsn=args.dsn, blob_root=args.blob_root) as store:
            written = run_once(store, args.vault_path, top_n=args.top_n)
            for path in written:
                print(path)
    else:
        asyncio.run(_run_async_mode(args))


if __name__ == "__main__":
    main()
