#!/usr/bin/env python3
"""mcp_client.py — raw httpx JSON-RPC client for @shinzolabs/gmail-mcp.

Implements D-05: the ingest-gmail adapter calls the Gmail MCP server via raw
httpx JSON-RPC requests. No Python MCP SDK is used or imported.

MCP Streamable HTTP transport (2025-03-26 spec):
  - Every JSON-RPC message = new HTTP POST to /mcp endpoint
  - Accept: application/json, text/event-stream (required by spec)
  - Session tracking via Mcp-Session-Id header (server returns it on initialize)
  - First call MUST be initialize; subsequent calls include the session ID
  - Tools called via tools/call method with name + arguments

Security: Only read-only Gmail tools are called — list_messages, get_message,
list_threads, get_thread. Write/mutate tool names are absent from this module
(T-04-13, ADR-004, ADR-008).
"""
import itertools
import os

import httpx

# ---------------------------------------------------------------------------
# Configuration — injected from environment at runtime
# ---------------------------------------------------------------------------
GMAIL_MCP_URL: str = os.environ.get("GMAIL_MCP_URL", "http://gmail-mcp-server:3000")
# MCP Streamable HTTP endpoint path (confirmed: @shinzolabs/gmail-mcp binds /mcp)
_ENDPOINT: str = "/mcp"

_id_counter = itertools.count(1)


# ---------------------------------------------------------------------------
# Core JSON-RPC helpers
# ---------------------------------------------------------------------------

async def mcp_call(
    client: httpx.AsyncClient,
    session_id: str,
    method: str,
    params: dict,
) -> dict:
    """POST one JSON-RPC 2.0 request to the MCP endpoint; return the response dict.

    Args:
        client:     An open httpx.AsyncClient instance.
        session_id: MCP session ID from init_mcp_session; empty string for the
                    initialize call itself.
        method:     JSON-RPC method (e.g. "initialize", "tools/call").
        params:     Method parameters dict.

    Returns:
        Parsed JSON response body (full envelope including "result" key).

    Raises:
        httpx.HTTPStatusError: on 4xx/5xx from the MCP server.
    """
    body = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params,
        "id": next(_id_counter),
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if session_id:
        headers["Mcp-Session-Id"] = session_id

    url = f"{GMAIL_MCP_URL}{_ENDPOINT}"
    resp = await client.post(url, json=body, headers=headers, timeout=30.0)
    resp.raise_for_status()
    return resp.json()


async def init_mcp_session(client: httpx.AsyncClient) -> str:
    """Initialize an MCP session and return the session ID.

    Sends the mandatory initialize call (protocolVersion 2025-03-26) and
    extracts the session ID from the server response.

    Args:
        client: An open httpx.AsyncClient instance.

    Returns:
        Session ID string (may be empty if server doesn't return one).
    """
    resp = await mcp_call(
        client,
        "",  # no session ID for the initialize call
        "initialize",
        {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "ingest-gmail", "version": "1.0"},
        },
    )
    # Session ID may come from result.sessionId or from the Mcp-Session-Id header
    return resp.get("result", {}).get("sessionId", "")


# ---------------------------------------------------------------------------
# Read-only Gmail tool wrappers (list/get only — no mutating operations)
# ---------------------------------------------------------------------------

async def list_messages(
    client: httpx.AsyncClient,
    session_id: str,
    query: str = "newer_than:7d",
    max_results: int = 50,
) -> list[dict]:
    """Call the list_messages MCP tool; return the list of message stubs.

    Each stub is a dict with at least "id" and "threadId" keys.
    """
    result = await mcp_call(
        client,
        session_id,
        "tools/call",
        {
            "name": "list_messages",
            "arguments": {
                "query": query,
                "maxResults": max_results,
            },
        },
    )
    # @shinzolabs/gmail-mcp wraps the result in content[0].text as JSON string
    import json as _json
    content = result.get("result", {}).get("content", [])
    if content and content[0].get("type") == "text":
        try:
            data = _json.loads(content[0]["text"])
            return data.get("messages", [])
        except (ValueError, KeyError):
            pass
    return []


async def get_message(
    client: httpx.AsyncClient,
    session_id: str,
    message_id: str,
) -> dict:
    """Call the get_message MCP tool; return the full message dict.

    Returns a dict with id, snippet, payload.headers (at minimum).
    """
    result = await mcp_call(
        client,
        session_id,
        "tools/call",
        {
            "name": "get_message",
            "arguments": {
                "messageId": message_id,
                "format": "metadata",
                "metadataHeaders": ["Subject", "Date", "From"],
            },
        },
    )
    import json as _json
    content = result.get("result", {}).get("content", [])
    if content and content[0].get("type") == "text":
        try:
            return _json.loads(content[0]["text"])
        except (ValueError, KeyError):
            pass
    return {}
