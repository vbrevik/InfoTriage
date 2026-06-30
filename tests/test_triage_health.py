#!/usr/bin/env python3
"""tests/test_triage_health.py — stdlib /health liveness server test (D-04, R7).

Starts the worker's connection handler on an ephemeral port (0), opens a raw
socket connection, sends a minimal HTTP GET, and asserts a 200 response.
Liveness only — does not touch the bus or DB (D-04).
"""
import asyncio

from worker import _handle_health


def test_health_200() -> None:
    async def _run() -> None:
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
