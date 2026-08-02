"""tests/test_mvp_poller.py — the MVP poller (Phase 13 lean stack).

Proves the whole synchronous value chain without Docker: a stubbed FreshRSS
Fever server feeds items to poll_once(), the scorer is monkeypatched (no LLM
call), and a stub ntfy server records pushes. Covers: CAT I fires exactly one
push; non-CAT-I fires zero; repeated items are deduped and since_id advances;
the health server responds 200 without touching bus or DB.
"""

from __future__ import annotations

import asyncio
import http.server
import json
import threading
import urllib.parse

import pytest
from store import InMemoryStore

from poller import _PollState, _handle_health, _summary_from_html, poll_once


class _FeverHandler(http.server.BaseHTTPRequestHandler):
    """Stub Fever server: serves a controllable items list, records requests."""

    items: list[dict] = []
    requests: list[dict] = []

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        self.__class__.requests.append(
            {
                "path": parsed.path,
                "query": query,
                "since_id": int(query.get("since_id", ["0"])[0]),
            }
        )
        since = int(query.get("since_id", ["0"])[0])
        items = [i for i in self.__class__.items if int(i.get("id", 0)) > since]
        body = json.dumps({"auth": 1, "items": items}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args) -> None:  # noqa: A002
        pass  # silence stub-server access logs


class _RecordingNtfy(http.server.BaseHTTPRequestHandler):
    """Stub ntfy server recording every POST."""

    requests: list[dict] = []

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        self.__class__.requests.append(
            {"path": self.path, "headers": dict(self.headers), "body": body}
        )
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, format, *args) -> None:  # noqa: A002
        pass


@pytest.fixture
def fever_server():
    _FeverHandler.items = []
    _FeverHandler.requests = []
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _FeverHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)


@pytest.fixture
def ntfy_server():
    _RecordingNtfy.requests = []
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _RecordingNtfy)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    try:
        yield f"http://127.0.0.1:{port}", _RecordingNtfy
    finally:
        server.shutdown()
        thread.join(timeout=5)


def _fever_item(item_id: int, *, title: str, html: str, author: str = "NRK") -> dict:
    return {
        "id": item_id,
        "title": title,
        "url": f"https://example.com/{item_id}",
        "html": f"<p>{html}</p>",
        "author": author,
        "created_on_time": 1700000000 + item_id,
    }


def _fake_scorer(cnr_for_title: dict[str, str], score: int = 9):
    """Patch the scorer: cnr per title (or "none"), no LLM call."""

    def fake_score(item_dict):
        cnr = cnr_for_title.get(item_dict.get("title", ""), "none")
        return {
            **item_dict,
            "ccir": "CIR-1" if cnr != "none" else "none",
            "cnr": cnr,
            "score": score,
            "bucket": "read" if cnr == "I" else "skip",
            "why": "test rationale",
            "pmesii": "Military",
            "tessoc": "none",
        }

    return fake_score


def test_summary_from_html_strips_tags_and_truncates():
    text = _summary_from_html("<p>Hello <b>world</b></p>", limit=20)
    assert text == "Hello world"[:20] or text.startswith("Hello world")
    assert "<" not in text


def test_poll_once_cat_i_fires_exactly_one_push(
    monkeypatch, tmp_path, fever_server, ntfy_server
):
    monkeypatch.setattr(
        "poller.score_item",
        _fake_scorer({"Troppebevegelse ved grensen": "I"}),
    )
    base_url, handler_cls = ntfy_server
    _FeverHandler.items = [
        _fever_item(1, title="Troppebevegelse ved grensen", html="Innhold 1"),
        _fever_item(2, title="Rutinesak", html="Innhold 2"),
    ]
    store = InMemoryStore(blob_root=tmp_path)
    state = _PollState(tmp_path / "state.json")

    from outbox import NtfyClient

    client = NtfyClient(base_url, "secret-token", "cnr-cat-i")
    result = asyncio.run(
        poll_once(
            store,
            client,
            base_url=fever_server,
            user="admin",
            password="pw",
            vault_path=tmp_path / "vault",
            state=state,
        )
    )

    assert result["scored"] == 2
    assert result["pushed"] == 1
    assert result["skipped"] == 0
    assert len(handler_cls.requests) == 1
    assert handler_cls.requests[0]["path"].endswith("/cnr-cat-i")
    body = json.loads(handler_cls.requests[0]["body"])
    assert body["cnr_tier"] == "I"
    assert state.since_id == 2


def test_poll_once_non_cat_i_fires_zero_pushes(
    monkeypatch, tmp_path, fever_server, ntfy_server
):
    monkeypatch.setattr(
        "poller.score_item", _fake_scorer({"L'Oréal bygger AI": "none"})
    )
    base_url, handler_cls = ntfy_server
    _FeverHandler.items = [
        _fever_item(1, title="L'Oréal bygger AI", html="Irrelevant"),
    ]
    store = InMemoryStore(blob_root=tmp_path)
    state = _PollState(tmp_path / "state.json")

    from outbox import NtfyClient

    client = NtfyClient(base_url, "secret-token", "cnr-cat-i")
    result = asyncio.run(
        poll_once(
            store,
            client,
            base_url=fever_server,
            user="admin",
            password="pw",
            vault_path=tmp_path / "vault",
            state=state,
        )
    )

    assert result["pushed"] == 0
    assert len(handler_cls.requests) == 0


def test_poll_once_dedupes_repeat_items_and_advances_since_id(
    monkeypatch, tmp_path, fever_server, ntfy_server
):
    monkeypatch.setattr("poller.score_item", _fake_scorer({"Samme sak": "I"}))
    base_url, handler_cls = ntfy_server
    _FeverHandler.items = [
        _fever_item(1, title="Samme sak", html="Innhold"),
    ]
    store = InMemoryStore(blob_root=tmp_path)
    state = _PollState(tmp_path / "state.json")

    from outbox import NtfyClient

    client = NtfyClient(base_url, "secret-token", "cnr-cat-i")

    first = asyncio.run(
        poll_once(
            store,
            client,
            base_url=fever_server,
            user="admin",
            password="pw",
            vault_path=tmp_path / "vault",
            state=state,
        )
    )
    assert first["pushed"] == 1
    assert len(handler_cls.requests) == 1

    # Second poll: the item is already persisted (same Item.id -> get_item hit)
    # AND the Fever server only returns items above since_id (now 1) — both
    # dedupe layers hold: zero new pushes.
    second = asyncio.run(
        poll_once(
            store,
            client,
            base_url=fever_server,
            user="admin",
            password="pw",
            vault_path=tmp_path / "vault",
            state=state,
        )
    )
    assert second["scored"] == 0
    assert second["skipped"] == 0
    assert second["pushed"] == 0
    assert len(handler_cls.requests) == 1  # unchanged


def test_poll_once_bad_item_does_not_kill_cycle(
    monkeypatch, tmp_path, fever_server, ntfy_server
):
    """One throwing item must not abort the cycle (per-item isolation).

    The bad item is LAST so the since_id cursor stays below it: it is NOT
    advanced on failure and must be re-fetched (and fail again) next cycle
    — while the good item before it is still scored, persisted, and pushed.
    (Known cursor limitation: an item that fails BEFORE a later good item
    advances past it is not retried — logged and accepted for the MVP.)
    """
    calls: list[str] = []

    def flaky_scorer(item_dict):
        title = item_dict.get("title", "")
        calls.append(title)
        if title == "Eksploderende lager":
            raise RuntimeError("LLM timeout")
        return {
            **item_dict,
            "ccir": "CIR-1",
            "cnr": "I",
            "score": 9,
            "bucket": "read",
            "why": "test rationale",
            "pmesii": "Military",
            "tessoc": "none",
        }

    monkeypatch.setattr("poller.score_item", flaky_scorer)
    base_url, handler_cls = ntfy_server
    _FeverHandler.items = [
        _fever_item(1, title="Rutinesak", html="Innhold 1"),
        _fever_item(2, title="Eksploderende lager", html="Innhold 2"),
    ]
    store = InMemoryStore(blob_root=tmp_path)
    state = _PollState(tmp_path / "state.json")

    from outbox import NtfyClient

    client = NtfyClient(base_url, "secret-token", "cnr-cat-i")
    result = asyncio.run(
        poll_once(
            store,
            client,
            base_url=fever_server,
            user="admin",
            password="pw",
            vault_path=tmp_path / "vault",
            state=state,
        )
    )

    # The bad item did not kill the cycle; the good item survived.
    assert result["scored"] == 1
    assert result["pushed"] == 1
    assert len(handler_cls.requests) == 1
    # Cursor stopped at the good item (1); the bad item (2) not advanced.
    assert state.since_id == 1

    # Second poll: cursor below the bad item -> it re-fetches and fails again,
    # the good item is deduped away (store hit) -> no new push.
    second = asyncio.run(
        poll_once(
            store,
            client,
            base_url=fever_server,
            user="admin",
            password="pw",
            vault_path=tmp_path / "vault",
            state=state,
        )
    )
    assert second["scored"] == 0
    assert second["pushed"] == 0
    assert len(handler_cls.requests) == 1  # unchanged
    assert calls.count("Eksploderende lager") == 2  # retried next cycle
    assert state.since_id == 1  # still stuck on the bad item — by design


def test_poll_once_kept_items_write_vault_notes(
    monkeypatch, tmp_path, fever_server, ntfy_server
):
    monkeypatch.setattr("poller.score_item", _fake_scorer({"Viktig sak": "I"}, score=9))
    base_url, _ = ntfy_server
    _FeverHandler.items = [
        _fever_item(1, title="Viktig sak", html="Innhold"),
    ]
    store = InMemoryStore(blob_root=tmp_path)
    state = _PollState(tmp_path / "state.json")
    vault_path = tmp_path / "vault"

    from outbox import NtfyClient

    client = NtfyClient(base_url, "secret-token", "cnr-cat-i")
    asyncio.run(
        poll_once(
            store,
            client,
            base_url=fever_server,
            user="admin",
            password="pw",
            vault_path=vault_path,
            state=state,
        )
    )

    assert vault_path.exists()
    # Item note + SAB written for the kept CAT I item.
    assert any(p.suffix == ".md" for p in vault_path.iterdir())
    sab = vault_path / "obsidian-sab.md"
    assert sab.exists()


def test_health_server_returns_200():
    """The liveness endpoint answers 200 without touching bus or DB.

    Mirrors tests/test_triage_health.py's proven pattern exactly: start the
    module-level handler on an ephemeral port and probe with a raw connection.
    """

    async def _run():
        server = await asyncio.start_server(_handle_health, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.write(b"GET /health HTTP/1.0\r\n\r\n")
            await writer.drain()
            data = await reader.read(200)
            assert b"200" in data
            writer.close()
            await writer.wait_closed()
        finally:
            server.close()
            await server.wait_closed()

    asyncio.run(_run())
