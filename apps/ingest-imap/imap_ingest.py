#!/usr/bin/env python3
"""imap_ingest.py — multi-mailbox IMAP adapter for InfoTriage.

READ-ONLY: connects to configured IMAP mailboxes, fetches recent messages, and
emits each message as an Item to Postgres + the event bus via ingest_common.
No Atom file is written — email is triage-only, not projected to FreshRSS (SPEC R1).

Fetch functions (load_mailboxes, infer_provider, connect, search_ids, dec,
body_text, fetch_entries) are faithful ports from apps/ingest/imap_to_atom.py.
The write_atom / OUT_DIR / Atom output path is intentionally absent — email is
triage-only, not projected to FreshRSS (SPEC R1).

Env vars consumed:
    MAILBOXES            — JSON array of mailbox specs (or .mailboxes.json fallback)
    INFOTRIAGE_PG_DSN    — PostgreSQL libpq connection string
    INFOTRIAGE_AMQP_DSN  — AMQP URL for RabbitMQ
    INFOTRIAGE_BLOB_ROOT — filesystem root for blob storage (default: data/blobs)

Each mailbox spec:
    {"name": str, "host": str, "user": str, "password": str,
     "query": str, "provider": str}

  provider in {"gmail", "imap"}. Gmail uses X-GM-RAW (proprietary search);
  standard IMAP SEARCH (RFC 3501) for all others.
"""
import email
import imaplib
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from email.header import decode_header

from contracts import Item
from ingest_common import build_bus, build_store, persist_and_publish

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# Mailbox configuration helpers (ported from apps/ingest/imap_to_atom.py)
# ---------------------------------------------------------------------------

def load_mailboxes() -> list[dict]:
    """Load mailbox list from MAILBOXES env, fallback to .mailboxes.json."""
    raw = os.environ.get("MAILBOXES", "").strip()
    if not raw:
        alt = os.path.join(ROOT, ".mailboxes.json")
        if os.path.exists(alt):
            raw = open(alt).read().strip()
    if not raw:
        raise SystemExit("Set MAILBOXES (JSON) or write .mailboxes.json with the list.")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise SystemExit(f"MAILBOXES JSON parse error: {e}")


def infer_provider(host: str) -> str:
    """Infer provider type from hostname. Gmail uses X-GM-RAW; others use standard SEARCH."""
    h = host.lower()
    # gmail.com and legacy googlemail.com (still used by some EU accounts)
    if "gmail.com" in h or "googlemail.com" in h:
        return "gmail"
    return "imap"  # standard IMAP SEARCH for Outlook / Fastmail / ProtonMail / custom


def connect(host: str, user: str, pw: str) -> imaplib.IMAP4_SSL:
    """Open an SSL IMAP connection and log in."""
    imap = imaplib.IMAP4_SSL(host)
    imap.login(user, pw)
    return imap


def _imap_date(query: str) -> str:
    """Expand 'since Nd' shorthand to a proper IMAP SEARCH criterion (SINCE DD-Mon-YYYY)."""
    m = re.fullmatch(r"since\s+(\d+)d", query.strip(), re.IGNORECASE)
    if m:
        since = datetime.now(tz=timezone.utc) - timedelta(days=int(m.group(1)))
        return f"SINCE {since.strftime('%d-%b-%Y')}"
    return query


def search_ids(imap, query: str, provider: str) -> list:
    """Provider-aware SEARCH. Gmail uses X-GM-RAW; everything else uses standard SEARCH."""
    if provider == "gmail":
        typ, data = imap.search(None, "X-GM-RAW", f'"{query}"')
    else:
        typ, data = imap.search(None, _imap_date(query))
    if typ != "OK" or not data or not data[0]:
        return []
    return data[0].split()


def dec(s: str) -> str:
    """Decode a MIME-encoded header value to a plain string."""
    if not s:
        return ""
    return "".join(
        (t.decode(enc or "utf-8", "replace") if isinstance(t, bytes) else t)
        for t, enc in decode_header(s)
    )


def body_text(msg) -> str:
    """Concatenate visible text content of an email message."""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                try:
                    return part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8", "replace"
                    )
                except Exception:
                    pass
        return msg.get("subject", "")
    try:
        return msg.get_payload(decode=True).decode(
            msg.get_content_charset() or "utf-8", "replace"
        )
    except Exception:
        return ""


def fetch_entries(imap, ids: list, max_recent: int = 60) -> list[tuple]:
    """Fetch (subject, from_, snippet, message_id) tuples for the most-recent message IDs.

    T-04-05: max_recent=60 cap retained from imap_to_atom.py to bound fetch volume.
    """
    def _parse(mid):
        typ, data = imap.fetch(mid, "(RFC822)")
        if typ != "OK":
            return None
        msg = email.message_from_bytes(data[0][1])
        return (
            dec(msg.get("subject")) or "(no subject)",
            dec(msg.get("from")) or "(unknown sender)",
            " ".join(body_text(msg).split())[:500],
            msg.get("Message-ID", str(mid)),
        )

    return [entry for entry in (_parse(mid) for mid in ids[-max_recent:]) if entry]


def fetch_items(mailbox: dict) -> list[Item]:
    """Connect to a single mailbox read-only and return a list of Item objects.

    No Atom file is written (SPEC R1, email is triage-only).
    Read-only posture: imap.select("INBOX", readonly=True); no STORE/EXPUNGE/COPY/APPEND.
    """
    host = mailbox["host"]
    user = mailbox["user"]
    pw = mailbox["password"]
    query = mailbox.get("query", "ALL")
    provider = mailbox.get("provider") or infer_provider(host)

    imap = connect(host, user, pw)
    imap.select("INBOX", readonly=True)  # read-only posture (ADR-004 / NF-4)
    ids = search_ids(imap, query, provider)
    entries = fetch_entries(imap, ids)
    imap.logout()

    return [
        Item(
            source=mailbox["name"],
            source_type="imap",
            url=f"imap://{host}/{message_id}",
            title=subject or "(no subject)",
            ts=datetime.now(tz=timezone.utc),
            lang="und",
            summary=snippet[:500],
        )
        for subject, from_, snippet, message_id in entries
    ]


async def ingest() -> None:
    """Zero-arg ingest coroutine for make_trigger_app (D-01).

    Loads mailboxes from env, fetches Items from each mailbox (read-only), and
    persists+publishes each via ingest_common.persist_and_publish (idempotent R6).
    No Atom file is written; email is triage-only (SPEC R1).
    """
    mailboxes = load_mailboxes()
    bus = build_bus()
    try:
        with build_store() as store:
            for mb in mailboxes:
                items = fetch_items(mb)
                for item in items:
                    await persist_and_publish(store, bus, item)
    finally:
        await bus.close()
