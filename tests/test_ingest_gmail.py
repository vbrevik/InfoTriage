#!/usr/bin/env python3
"""test_ingest_gmail.py — R3 unit tests for ingest-gmail MCP client adapter.

Verifies:
  - fetch_items() maps Gmail messages to Item with source_type="gmail"
  - ingest() produces >=1 row + >=1 item.ingested event on first run
  - Re-running ingest() over identical messages yields no new event (R6 idempotency)
  - Only read-only MCP tool names appear in the adapter source (static check)
  - No Python MCP SDK imports (D-05 — raw httpx only)

MCP transport is mocked via monkeypatching mcp_client.init_mcp_session and
mcp_client.mcp_call to return a single fake Gmail message (no network required).
"""
import datetime
import pathlib
import re

import pytest

from contracts import InMemoryBus, Item
from store import InMemoryStore


# ---------------------------------------------------------------------------
# Fake Gmail message as returned by @shinzolabs/gmail-mcp get_message tool
# (JSON-RPC result.content[0].text is a JSON string of the message object)
# ---------------------------------------------------------------------------
FAKE_MESSAGE_ID = "18f2e3a1b9c4d5e6"
FAKE_SUBJECT = "Test newsletter from Acme"
FAKE_SNIPPET = "Here is the weekly update from Acme Corp."
FAKE_DATE = "Mon, 29 Jun 2026 10:00:00 +0000"

FAKE_MCP_LIST_RESULT = {
    "result": {
        "content": [
            {
                "type": "text",
                "text": (
                    f'{{"messages": [{{"id": "{FAKE_MESSAGE_ID}", '
                    f'"threadId": "thread-abc123"}}]}}'
                ),
            }
        ]
    }
}

FAKE_MCP_GET_RESULT = {
    "result": {
        "content": [
            {
                "type": "text",
                "text": (
                    f'{{"id": "{FAKE_MESSAGE_ID}", '
                    f'"snippet": "{FAKE_SNIPPET}", '
                    f'"payload": {{"headers": ['
                    f'{{"name": "Subject", "value": "{FAKE_SUBJECT}"}}, '
                    f'{{"name": "Date", "value": "{FAKE_DATE}"}}, '
                    f'{{"name": "From", "value": "Acme <news@acme.com>"}}'
                    f"]}}}}"
                ),
            }
        ]
    }
}


@pytest.fixture()
def mock_mcp(monkeypatch):
    """Monkeypatch mcp_client so no real HTTP calls are made."""
    import mcp_client

    call_count = {"n": 0}

    async def fake_init_mcp_session(client):
        return "fake-session-id"

    async def fake_mcp_call(client, session_id, method, params):
        name = params.get("name", "") if method == "tools/call" else method
        if name == "list_messages":
            return FAKE_MCP_LIST_RESULT
        elif name == "get_message":
            return FAKE_MCP_GET_RESULT
        return {"result": {}}

    monkeypatch.setattr(mcp_client, "init_mcp_session", fake_init_mcp_session)
    monkeypatch.setattr(mcp_client, "mcp_call", fake_mcp_call)
    return call_count


# ---------------------------------------------------------------------------
# Test: fetch_items produces Item with source_type="gmail"
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_fetch_items_source_type(mock_mcp, tmp_path):
    """fetch_items maps a Gmail message to Item(source_type='gmail')."""
    import gmail_ingest

    # Simulate a single message dict (as built after get_message call)
    messages = [
        {
            "id": FAKE_MESSAGE_ID,
            "snippet": FAKE_SNIPPET,
            "subject": FAKE_SUBJECT,
            "date": FAKE_DATE,
        }
    ]

    items = gmail_ingest.fetch_items(messages)
    assert len(items) == 1
    item = items[0]
    assert isinstance(item, Item)
    assert item.source_type == "gmail"
    assert item.url == f"gmail://message/{FAKE_MESSAGE_ID}"
    assert item.title == FAKE_SUBJECT
    assert item.summary == FAKE_SNIPPET[:500]
    # ts must be tz-aware
    assert item.ts.tzinfo is not None


# ---------------------------------------------------------------------------
# Test: ingest() produces 1 row + 1 event on first run
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ingest_first_run(mock_mcp, monkeypatch, tmp_path):
    """First ingest() run: 1 gmail row in store, 1 item.ingested event."""
    store = InMemoryStore(blob_root=tmp_path / "blobs")
    bus = InMemoryBus()

    import gmail_ingest

    # Patch build_store / build_bus to return test doubles
    monkeypatch.setattr(gmail_ingest, "_build_store", lambda: store)
    monkeypatch.setattr(gmail_ingest, "_build_bus", lambda: bus)

    await gmail_ingest.ingest()

    items = store.list_items(source_type_in=["gmail"])
    assert len(items) == 1
    assert items[0].source_type == "gmail"

    events = await bus.subscribe("item.ingested")
    assert len(events) == 1
    assert events[0]["source_type"] == "gmail"


# ---------------------------------------------------------------------------
# Test: re-running ingest() with same messages yields no new event (R6)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ingest_idempotency(mock_mcp, monkeypatch, tmp_path):
    """Second ingest() run over same messages: no new row, no new event."""
    store = InMemoryStore(blob_root=tmp_path / "blobs")
    bus = InMemoryBus()

    import gmail_ingest

    monkeypatch.setattr(gmail_ingest, "_build_store", lambda: store)
    monkeypatch.setattr(gmail_ingest, "_build_bus", lambda: bus)

    await gmail_ingest.ingest()
    await gmail_ingest.ingest()

    items = store.list_items(source_type_in=["gmail"])
    assert len(items) == 1  # still exactly one row

    events = await bus.subscribe("item.ingested")
    assert len(events) == 1  # exactly one event, not two (R6)


# ---------------------------------------------------------------------------
# Static check: only read-only tool names in adapter source
# ---------------------------------------------------------------------------
def test_no_write_tool_names_in_source():
    """No mutating Gmail MCP tool names appear in the adapter source files."""
    import pathlib

    adapter_root = pathlib.Path(__file__).parent.parent / "apps" / "ingest-gmail"
    write_tools = re.compile(
        r"send_message|send_email|create_draft|trash|modify_message|delete_message|mark_read|markAsRead",
        re.IGNORECASE,
    )

    for path in adapter_root.glob("*.py"):
        source = path.read_text()
        # Exclude pure comments (# ...) — check non-comment occurrences
        non_comment_lines = [
            line for line in source.splitlines() if not line.lstrip().startswith("#")
        ]
        non_comment_source = "\n".join(non_comment_lines)
        match = write_tools.search(non_comment_source)
        assert match is None, (
            f"Write tool name '{match.group()}' found in {path.name} "
            "(only read-only tools allowed — ADR-004, T-04-13)"
        )


# ---------------------------------------------------------------------------
# Static check: no Python MCP SDK import (D-05 — raw httpx only)
# ---------------------------------------------------------------------------
def test_no_python_mcp_sdk():
    """No 'import mcp' or 'from mcp' in ingest-gmail source (D-05)."""
    adapter_root = pathlib.Path(__file__).parent.parent / "apps" / "ingest-gmail"
    mcp_import = re.compile(r"^\s*(import mcp\b|from mcp\b)", re.MULTILINE)

    for path in adapter_root.glob("*.py"):
        source = path.read_text()
        assert not mcp_import.search(source), (
            f"Python MCP SDK import found in {path.name} — "
            "D-05 requires raw httpx JSON-RPC only"
        )
