#!/bin/sh
# entrypoint.sh — launch @shinzolabs/gmail-mcp in Streamable HTTP transport mode.
#
# PORT must be set (default 3000) to force HTTP transport.
# Without PORT the server defaults to stdio — the Python adapter would get
# "connection refused" from httpx (RESEARCH Pitfall 3).
#
# All credentials (CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN) come from the
# docker-compose env_file (.env) — never baked into this image (NF-6, ADR-008).

export PORT="${PORT:-3000}"

exec npx @shinzolabs/gmail-mcp
