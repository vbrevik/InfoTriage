#!/usr/bin/env python3
"""test_ingest_body_email.py — SPEC R7 producer-side body write path: gmail + imap/pop3.

Covers plan 12-08 Task 1: both email adapters set Item.body at every construction
site (gmail has one; imap has two — the IMAP branch and the POP3 branch). Bodyless
messages must persist SQL NULL, never the empty string. No adapter truncates,
caps, or HTML-sanitizes the body; the summary derivation is unchanged.

All assertions read the persisted value back through store.get_item(), not the
constructed Item, so the store's empty/whitespace-to-None coercion (plan 12-07) is
part of what is proven, per the plan's explicit instruction.
"""
import base64
import json
from email.mime.text import MIMEText

import pytest

from store import InMemoryStore

# ---------------------------------------------------------------------------
# Shared fixture text — deliberately longer than the 500-char summary cap so
# the byte-identical / no-truncation property is distinguishable from summary.
# ---------------------------------------------------------------------------
MULTI_PARAGRAPH_TEXT = (
    "First paragraph of the briefing describes the initial situation in detail. " * 3
    + "\n\nSecond paragraph adds further operational context that runs well past "
    "the five-hundred character summary truncation boundary, on purpose. " * 3
    + "\n\nThird paragraph closes the report with concluding remarks and next steps."
)
assert len(MULTI_PARAGRAPH_TEXT) > 500, "fixture must exceed the summary cap"


# ===========================================================================
# Gmail — single construction site (gmail_ingest.py)
# ===========================================================================

FAKE_MESSAGE_ID = "18f2e3a1b9c4d5e6"
FAKE_SUBJECT = "Test briefing from Acme"
FAKE_SNIPPET = "Here is the weekly briefing from Acme Corp."
FAKE_DATE = "Mon, 29 Jun 2026 10:00:00 +0000"


def _b64(text: str) -> str:
    """Gmail API's URL-safe base64, no padding."""
    return base64.urlsafe_b64encode(text.encode("utf-8")).decode("ascii").rstrip("=")


def _gmail_list_result() -> dict:
    return {
        "result": {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {"messages": [{"id": FAKE_MESSAGE_ID, "threadId": "thread-1"}]}
                    ),
                }
            ]
        }
    }


def _gmail_get_result(payload: dict) -> dict:
    return {
        "result": {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "id": FAKE_MESSAGE_ID,
                            "snippet": FAKE_SNIPPET,
                            "payload": {
                                "headers": [
                                    {"name": "Subject", "value": FAKE_SUBJECT},
                                    {"name": "Date", "value": FAKE_DATE},
                                    {"name": "From", "value": "Acme <news@acme.com>"},
                                ],
                                **payload,
                            },
                        }
                    ),
                }
            ]
        }
    }


def _mock_mcp(monkeypatch, get_result: dict):
    """Monkeypatch mcp_client so no real HTTP calls are made."""
    import mcp_client

    async def fake_init_mcp_session(client):
        return "fake-session-id"

    async def fake_mcp_call(client, session_id, method, params):
        name = params.get("name", "") if method == "tools/call" else method
        if name == "list_messages":
            return _gmail_list_result()
        elif name == "get_message":
            return get_result
        return {"result": {}}

    monkeypatch.setattr(mcp_client, "init_mcp_session", fake_init_mcp_session)
    monkeypatch.setattr(mcp_client, "mcp_call", fake_mcp_call)


@pytest.mark.asyncio
async def test_gmail_text_part_persists_full_body_byte_identical(tmp_path, monkeypatch):
    """A gmail message with a text/plain part persists that exact text as body."""
    from contracts import InMemoryBus

    import gmail_ingest

    _mock_mcp(
        monkeypatch,
        _gmail_get_result(
            {
                "mimeType": "text/plain",
                "body": {"data": _b64(MULTI_PARAGRAPH_TEXT)},
            }
        ),
    )
    store = InMemoryStore(blob_root=tmp_path / "blobs")
    bus = InMemoryBus()
    monkeypatch.setattr(gmail_ingest, "_build_store", lambda: store)
    monkeypatch.setattr(gmail_ingest, "_build_bus", lambda: bus)

    await gmail_ingest.ingest()

    items = store.list_items(source_type_in=["gmail"])
    assert len(items) == 1
    retrieved = store.get_item(items[0].id)
    # Byte-identical, no truncation — body is longer than the 500-char summary cap.
    assert retrieved.body == MULTI_PARAGRAPH_TEXT
    # Summary derivation is unchanged from its pre-existing behavior.
    assert retrieved.summary == FAKE_SNIPPET[:500]


@pytest.mark.asyncio
async def test_gmail_no_text_part_persists_null_body(tmp_path, monkeypatch):
    """A gmail message with no readable text/plain part persists a NULL body."""
    from contracts import InMemoryBus

    import gmail_ingest

    # Multipart message with only an image attachment — no text/plain anywhere.
    _mock_mcp(
        monkeypatch,
        _gmail_get_result(
            {
                "mimeType": "multipart/mixed",
                "parts": [
                    {
                        "mimeType": "image/png",
                        "body": {"data": _b64("not-real-image-bytes")},
                    }
                ],
            }
        ),
    )
    store = InMemoryStore(blob_root=tmp_path / "blobs")
    bus = InMemoryBus()
    monkeypatch.setattr(gmail_ingest, "_build_store", lambda: store)
    monkeypatch.setattr(gmail_ingest, "_build_bus", lambda: bus)

    await gmail_ingest.ingest()

    items = store.list_items(source_type_in=["gmail"])
    assert len(items) == 1
    retrieved = store.get_item(items[0].id)
    assert retrieved.body is None
    assert retrieved.summary == FAKE_SNIPPET[:500]


def test_gmail_extract_text_body_decodes_nested_multipart():
    """_extract_text_body recurses into multipart/alternative to find text/plain."""
    import gmail_ingest

    payload = {
        "mimeType": "multipart/alternative",
        "parts": [
            {"mimeType": "text/html", "body": {"data": _b64("<p>html</p>")}},
            {"mimeType": "text/plain", "body": {"data": _b64("plain text wins")}},
        ],
    }
    assert gmail_ingest._extract_text_body(payload) == "plain text wins"


def test_gmail_extract_text_body_returns_empty_for_no_text():
    """_extract_text_body returns '' (not None) when no text/plain part exists."""
    import gmail_ingest

    payload = {"mimeType": "image/png", "body": {"data": _b64("binary-ish")}}
    assert gmail_ingest._extract_text_body(payload) == ""


# ===========================================================================
# IMAP — two construction sites (imap_ingest.py: _fetch_imap and _fetch_pop3)
# ===========================================================================

FIXTURE_MAILBOX = {
    "name": "test-mailbox",
    "host": "imap.example.com",
    "user": "user@example.com",
    "password": "secret",
    "query": "ALL",
    "provider": "imap",
}


def _make_email_bytes(subject: str, text: str, msg_id: str) -> bytes:
    msg = MIMEText(text, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = "sender@example.com"
    msg["Message-ID"] = msg_id
    return msg.as_bytes()


class _FakeImapConn:
    """Minimal imaplib.IMAP4_SSL stub — only the methods fetch_entries/_fetch_imap use."""

    def __init__(self, messages: dict):
        self._messages = messages

    def select(self, folder, readonly=False):
        return ("OK", [b"OK"])

    def fetch(self, mid, spec):
        raw = self._messages[mid]
        return ("OK", [(b"1 (RFC822 {%d}" % len(raw), raw)])

    def logout(self):
        pass


class _FakePop3:
    """Minimal poplib.POP3_SSL stub — only the methods _fetch_pop3 uses."""

    def __init__(self, raw_messages: list):
        self._raw = raw_messages

    def uidl(self):
        listings = [f"{i + 1} uidl-{i + 1}".encode() for i in range(len(self._raw))]
        return (b"+OK", None, listings)

    def stat(self):
        return (b"+OK", [str(len(self._raw)).encode()])

    def retr(self, idx):
        raw = self._raw[idx - 1]
        lines = raw.split(b"\r\n")
        return (b"+OK", lines, len(raw))

    def quit(self):
        pass


def test_imap_site_persists_full_text_byte_identical(tmp_path, monkeypatch):
    """_fetch_imap (site 1 of 2) persists the full decoded body, byte-identical."""
    import imap_ingest

    raw = _make_email_bytes(
        "IMAP Site Subject", MULTI_PARAGRAPH_TEXT, "<imap-site@example.com>"
    )
    fake_conn = _FakeImapConn({b"1": raw})
    monkeypatch.setattr(imap_ingest, "connect", lambda host, user, pw: fake_conn)
    monkeypatch.setattr(imap_ingest, "search_ids", lambda imap, query, provider: [b"1"])

    items = imap_ingest._fetch_imap(FIXTURE_MAILBOX)
    assert len(items) == 1
    item = items[0]
    expected_summary = " ".join(MULTI_PARAGRAPH_TEXT.split())[:500]
    assert item.summary == expected_summary

    store = InMemoryStore(blob_root=tmp_path / "blobs")
    store.put_item(item)
    retrieved = store.get_item(item.id)
    assert retrieved.body == MULTI_PARAGRAPH_TEXT
    assert retrieved.summary == expected_summary


def test_pop3_site_persists_full_text_byte_identical(tmp_path, monkeypatch):
    """_fetch_pop3 (site 2 of 2) persists the full decoded body, byte-identical."""
    import imap_ingest

    raw = _make_email_bytes(
        "POP3 Site Subject", MULTI_PARAGRAPH_TEXT, "<pop3-site@example.com>"
    )
    fake_pop = _FakePop3([raw])
    monkeypatch.setattr(imap_ingest, "connect_pop3", lambda host, user, pw: fake_pop)
    mailbox = {**FIXTURE_MAILBOX, "protocol": "pop3"}

    items = imap_ingest._fetch_pop3(mailbox)
    assert len(items) == 1
    item = items[0]
    expected_summary = " ".join(MULTI_PARAGRAPH_TEXT.split())[:500]
    assert item.summary == expected_summary

    store = InMemoryStore(blob_root=tmp_path / "blobs")
    store.put_item(item)
    retrieved = store.get_item(item.id)
    assert retrieved.body == MULTI_PARAGRAPH_TEXT
    assert retrieved.summary == expected_summary


def test_imap_whitespace_only_payload_persists_null_body(tmp_path, monkeypatch):
    """A message whose payload decodes to only whitespace persists a NULL body."""
    import imap_ingest

    raw = _make_email_bytes(
        "Whitespace Only", "   \n\n\t  \n", "<whitespace@example.com>"
    )
    fake_conn = _FakeImapConn({b"1": raw})
    monkeypatch.setattr(imap_ingest, "connect", lambda host, user, pw: fake_conn)
    monkeypatch.setattr(imap_ingest, "search_ids", lambda imap, query, provider: [b"1"])

    items = imap_ingest._fetch_imap(FIXTURE_MAILBOX)
    assert len(items) == 1
    item = items[0]

    store = InMemoryStore(blob_root=tmp_path / "blobs")
    store.put_item(item)
    retrieved = store.get_item(item.id)
    assert retrieved.body is None
