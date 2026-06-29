#!/usr/bin/env python3
"""test_trigger_lock.py — single-instance lock tests for the POST /run trigger (D-01).

Verifies that make_trigger_app enforces the concurrency invariant:
  - First POST /run on an idle app: 200 + {"status": "started"}
  - Second POST /run while first is in-flight: 409 + {"status": "already_running"}
  - After in-flight run completes: next POST /run accepted again (200)
  - Ingest coroutine invoked exactly once during the locked window
  - GET /health returns 200 regardless of run state

Uses httpx.AsyncClient + httpx.ASGITransport (no live server).
"""
import asyncio

import httpx
import pytest

from ingest_common import make_trigger_app


@pytest.mark.asyncio
async def test_trigger_200_then_409_then_200() -> None:
    """Full 200 → 409 → 200 sequence with ingest-count assertion."""
    gate = asyncio.Event()
    invocation_count = 0

    async def slow_ingest() -> None:
        nonlocal invocation_count
        invocation_count += 1
        await gate.wait()  # block until test opens the gate

    app = make_trigger_app(slow_ingest, name="test-adapter")
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # First POST /run — should start the ingest
        r1 = await client.post("/run")
        assert r1.status_code == 200, f"Expected 200, got {r1.status_code}: {r1.text}"
        assert r1.json() == {"status": "started"}

        # Give the task a chance to be scheduled (but ingest blocks on gate)
        await asyncio.sleep(0)

        # Second POST /run while first is in-flight — must be rejected
        r2 = await client.post("/run")
        assert r2.status_code == 409, f"Expected 409, got {r2.status_code}: {r2.text}"
        assert r2.json() == {"status": "already_running"}

        # Ingest was invoked exactly once so far
        assert invocation_count == 1

        # Release the gate — ingest coroutine completes
        gate.set()
        # Let the task finish and the finally block clear the flag
        await asyncio.sleep(0.05)

        # Third POST /run — should be accepted again
        gate.clear()
        r3 = await client.post("/run")
        assert r3.status_code == 200, f"Expected 200, got {r3.status_code}: {r3.text}"
        assert r3.json() == {"status": "started"}

        # Final invocation count: 2 (one for r1, one for r3)
        gate.set()
        await asyncio.sleep(0.05)

    assert invocation_count == 2


@pytest.mark.asyncio
async def test_trigger_health_always_200() -> None:
    """GET /health returns 200 regardless of run state."""
    gate = asyncio.Event()

    async def blocking_ingest() -> None:
        await gate.wait()

    app = make_trigger_app(blocking_ingest, name="health-test")
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Health while idle
        r_idle = await client.get("/health")
        assert r_idle.status_code == 200
        assert r_idle.json() == {"status": "ok"}

        # Start a run (blocks on gate)
        await client.post("/run")
        await asyncio.sleep(0)

        # Health while running
        r_running = await client.get("/health")
        assert r_running.status_code == 200
        assert r_running.json() == {"status": "ok"}

        # Clean up
        gate.set()
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_trigger_lock_cleared_after_exception() -> None:
    """Lock is cleared in finally block even if ingest raises."""
    invocation_count = 0

    async def failing_ingest() -> None:
        nonlocal invocation_count
        invocation_count += 1
        await asyncio.sleep(0)
        raise RuntimeError("simulated ingest failure")

    app = make_trigger_app(failing_ingest, name="exception-test")
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Start run — will raise internally
        r1 = await client.post("/run")
        assert r1.status_code == 200

        # Let the task run and raise
        await asyncio.sleep(0.05)

        # Lock should be cleared — next POST accepted
        r2 = await client.post("/run")
        assert r2.status_code == 200
        assert r2.json() == {"status": "started"}

        # Total: 2 invocations
        await asyncio.sleep(0.05)

    assert invocation_count == 2
