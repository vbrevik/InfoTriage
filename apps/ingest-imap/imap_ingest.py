#!/usr/bin/env python3
"""imap_ingest.py — multi-protocol mail adapter for InfoTriage.

READ-ONLY: connects to configured IMAP or POP3 mailboxes, fetches recent
messages, and emits each message as an Item to Postgres + the event bus via
ingest_common. No Atom file is written — email is triage-only, not projected
to FreshRSS (SPEC R1).

The original implementation was IMAP-only; POP3 was added as a parallel
branch behind the per-mailbox ``protocol`` field so a single adapter can
fetch both IMAP (Gmail / Outlook / Fastmail / ProtonMail / custom IMAP)
and POP3 (e.g. rs-pop / Hover / older ISP mailboxes).

Env vars consumed:
    MAILBOXES            — JSON array of mailbox specs (or .mailboxes.json fallback)
    INFOTRIAGE_PG_DSN    — PostgreSQL libpq connection string
    INFOTRIAGE_AMQP_DSN  — AMQP URL for RabbitMQ
    INFOTRIAGE_BLOB_ROOT — filesystem root for blob storage (default: data/blobs)

Each mailbox spec:
    {"name": str, "host": str, "user": str, "password": str,
     "query": str, "provider": str, "protocol": str}

  protocol in {"imap", "pop3"} — defaults to "imap" for backward compat.
  provider in {"gmail", "imap"} — kept for IMAP X-GM-RAW vs standard SEARCH
  routing; ignored when protocol is "pop3".

POP3 has no folders, no server-side search, and no read-state sync. We keep
the last ``max_recent`` (default 60) messages and use the server-allocated
UIDL as the per-message unique key. The Item.id = sha256(source_type + NUL
+ url + NUL + title) is therefore stable across polls for the same UIDL,
giving us idempotent ingest without a UIDL store (R6).
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


def connect_pop3(host: str, user: str, pw: str):
    """Open an SSL POP3 connection, send USER + PASS, return the live poplib object.

    Imported lazily so deployments that only ever use IMAP don't pay the
    poplib import on cold start. Tests monkeypatch this symbol.
    """
    import poplib  # stdlib; deferred import keeps IMAP-only start cheap

    pop = poplib.POP3_SSL(host)
    pop.user(user)
    pop.pass_(pw)
    return pop


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


# ---------------------------------------------------------------------------
# Fetch dispatch — IMAP and POP3 branches
# ---------------------------------------------------------------------------


def _fetch_imap(mailbox: dict) -> list[Item]:
    """IMAP branch — original behavior, unchanged downstream of connect()."""
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


def _fetch_pop3(mailbox: dict, max_recent: int = 60) -> list[Item]:
    """POP3 branch — UIDL provides stable per-message dedup URLs.

    POP3's ``TOP i N`` could fetch headers + first N body lines (cheaper) but
    we use ``RETR i`` for the full message because email body text is short
    and the existing ``email.message_from_bytes`` path is what the IMAP
    branch already exercises. UIDL uniqueness makes the resulting Item.id
    idempotent across polls.
    """
    import poplib  # local import to avoid pulling poplib on IMAP-only runs

    host = mailbox["host"]
    user = mailbox["user"]
    pw = mailbox["password"]
    max_recent = int(mailbox.get("max_recent", max_recent))

    pop = connect_pop3(host, user, pw)
    try:
        # UIDL → {idx: uidl} dict. UIDLs are stable across sessions, so the
        # same physical message yields the same Item.url on every poll —
        # downstream Item.id (sha256 of source_type + url + title) dedups
        # naturally through ingest_common.persist_and_publish (R6).
        resp, _octets, listings = pop.uidl()
        if isinstance(resp, bytes) and resp.startswith(b"-ERR"):
            # Some servers temporarily reject UIDL. Fall back to ordinal-only.
            uidls = {}
        else:
            uidls = {}
            for line in listings:
                parts = line.decode("utf-8", "replace").split()
                if len(parts) < 2:
                    continue
                try:
                    idx = int(parts[0])
                except ValueError:
                    continue
                uidls[idx] = parts[1]

        resp, total_list = pop.stat()
        # Bail loudly on a negative response — a transient POP3 outage must
        # NOT crash the whole ingest run; the consumer nacks to DLQ for retry.
        if isinstance(resp, bytes) and resp.startswith(b"-ERR"):
            return []
        count = int(total_list[0])
        if count == 0:
            return []
        # POP3 indexes grow as messages arrive; the most-recent max_recent live
        # at the tail. Newer-only fetch keeps bandwidth bounded even on small
        # accounts and matches the IMAP "last 60" semantics.
        start = max(1, count - max_recent + 1)

        entries: list[tuple] = []
        for idx in range(start, count + 1):
            uidl = uidls.get(idx, str(idx))
            # poplib.retr returns (resp, lines, octets); lines are bytes
            # without trailing CRLF. Reassemble with CRLF so RFC 822 parsers
            # accept it.
            resp, lines, _ = pop.retr(idx)
            raw = b"\r\n".join(lines)
            msg = email.message_from_bytes(raw)
            subject = dec(msg.get("subject")) or "(no subject)"
            from_ = dec(msg.get("from")) or "(unknown sender)"
            snippet = " ".join(body_text(msg).split())[:500]
            # Prefer Message-ID; fall back to UIDL+idx for messages without it.
            message_id = msg.get("Message-ID") or f"<pop3-{uidl}-{idx}@local>"
            entries.append((subject, from_, snippet, uidl, message_id))
    finally:
        try:
            pop.quit()
        except poplib.error_proto:
            # Some servers reject QUIT when torn down mid-session; safe to ignore.
            pass

    return [
        Item(
            source=mailbox["name"],
            source_type="pop3",
            url=f"pop3://{host}/{uidl}",
            title=subject or "(no subject)",
            ts=datetime.now(tz=timezone.utc),
            lang="und",
            summary=snippet[:500],
        )
        for subject, from_, snippet, uidl, message_id in entries
    ]


def fetch_items(mailbox: dict) -> list[Item]:
    """Connect to a single mailbox read-only and return a list of Item objects.

    Dispatches to IMAP or POP3 based on ``mailbox['protocol']`` (defaulting
    to "imap" for back-compat with existing MAILBOXES JSON specs). No Atom
    file is written (SPEC R1, email is triage-only).
    Read-only posture: imap.select("INBOX", readonly=True); POP3 RETR only,
    never DELE.
    """
    protocol = (mailbox.get("protocol") or "imap").lower()
    if protocol == "pop3":
        return _fetch_pop3(mailbox)
    # "" or "imap" or any other value falls through to IMAP (back-compat).
    return _fetch_imap(mailbox)


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
