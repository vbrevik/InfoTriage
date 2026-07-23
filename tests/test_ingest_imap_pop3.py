#!/usr/bin/env python3
"""test_ingest_imap_pop3.py — POP3 protocol dispatch tests (RED).

POP3 was added to apps/ingest-imap/imap_ingest.py as a parallel branch to
IMAP. These tests lock the contract:
  - mailbox spec with protocol="pop3" routes to the POP3 connector
  - mailbox defaults to "imap" when protocol is missing (back-compat)
  - POP3 Items carry source_type="pop3" and url shape f"pop3://{host}/{uidl}"
  - POP3 messages without outbound article URLs are still ingested (read
    queue is not a sink — the link filter lives in the brief view layer)
"""
import pathlib
from unittest.mock import MagicMock

import pytest

from contracts import InMemoryBus, Item
from store import InMemoryStore


POP3_FIXTURE_MAILBOX = {
    "name": "test-pop3",
    "host": "pop.example.com",
    "user": "test@example.com",
    "password": "secret",
    "protocol": "pop3",
}


IMAP_FIXTURE_MAILBOX = {
    "name": "test-imap",
    "host": "imap.example.com",
    "user": "test@example.com",
    "password": "secret",
    "provider": "imap",
}


# Minimal IMAP stub — re-used from the existing test style.
class _MockImap:
    def select(self, folder, readonly=False):
        return ("OK", [b"0"])

    def logout(self):
        pass

    def search(self, charset, *criteria):
        # Empty result — the IMAP-dispatch tests only assert the connect()
        # decision is protocol-correct; they don't care about items.
        return ("OK", [b""])

    def fetch(self, mid, what):
        return ("OK", [None, b""])


# Minimal POP3 stub. The methods imap_ingest calls are listed below.
class _MockPop3:
    seed = [
        # (uidl, raw_rfc822_bytes)
        (
            "uid-A",
            (
                b"From: sender@example.com\r\n"
                b"Subject: Newsletter with link\r\n"
                b"Message-ID: <m1@example.com>\r\n"
                b"\r\n"
                b"See https://example.com/article1 for details.\r\n"
            ),
        ),
        (
            "uid-B",
            (
                b"From: sender@example.com\r\n"
                b"Subject: Plain update\r\n"
                b"Message-ID: <m2@example.com>\r\n"
                b"\r\n"
                b"Visit https://nrk.no/another to read more.\r\n"
            ),
        ),
    ]

    def user(self, _u):
        return ("+OK", [])

    def pass_(self, _p):
        return ("+OK", [])

    def stat(self):
        # poplib.stat() returns 2-tuple (resp, [count, size]).
        return ("+OK", [len(self.seed), sum(len(b) for _, b in self.seed)])

    def uidl(self):
        # poplib.uidl() (no arg) returns 3-tuple (resp, octets, listings) —
        # shape mirrors real poplib so the test fails fast if the consumer
        # expects the wrong shape.
        listings = [f"{i + 1} {u}".encode() for i, (u, _) in enumerate(self.seed)]
        return ("+OK", sum(len(b) for _, b in self.seed), listings)

    def retr(self, idx):
        raw = self.seed[idx - 1][1]
        lines = raw.split(b"\r\n")
        return ("+OK", lines, len(raw))

    def quit(self):
        return ("+OK", [])


@pytest.mark.asyncio
async def test_pop3_dispatch_calls_connect_pop3(
    tmp_path: pathlib.Path, monkeypatch
) -> None:
    """A mailbox with protocol='pop3' must route to connect_pop3, never to connect."""
    import imap_ingest

    connect_pop3 = MagicMock(return_value=_MockPop3())
    connect_imap = MagicMock(return_value=_MockImap())
    # Replace fetch_items with the real one (we test the real dispatch path, not
    # a higher-level stub). The fetch implementation must call connect_pop3.
    monkeypatch.setattr(imap_ingest, "load_mailboxes", lambda: [POP3_FIXTURE_MAILBOX])
    monkeypatch.setattr(imap_ingest, "connect", connect_imap)
    monkeypatch.setattr(imap_ingest, "connect_pop3", connect_pop3)
    # Stub out the publisher side — we only care about the connect decision.
    monkeypatch.setattr(
        imap_ingest, "build_store", lambda: InMemoryStore(blob_root=tmp_path / "blobs")
    )
    monkeypatch.setattr(imap_ingest, "build_bus", lambda: InMemoryBus())

    await imap_ingest.ingest()

    connect_pop3.assert_called_once_with(
        POP3_FIXTURE_MAILBOX["host"],
        POP3_FIXTURE_MAILBOX["user"],
        POP3_FIXTURE_MAILBOX["password"],
    )
    assert not connect_imap.called, "connect (imap) must NOT be called for POP3"


@pytest.mark.asyncio
async def test_pop3_fetch_produces_items_with_pop3_url(
    tmp_path: pathlib.Path, monkeypatch
) -> None:
    """POP3 messages are persisted as Items with source_type='pop3' and a pop3:// url."""
    import imap_ingest

    store = InMemoryStore(blob_root=tmp_path / "blobs")
    bus = InMemoryBus()

    monkeypatch.setattr(imap_ingest, "load_mailboxes", lambda: [POP3_FIXTURE_MAILBOX])
    monkeypatch.setattr(imap_ingest, "connect_pop3", lambda host, user, pw: _MockPop3())
    monkeypatch.setattr(imap_ingest, "connect", MagicMock(return_value=_MockImap()))
    monkeypatch.setattr(imap_ingest, "build_store", lambda: store)
    monkeypatch.setattr(imap_ingest, "build_bus", lambda: bus)

    await imap_ingest.ingest()

    items = store.list_items()
    assert len(items) == 2, f"Expected 2 POP3 Items, got {len(items)}"
    for it in items:
        assert (
            it.source_type == "pop3"
        ), f"source_type must be pop3, got {it.source_type}"
        assert it.url.startswith(
            "pop3://pop.example.com/"
        ), f"pop3 url shape required, got {it.url!r}"
        assert it.lang == "und"


@pytest.mark.asyncio
async def test_default_protocol_is_imap(tmp_path: pathlib.Path, monkeypatch) -> None:
    """A mailbox spec without a 'protocol' key must default to IMAP (back-compat)."""
    import imap_ingest

    # No protocol field — legacy spec.
    legacy_mailbox = dict(POP3_FIXTURE_MAILBOX)
    legacy_mailbox.pop("protocol", None)
    legacy_mailbox["provider"] = "imap"

    connect_pop3 = MagicMock(return_value=_MockPop3())
    connect_imap = MagicMock(return_value=_MockImap())
    monkeypatch.setattr(imap_ingest, "load_mailboxes", lambda: [legacy_mailbox])
    monkeypatch.setattr(imap_ingest, "connect", connect_imap)
    monkeypatch.setattr(imap_ingest, "connect_pop3", connect_pop3)
    monkeypatch.setattr(
        imap_ingest, "build_store", lambda: InMemoryStore(blob_root=tmp_path / "blobs")
    )
    monkeypatch.setattr(imap_ingest, "build_bus", lambda: InMemoryBus())

    await imap_ingest.ingest()

    connect_imap.assert_called_once()
    assert not connect_pop3.called


@pytest.mark.asyncio
async def test_imap_protocol_key_explicit(tmp_path: pathlib.Path, monkeypatch) -> None:
    """Explicit protocol='imap' continues to use the imaplib connector."""
    import imap_ingest

    explicit_imap = dict(IMAP_FIXTURE_MAILBOX)
    explicit_imap["protocol"] = "imap"

    connect_pop3 = MagicMock(return_value=_MockPop3())
    connect_imap = MagicMock(return_value=_MockImap())
    monkeypatch.setattr(imap_ingest, "load_mailboxes", lambda: [explicit_imap])
    monkeypatch.setattr(imap_ingest, "connect", connect_imap)
    monkeypatch.setattr(imap_ingest, "connect_pop3", connect_pop3)
    monkeypatch.setattr(
        imap_ingest, "build_store", lambda: InMemoryStore(blob_root=tmp_path / "blobs")
    )
    monkeypatch.setattr(imap_ingest, "build_bus", lambda: InMemoryBus())

    await imap_ingest.ingest()

    connect_imap.assert_called_once()
    assert not connect_pop3.called


@pytest.mark.asyncio
async def test_pop3_idempotent_across_runs(tmp_path: pathlib.Path, monkeypatch) -> None:
    """Re-running the POP3 ingest does not produce duplicate Items (Item.id dedup)."""
    import imap_ingest

    store = InMemoryStore(blob_root=tmp_path / "blobs")
    bus = InMemoryBus()
    monkeypatch.setattr(imap_ingest, "load_mailboxes", lambda: [POP3_FIXTURE_MAILBOX])
    monkeypatch.setattr(imap_ingest, "connect_pop3", lambda host, user, pw: _MockPop3())
    monkeypatch.setattr(imap_ingest, "connect", MagicMock(return_value=_MockImap()))
    monkeypatch.setattr(imap_ingest, "build_store", lambda: store)
    monkeypatch.setattr(imap_ingest, "build_bus", lambda: bus)

    await imap_ingest.ingest()
    await imap_ingest.ingest()

    items = store.list_items()
    assert len(items) == 2, f"Re-run must dedup, got {len(items)} items"


def test_pop3_url_scheme_produces_stable_id() -> None:
    """The Item.id (dedup key) for POP3 must be a SHA-256 of source_type|url|title."""
    item = Item(
        source="test-pop3",
        source_type="pop3",
        url="pop3://pop.example.com/uid-A",
        title="Subject",
        ts=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        lang="und",
    )
    # Same url + same title → same id (dedup-friendly).
    other = item.model_copy()
    assert item.id == other.id
    # Different url → different id (new message on next poll).
    bumped = item.model_copy(update={"url": "pop3://pop.example.com/uid-A2"})
    assert item.id != bumped.id
