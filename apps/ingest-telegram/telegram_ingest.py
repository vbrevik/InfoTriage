#!/usr/bin/env python3
"""telegram_ingest.py — Telegram SOCMINT adapter for InfoTriage.

Reads public Telegram channels and emits each post as an Item.
Posts carry discipline="SOCMINT" and a default Admiralty reliability rating.

Environment variables:
    TELEGRAM_API_ID      — Telegram app api_id (integer)
    TELEGRAM_API_HASH    — Telegram app api_hash
    TELEGRAM_CHANNELS    — comma-separated list of channel identifiers
    TELEGRAM_SINCE       — default window for --since (default: 24h)
    INFOTRIAGE_PG_DSN    — PostgreSQL libpq connection string
    INFOTRIAGE_AMQP_DSN  — AMQP URL for RabbitMQ
    INFOTRIAGE_BLOB_ROOT — filesystem root for blob storage (default: data/blobs)
"""
import argparse
import datetime
import logging
import os
import re
from typing import Optional

from contracts import BusClient, Item, require_discipline
from ingest_common import build_bus, build_store, persist_and_publish
from store._protocol import Store

log = logging.getLogger(__name__)

# Default Admiralty reliability for SOCMINT social-media content.
DEFAULT_ADMIRALTY_RELIABILITY = "C3"


# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------


def load_channels(cli_channels: Optional[list[str]] = None) -> list[str]:
    """Resolve channel identifiers from CLI args or TELEGRAM_CHANNELS env var."""
    if cli_channels:
        return list(cli_channels)
    raw = os.environ.get("TELEGRAM_CHANNELS", "").strip()
    if not raw:
        return []
    return [c.strip() for c in raw.split(",") if c.strip()]


def parse_since(since: Optional[str]) -> Optional[datetime.datetime]:
    """Parse a relative window like '24h' or '7d' into a UTC datetime.

    Returns None if since is None or empty.
    """
    if not since:
        return None
    since = since.strip()
    match = re.fullmatch(r"(\d+)([hd])", since, re.IGNORECASE)
    if not match:
        raise ValueError(f"Invalid --since value: {since!r}; expected e.g. 24h or 7d")
    value, unit = int(match.group(1)), match.group(2).lower()
    delta = (
        datetime.timedelta(hours=value)
        if unit == "h"
        else datetime.timedelta(days=value)
    )
    return datetime.datetime.now(tz=datetime.timezone.utc) - delta


# ---------------------------------------------------------------------------
# Telethon seam (lazy import so tests can mock without installing Telethon)
# ---------------------------------------------------------------------------


def _create_client(api_id: Optional[int] = None, api_hash: Optional[str] = None):
    """Build a Telethon TelegramClient from env vars."""
    try:
        api_id = api_id or int(os.environ["TELEGRAM_API_ID"])
        api_hash = api_hash or os.environ["TELEGRAM_API_HASH"]
    except (KeyError, ValueError) as exc:
        raise SystemExit(
            "Telegram credentials missing. Set TELEGRAM_API_ID and TELEGRAM_API_HASH."
        ) from exc
    from telethon import TelegramClient

    return TelegramClient("infotriage", api_id, api_hash)


async def fetch_messages(
    client, channel: str, since: Optional[datetime.datetime] = None, limit: int = 100
) -> list:
    """Fetch recent messages from a Telegram channel, filtering by UTC datetime.

    Args:
        client: TelegramClient (or compatible mock).
        channel: Channel identifier (username, ID, or URL).
        since: UTC datetime; only messages after this are returned.
        limit: maximum messages per channel.

    Returns:
        List of Telethon Message-like objects with date >= since.
    """
    entity = await client.get_entity(channel)
    messages = []
    # iter_messages returns newest first; once we pass the window we can stop.
    async for message in client.iter_messages(entity, limit=limit):
        if since is not None and message.date < since:
            break
        messages.append(message)
    return messages


# ---------------------------------------------------------------------------
# Message → Item mapping
# ---------------------------------------------------------------------------


def _message_to_item(channel: str, message) -> Item:
    """Map a Telethon message to an InfoTriage Item."""
    text = getattr(message, "text", "") or ""
    title = text.split("\n", 1)[0].strip() or f"telegram:{channel}:{message.id}"
    url = f"https://t.me/{channel.lstrip('@')}/{message.id}"
    item = Item(
        source=channel,
        source_type="telegram",
        url=url,
        title=title,
        ts=message.date,
        lang="und",
        summary=text[:500],
        discipline="SOCMINT",
        admiralty_reliability=DEFAULT_ADMIRALTY_RELIABILITY,
    )
    require_discipline(item)
    return item


# ---------------------------------------------------------------------------
# Main ingest coroutine
# ---------------------------------------------------------------------------


async def ingest(
    since: Optional[str] = None,
    channels: Optional[list[str]] = None,
    dry_run: bool = False,
    _client=None,
) -> list[Item]:
    """Fetch Telegram messages and emit Items.

    Args:
        since: Relative window like "24h" or "7d".
        channels: Override channel list (defaults to TELEGRAM_CHANNELS env).
        dry_run: If True, build Items but do not persist or publish.
        _client: Optional injected Telegram client for tests.

    Returns:
        List of Items produced.
    """
    channel_ids = load_channels(channels)
    if not channel_ids:
        raise SystemExit(
            "No Telegram channels configured. Set TELEGRAM_CHANNELS or pass --channel."
        )

    since_dt = parse_since(since)
    client = _client if _client is not None else _create_client()
    produced: list[Item] = []
    window = since or "latest 100"
    log.info(
        "telegram ingest start: channels=%d window=%s dry_run=%s",
        len(channel_ids),
        window,
        dry_run,
    )

    store: Optional[Store] = None
    bus: Optional[BusClient] = None
    if not dry_run:
        store = build_store()
        bus = build_bus()

    async with client:
        for channel in channel_ids:
            log.info("fetching messages from %s", channel)
            messages = await fetch_messages(client, channel, since_dt)
            for msg in messages:
                item = _message_to_item(channel, msg)
                produced.append(item)
                if dry_run:
                    continue
                assert store is not None and bus is not None
                await persist_and_publish(store, bus, item)

    if not dry_run:
        close_fn = getattr(bus, "close", None)
        if callable(close_fn):
            await close_fn()

    log.info("telegram ingest complete: %d items produced", len(produced))
    return produced


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ingest public Telegram channels into InfoTriage."
    )
    parser.add_argument(
        "--since",
        default=os.environ.get("TELEGRAM_SINCE", "24h"),
        help="Window like 24h or 7d",
    )
    parser.add_argument(
        "--channel", action="append", help="Telegram channel identifier (repeatable)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build Items without persisting or publishing",
    )
    return parser


def main() -> None:
    """Synchronous CLI entry point."""
    parser = _build_argument_parser()
    args = parser.parse_args()
    import asyncio

    asyncio.run(ingest(since=args.since, channels=args.channel, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
