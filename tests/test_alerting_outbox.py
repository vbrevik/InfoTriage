"""tests/test_alerting_outbox.py — SPEC R4 outbox retry + dead-letter.

Proves the egress path is lossless: a stubbed-dead ntfy causes exactly 3 POST
attempts on the 1s/5s locked schedule, then one message on outbox.dlx and one
audit row (Test 3); a transient failure that recovers on retry produces
exactly one delivered message and zero dead-letter messages (Tests 1/2); a
connection error is treated identically to a non-2xx response (Test 5); the
dead-letter message and audit row carry enough to reconstruct the alert and
explain the failure (Tests 6/7); and a failure to durably record the outcome
propagates rather than being swallowed, so the trigger message is never
falsely acked (Test 8).
"""

from __future__ import annotations

import asyncio
import hashlib
import http.server
import socket
import threading

import pytest
from store import InMemoryStore

import outbox
from outbox import DLX_ROUTING_KEY, RETRY_SCHEDULE, NtfyClient, dead_letter, deliver_with_retry


# ---------------------------------------------------------------------------
# Fixtures / fakes
# ---------------------------------------------------------------------------


class _SequencedHandler(http.server.BaseHTTPRequestHandler):
    """Stub ntfy server whose response status code sequence the test controls.

    class-level `status_codes` is consumed one per request, in order; once
    exhausted, the last code repeats.
    """

    status_codes: list[int] = [200]
    requests: list[dict] = []

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        idx = len(self.__class__.requests)
        self.__class__.requests.append(
            {"path": self.path, "headers": dict(self.headers), "body": body}
        )
        codes = self.__class__.status_codes
        code = codes[idx] if idx < len(codes) else codes[-1]
        self.send_response(code)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, format, *args) -> None:  # noqa: A002
        pass  # silence stub-server access logs during test runs


@pytest.fixture
def sequenced_ntfy_server():
    """Factory fixture: call with a status-code sequence, get (base_url, handler_cls)."""
    servers: list[tuple[http.server.ThreadingHTTPServer, threading.Thread]] = []

    def _start(status_codes: list[int]):
        _SequencedHandler.status_codes = list(status_codes)
        _SequencedHandler.requests = []
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _SequencedHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        servers.append((server, thread))
        port = server.server_address[1]
        return f"http://127.0.0.1:{port}", _SequencedHandler

    yield _start

    for server, thread in servers:
        server.shutdown()
        thread.join(timeout=5)


def _dead_port_url() -> str:
    """Return a URL pointing at a port nothing listens on (real ECONNREFUSED).

    Binds an ephemeral port, then closes it immediately — freeing it while
    guaranteeing nothing else grabs it in the tiny window before the test's
    connection attempt.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return f"http://127.0.0.1:{port}"


class FakeBus:
    """Records every publish — routing key, item id, payload."""

    def __init__(self) -> None:
        self.published: list[tuple[str, str, dict]] = []

    async def publish(self, routing_key: str, item_id: str, payload: dict) -> None:
        self.published.append((routing_key, item_id, payload))


@pytest.fixture(autouse=True)
def sleep_calls(monkeypatch):
    """Patch outbox.asyncio.sleep so the suite runs in well under a second
    while still asserting the requested delay values."""
    calls: list[float] = []

    async def _fake_sleep(delay: float) -> None:
        calls.append(delay)

    monkeypatch.setattr(outbox.asyncio, "sleep", _fake_sleep)
    return calls


def _payload(item_id: str, cnr_tier: str = "I") -> dict:
    dedupe_id = hashlib.sha256(f"{item_id}|{cnr_tier}".encode()).hexdigest()[:16]
    return {
        "alert_id": f"alert-{item_id}",
        "sab_excerpt": "excerpt text",
        "dedupe_id": dedupe_id,
        "cnr_tier": cnr_tier,
        "item_link": "obsidian://open?vault=x&file=sab",
        "pmseii_tags": ["M", "P"],
        "deep_link": f"obsidian://open?vault=x&file={item_id}",
    }


def _seed_claim(store: InMemoryStore, payload: dict, item_id: str) -> None:
    """Create the alert_state row deliver_with_retry/dead_letter will update
    — mirrors the real flow where dedupe.claim() runs before delivery."""
    store.claim_alert(
        payload["dedupe_id"], item_id, payload["cnr_tier"], payload["alert_id"]
    )


def _raw_row(store: InMemoryStore, dedupe_id: str) -> dict | None:
    row = store._alert_state.get(dedupe_id)
    return dict(row) if row is not None else None


# ---------------------------------------------------------------------------
# Test 1: first attempt succeeds
# ---------------------------------------------------------------------------


def test_first_attempt_success_yields_one_post_and_delivered_outcome(
    sequenced_ntfy_server, tmp_path
):
    base_url, handler_cls = sequenced_ntfy_server([200])
    store = InMemoryStore(blob_root=tmp_path)
    bus = FakeBus()
    client = NtfyClient(base_url, "secret-token", "cnr-cat-i")
    item_id = "item-1"
    payload = _payload(item_id)
    _seed_claim(store, payload, item_id)

    asyncio.run(deliver_with_retry(client, store, bus, payload, item_id=item_id))

    assert len(handler_cls.requests) == 1
    assert bus.published == []
    row = _raw_row(store, payload["dedupe_id"])
    assert row["delivered_at"] is not None
    assert row["dlx_at"] is None


# ---------------------------------------------------------------------------
# Test 2: transient failure recovers on retry
# ---------------------------------------------------------------------------


def test_500_then_200_yields_two_posts_delivered_zero_dead_letters(
    sequenced_ntfy_server, tmp_path
):
    base_url, handler_cls = sequenced_ntfy_server([500, 200])
    store = InMemoryStore(blob_root=tmp_path)
    bus = FakeBus()
    client = NtfyClient(base_url, "secret-token", "cnr-cat-i")
    item_id = "item-2"
    payload = _payload(item_id)
    _seed_claim(store, payload, item_id)

    asyncio.run(deliver_with_retry(client, store, bus, payload, item_id=item_id))

    assert len(handler_cls.requests) == 2
    assert bus.published == []
    row = _raw_row(store, payload["dedupe_id"])
    assert row["delivered_at"] is not None
    assert row["dlx_at"] is None


# ---------------------------------------------------------------------------
# Test 3: always-500 exhausts retries, dead-letters, writes audit
# ---------------------------------------------------------------------------


def test_always_500_yields_three_posts_one_dead_letter_one_audit_row(
    sequenced_ntfy_server, tmp_path
):
    base_url, handler_cls = sequenced_ntfy_server([500, 500, 500])
    store = InMemoryStore(blob_root=tmp_path)
    bus = FakeBus()
    client = NtfyClient(base_url, "secret-token", "cnr-cat-i")
    item_id = "item-3"
    payload = _payload(item_id)
    _seed_claim(store, payload, item_id)

    asyncio.run(deliver_with_retry(client, store, bus, payload, item_id=item_id))

    assert len(handler_cls.requests) == 3

    dlx_publishes = [p for p in bus.published if p[0] == DLX_ROUTING_KEY]
    assert len(dlx_publishes) == 1
    _, dlx_item_id, dlx_payload = dlx_publishes[0]
    assert dlx_item_id == item_id
    for key in (
        "alert_id",
        "sab_excerpt",
        "dedupe_id",
        "cnr_tier",
        "item_link",
        "pmseii_tags",
        "deep_link",
    ):
        assert dlx_payload[key] == payload[key]
    assert "reason" in dlx_payload
    assert dlx_payload["attempts"] == 3

    audit_rows = store._audit
    dead_letter_rows = [r for r in audit_rows if r["op"] == "alert_dead_lettered"]
    assert len(dead_letter_rows) == 1
    details = dead_letter_rows[0]["details"]
    assert details["alert_id"] == payload["alert_id"]
    assert details["dedupe_id"] == payload["dedupe_id"]
    assert details["attempts"] == 3

    row = _raw_row(store, payload["dedupe_id"])
    assert row["dlx_at"] is not None
    assert row["delivered_at"] is None


# ---------------------------------------------------------------------------
# Test 4: retry timing — sleep(1) then sleep(5), no third sleep
# ---------------------------------------------------------------------------


def test_retry_schedule_sleeps_one_then_five_only(
    sequenced_ntfy_server, tmp_path, sleep_calls
):
    assert RETRY_SCHEDULE == (1, 5)
    base_url, handler_cls = sequenced_ntfy_server([500, 500, 500])
    store = InMemoryStore(blob_root=tmp_path)
    bus = FakeBus()
    client = NtfyClient(base_url, "secret-token", "cnr-cat-i")
    item_id = "item-4"
    payload = _payload(item_id)
    _seed_claim(store, payload, item_id)

    asyncio.run(deliver_with_retry(client, store, bus, payload, item_id=item_id))

    assert sleep_calls == [1, 5]


# ---------------------------------------------------------------------------
# Test 5: connection error treated the same as non-2xx
# ---------------------------------------------------------------------------


def test_connection_error_on_every_attempt_dead_letters_like_always_500(tmp_path):
    dead_url = _dead_port_url()
    store = InMemoryStore(blob_root=tmp_path)
    bus = FakeBus()
    client = NtfyClient(dead_url, "secret-token", "cnr-cat-i")
    item_id = "item-5"
    payload = _payload(item_id)
    _seed_claim(store, payload, item_id)

    asyncio.run(deliver_with_retry(client, store, bus, payload, item_id=item_id))

    dlx_publishes = [p for p in bus.published if p[0] == DLX_ROUTING_KEY]
    assert len(dlx_publishes) == 1
    assert dlx_publishes[0][2]["attempts"] == 3

    row = _raw_row(store, payload["dedupe_id"])
    assert row["dlx_at"] is not None
    assert row["delivered_at"] is None


# ---------------------------------------------------------------------------
# Test 6: dead-letter body carries the full 7-field payload + reason/attempts
# (also covered inline in Test 3; this test isolates dead_letter() directly)
# ---------------------------------------------------------------------------


def test_dead_letter_body_carries_full_payload_plus_reason_and_attempts(tmp_path):
    store = InMemoryStore(blob_root=tmp_path)
    bus = FakeBus()
    item_id = "item-6"
    payload = _payload(item_id)
    _seed_claim(store, payload, item_id)

    asyncio.run(
        dead_letter(
            store, bus, payload, item_id=item_id, reason="boom", attempts=3
        )
    )

    _, dlx_item_id, dlx_payload = bus.published[0]
    assert dlx_item_id == item_id
    for key, value in payload.items():
        assert dlx_payload[key] == value
    assert dlx_payload["reason"] == "boom"
    assert dlx_payload["attempts"] == 3


# ---------------------------------------------------------------------------
# Test 7: audit row op/details are reconstructable
# ---------------------------------------------------------------------------


def test_dead_letter_audit_row_op_and_details(tmp_path):
    store = InMemoryStore(blob_root=tmp_path)
    bus = FakeBus()
    item_id = "item-7"
    payload = _payload(item_id)
    _seed_claim(store, payload, item_id)

    asyncio.run(
        dead_letter(
            store, bus, payload, item_id=item_id, reason="boom", attempts=3
        )
    )

    assert len(store._audit) == 1
    row = store._audit[0]
    assert row["op"] == "alert_dead_lettered"
    assert row["item_id"] == item_id
    assert row["details"]["alert_id"] == payload["alert_id"]
    assert row["details"]["dedupe_id"] == payload["dedupe_id"]
    assert row["details"]["attempts"] == 3


# ---------------------------------------------------------------------------
# Test 8: ack-after-record — a failure recording the outcome must propagate
# ---------------------------------------------------------------------------


class _RaisingOutcomeStore(InMemoryStore):
    """A Store whose mark_alert_outcome raises — proves the handler
    propagates the exception rather than swallowing it, so the caller's
    message.process() context does not falsely ack (T-12-32)."""

    def mark_alert_outcome(self, dedupe_id, *, outcome, now=None):  # type: ignore[override]
        raise RuntimeError("simulated durable-record failure")


def test_ack_after_record_propagates_on_outcome_recording_failure(
    sequenced_ntfy_server, tmp_path
):
    base_url, handler_cls = sequenced_ntfy_server([200])
    store = _RaisingOutcomeStore(blob_root=tmp_path)
    bus = FakeBus()
    client = NtfyClient(base_url, "secret-token", "cnr-cat-i")
    item_id = "item-8"
    payload = _payload(item_id)
    _seed_claim(store, payload, item_id)

    with pytest.raises(RuntimeError, match="simulated durable-record failure"):
        asyncio.run(deliver_with_retry(client, store, bus, payload, item_id=item_id))


def test_ack_after_record_propagates_via_emit_path_not_swallowed(tmp_path):
    """Drives the full emit path (claim -> deliver_with_retry) with a store
    whose outcome-recording method raises, confirming handle_verdict_ready
    itself propagates rather than swallowing (Task 2 Test 8, full-path
    variant)."""
    from datetime import datetime, timezone

    from contracts import Item
    from emitter import handle_verdict_ready

    store = _RaisingOutcomeStore(blob_root=tmp_path)
    item = Item(
        source="Test Source",
        source_type="rss",
        url="https://example.com/item-8b",
        title="A CAT I test item",
        ts=datetime.now(tz=timezone.utc),
        lang="en",
        summary="fallback summary text",
    )
    store.put_item(item)
    store.put_enrichment(
        item.id,
        {
            "ccir": None,
            "cnr": "I",
            "score": 9,
            "bucket": "keep",
            "why": "rationale",
            "pmesii": "",
            "tessoc": None,
        },
    )

    class _AlwaysOkClient:
        async def deliver(self, payload, item_title=""):
            return None

    bus = FakeBus()
    with pytest.raises(RuntimeError, match="simulated durable-record failure"):
        asyncio.run(
            handle_verdict_ready(
                {"event": "verdict.ready", "item_id": item.id, "cnr": "I"},
                store,
                _AlwaysOkClient(),
                bus=bus,
            )
        )
