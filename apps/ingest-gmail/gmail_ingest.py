#!/usr/bin/env python3
"""gmail_ingest.py — Gmail MCP adapter: fetch Gmail messages → Item → Postgres + bus.

Implements SPEC R3 (ingest-gmail): initializes an MCP session with the self-hosted
@shinzolabs/gmail-mcp server via raw httpx JSON-RPC (D-05), normalizes each Gmail
message to an Item with source_type="gmail", and calls persist_and_publish for
idempotent storage + event publishing (R6).

Environment variables:
    GMAIL_MCP_URL        — MCP server URL (default: http://gmail-mcp-server:3000)
    GMAIL_QUERY          — Gmail search query (default: newer_than:7d)
    INFOTRIAGE_PG_DSN    — Postgres DSN (for build_store)
    INFOTRIAGE_AMQP_DSN  — RabbitMQ AMQP URL (for build_bus)

Security: no write/mutate tools are called; source_type is always "gmail";
no credentials flow through this module (T-04-11, T-04-12, T-04-13, ADR-008).
"""
import datetime
import logging
import os
from email.utils import parsedate_to_datetime

import httpx

import mcp_client
from ingest_common import build_bus, build_store, persist_and_publish

log = logging.getLogger(__name__)

GMAIL_QUERY: str = os.environ.get("GMAIL_QUERY", "newer_than:7d")
MAX_MESSAGES: int = int(os.environ.get("GMAIL_MAX_MESSAGES", "50"))


# ---------------------------------------------------------------------------
# Testability seam: allow tests to inject store/bus without real env vars
# ---------------------------------------------------------------------------

def _build_store():
    """Default store factory; replaced by tests via monkeypatch."""
    return build_store()


def _build_bus():
    """Default bus factory; replaced by tests via monkeypatch."""
    return build_bus()


# ---------------------------------------------------------------------------
# Normalization: Gmail message dict → Item
# ---------------------------------------------------------------------------

def _parse_subject(headers: list[dict]) -> str:
    """Extract the Subject header value (empty string if missing)."""
    for h in headers:
        if h.get("name", "").lower() == "subject":
            return h.get("value", "")
    return ""


def _parse_date(headers: list[dict]) -> datetime.datetime:
    """Parse Date header to tz-aware datetime; fallback to now() UTC."""
    for h in headers:
        if h.get("name", "").lower() == "date":
            raw = h.get("value", "")
            if raw:
                try:
                    return parsedate_to_datetime(raw)
                except Exception:
                    pass
    return datetime.datetime.now(tz=datetime.timezone.utc)


def fetch_items(messages: list[dict]) -> list:
    """Normalize a list of Gmail message dicts to Item instances.

    Each dict must have:
        id       — Gmail message ID (used to build a synthetic url)
        snippet  — short text preview
        subject  — subject line (already extracted from headers)
        date     — RFC 2822 date string

    Returns a list of Item instances with source_type="gmail".
    """
    from contracts import Item

    items = []
    for msg in messages:
        msg_id = msg.get("id", "")
        subject = msg.get("subject", "") or "(no subject)"
        snippet = msg.get("snippet", "") or ""
        date_str = msg.get("date", "")

        # Parse date to tz-aware datetime
        if date_str:
            try:
                ts = parsedate_to_datetime(date_str)
            except Exception:
                ts = datetime.datetime.now(tz=datetime.timezone.utc)
        else:
            ts = datetime.datetime.now(tz=datetime.timezone.utc)

        item = Item(
            source="gmail",
            source_type="gmail",
            url=f"gmail://message/{msg_id}",
            title=subject,
            ts=ts,
            lang="und",  # language unknown without content analysis
            summary=snippet[:500],
        )
        items.append(item)
    return items


# ---------------------------------------------------------------------------
# Main ingest coroutine
# ---------------------------------------------------------------------------

async def ingest() -> None:
    """Fetch Gmail messages via MCP and persist each as an Item.

    Opens an httpx.AsyncClient, initializes the MCP session, lists messages
    filtered by GMAIL_QUERY, fetches each message's metadata, normalizes to
    Items, and calls persist_and_publish for each one.
    """
    store = _build_store()
    bus = _build_bus()

    async with httpx.AsyncClient() as client:
        try:
            session_id = await mcp_client.init_mcp_session(client)
            log.info("MCP session initialized (id=%s)", session_id or "(none)")

            stubs = await mcp_client.list_messages(
                client, session_id, query=GMAIL_QUERY, max_results=MAX_MESSAGES
            )
            log.info("Listed %d Gmail messages for query=%r", len(stubs), GMAIL_QUERY)

            if not stubs:
                log.info("No messages matched query — nothing to ingest")
                return

            # Fetch full metadata for each message
            raw_messages = []
            for stub in stubs:
                msg_id = stub.get("id", "")
                if not msg_id:
                    continue
                msg = await mcp_client.get_message(client, session_id, msg_id)
                # Extract subject and date from payload headers
                headers = msg.get("payload", {}).get("headers", [])
                raw_messages.append(
                    {
                        "id": msg.get("id", msg_id),
                        "snippet": msg.get("snippet", ""),
                        "subject": _parse_subject(headers),
                        "date": _parse_date(headers).isoformat(),
                    }
                )

            items = fetch_items(raw_messages)
            log.info("Normalized %d items", len(items))

            # Persist and publish inside the store context manager
            with store:
                new_count = 0
                for item in items:
                    is_new = await persist_and_publish(store, bus, item)
                    if is_new:
                        new_count += 1
            log.info("Ingested %d new, %d duplicates", new_count, len(items) - new_count)

        except Exception:
            log.exception("ingest-gmail run failed")
            raise

    # Close the bus connection (RabbitMQBus requires explicit close)
    if hasattr(bus, "close"):
        await bus.close()
