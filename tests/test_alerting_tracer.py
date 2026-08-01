"""test_alerting_tracer.py — Phase 12 Plan 01 tracer.

Proves the whole apps/alerting slice end-to-end without Docker: a CAT I
verdict.ready trigger -> emitter -> Store lookups -> 7-field payload ->
authenticated POST to a stub ntfy server. Also proves the fail-closed
NTFY_TOKEN startup guard via a real subprocess invocation.
"""

from __future__ import annotations

import asyncio
import hashlib
import http.server
import json
import os
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest
from contracts import Item
from store import InMemoryStore

from emitter import build_alert_payload, handle_trigger
from outbox import NtfyClient

REPO_ROOT = Path(__file__).resolve().parents[1]
ALERTING_WORKER = REPO_ROOT / "apps" / "alerting" / "alerting_worker.py"


class _RecordingHandler(http.server.BaseHTTPRequestHandler):
    """Records every POST this stub ntfy server receives."""

    requests: list[dict] = []

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        self.__class__.requests.append(
            {"path": self.path, "headers": dict(self.headers), "body": body}
        )
        self.send_response(200)
        self.end_headers()

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        pass  # silence stub-server access logs during test runs


@pytest.fixture
def stub_ntfy_server():
    """Start a stub ntfy HTTP server on an ephemeral localhost port."""
    _RecordingHandler.requests = []
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _RecordingHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    try:
        yield f"http://127.0.0.1:{port}", _RecordingHandler
    finally:
        server.shutdown()
        thread.join(timeout=5)


def _make_item(url_seed: str) -> Item:
    return Item(
        source="Test Source",
        source_type="rss",
        url=f"https://example.com/{url_seed}",
        title="A CAT I test item",
        ts=datetime.now(tz=timezone.utc),
        lang="en",
        summary="fallback summary text",
    )


def _seed(store: InMemoryStore, item: Item, *, cnr: str, why: str, pmesii: str) -> str:
    store.put_item(item)
    store.put_enrichment(
        item.id,
        {
            "ccir": None,
            "cnr": cnr,
            "score": 9,
            "bucket": "keep",
            "why": why,
            "pmesii": pmesii,
            "tessoc": None,
        },
    )
    return item.id


def test_cat_i_produces_exactly_one_authenticated_post(stub_ntfy_server, tmp_path):
    base_url, handler_cls = stub_ntfy_server
    store = InMemoryStore(blob_root=tmp_path)
    item = _make_item("cat-i-1")
    item_id = _seed(store, item, cnr="I", why="rationale text", pmesii="M, P , E,")

    client = NtfyClient(base_url, "secret-token-value", "cnr-cat-i")
    asyncio.run(
        handle_trigger(item_id, {"event": "verdict.ready", "cnr": "I"}, store, client)
    )

    assert len(handler_cls.requests) == 1
    req = handler_cls.requests[0]
    assert req["path"].endswith("/cnr-cat-i")
    assert req["headers"]["Authorization"].startswith("Bearer ")
    assert "secret-token-value" in req["headers"]["Authorization"]

    body = json.loads(req["body"])
    assert sorted(body.keys()) == [
        "alert_id",
        "cnr_tier",
        "dedupe_id",
        "deep_link",
        "item_link",
        "pmseii_tags",
        "sab_excerpt",
    ]
    assert body["pmseii_tags"] == ["M", "P", "E"]
    expected_dedupe = hashlib.sha256(f"{item_id}|I".encode()).hexdigest()[:16]
    assert body["dedupe_id"] == expected_dedupe
    assert len(body["dedupe_id"]) == 16
    assert body["deep_link"].startswith("obsidian://open?vault=")
    assert body["item_link"].startswith("obsidian://open?vault=")


@pytest.mark.parametrize("cnr", ["II", "Routine"])
def test_non_cat_i_produces_zero_posts(stub_ntfy_server, tmp_path, cnr):
    base_url, handler_cls = stub_ntfy_server
    store = InMemoryStore(blob_root=tmp_path)
    item = _make_item(f"non-cat-i-{cnr}")
    item_id = _seed(store, item, cnr=cnr, why="rationale text", pmesii="")

    client = NtfyClient(base_url, "secret-token-value", "cnr-cat-i")
    asyncio.run(
        handle_trigger(item_id, {"event": "verdict.ready", "cnr": cnr}, store, client)
    )

    assert len(handler_cls.requests) == 0


def test_sab_excerpt_capped_at_500_chars(tmp_path):
    store = InMemoryStore(blob_root=tmp_path)
    item = _make_item("long-excerpt")
    long_why = "x" * 5000
    item_id = _seed(store, item, cnr="I", why=long_why, pmesii="")
    enrichment = store.get_enrichment(item_id)

    payload = build_alert_payload(item, enrichment, item_id, "I")

    assert len(payload["sab_excerpt"]) <= 500


def test_fail_closed_on_missing_ntfy_token():
    env = os.environ.copy()
    env.pop("NTFY_TOKEN", None)
    pythonpath_parts = [
        str(REPO_ROOT / "libs" / "contracts" / "src"),
        str(REPO_ROOT / "libs" / "store" / "src"),
    ]
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = os.pathsep.join(
        pythonpath_parts + ([existing] if existing else [])
    )

    result = subprocess.run(
        [sys.executable, str(ALERTING_WORKER), "--dsn", "X", "--amqp-dsn", "Y"],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )

    assert result.returncode != 0
    assert "NTFY_TOKEN" in result.stderr


def test_outbox_never_logs_token_or_authorization():
    """No log.*()/print() call in outbox.py references the token or headers.

    Walks the AST rather than grepping lines so a multi-line call (like the
    log.info(...) delivery-confirmation call) is checked as a whole unit.
    """
    import ast

    outbox_path = REPO_ROOT / "apps" / "alerting" / "outbox.py"
    tree = ast.parse(outbox_path.read_text())
    forbidden_names = {"token", "headers", "Authorization"}

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        is_log_call = (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "log"
        )
        is_print_call = isinstance(func, ast.Name) and func.id == "print"
        if not (is_log_call or is_print_call):
            continue
        call_source = ast.dump(node)
        for forbidden in forbidden_names:
            assert (
                forbidden not in call_source
            ), f"log/print call references {forbidden!r}: {ast.unparse(node)}"
