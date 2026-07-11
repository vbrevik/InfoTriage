#!/usr/bin/env python3
"""trigger.py — FastAPI single-instance lock trigger for InfoTriage ingest adapters.

Implements the D-01/D-02 trigger pattern: a minimal FastAPI app with two routes:
  POST /run    — starts the ingest coroutine if no run is in progress (D-01 single-instance lock)
  GET  /health — liveness probe; always returns 200

The in-flight flag is set SYNCHRONOUSLY (no await between the 409 check and the flag
assignment) so concurrent POSTs cannot both pass the gate. The flag is cleared inside a
finally block so a crashed run never permanently wedges the lock.

Usage:
    from ingest_common import make_trigger_app

    async def my_ingest_coro() -> None:
        ...

    app = make_trigger_app(my_ingest_coro, name="imap-adapter")
    # uvicorn.run(app, host="0.0.0.0", port=8080)
"""
import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import Any

from contracts import setup_logging
from fastapi import FastAPI
from fastapi.responses import JSONResponse

log = logging.getLogger(__name__)


def make_trigger_app(
    ingest_coro: Callable[[], Coroutine[Any, Any, None]],
    *,
    name: str,
) -> FastAPI:
    """Build the POST /run + GET /health FastAPI app with a single-instance lock.

    Args:
        ingest_coro: A zero-argument async callable that performs the ingest run.
                     It will be invoked via asyncio.create_task() so the POST /run
                     handler returns immediately.
        name:        Human-readable adapter name for log messages.

    Returns:
        A configured FastAPI application. Mount or run with uvicorn.

    Concurrency contract (D-01):
        - The in-flight flag is set with NO await between the 409 check and the set.
        - This eliminates the race window: two concurrent POSTs cannot both see
          in_flight=False and both proceed past the gate.
        - The flag is cleared in a finally block, so crashes never wedge the lock.
    """
    setup_logging(name)

    app = FastAPI(title=name)

    # Single-element dict used as a mutable flag (closure-friendly without nonlocal)
    _state: dict[str, bool] = {"in_flight": False}

    async def _wrap() -> None:
        """Run ingest_coro and clear the flag in finally (crash-safe)."""
        try:
            await ingest_coro()
        except Exception:
            log.exception("Ingest run raised an exception in %s — clearing lock", name)
        finally:
            _state["in_flight"] = False
            log.debug("Ingest lock cleared for %s", name)

    @app.post("/run")
    async def run() -> JSONResponse:
        """Start an ingest run if no run is currently in progress.

        Returns 200 + {"status": "started"} when the run is started.
        Returns 409 + {"status": "already_running"} when a run is in progress.

        The in-flight flag is set SYNCHRONOUSLY before the first await to eliminate
        the concurrency race window (D-01).
        """
        # Check and set flag synchronously — no await between check and set (D-01)
        if _state["in_flight"]:
            log.debug("POST /run rejected — %s already in flight", name)
            return JSONResponse(status_code=409, content={"status": "already_running"})

        # Set flag synchronously before scheduling the task (no await before this line)
        _state["in_flight"] = True
        asyncio.create_task(_wrap())
        log.info("POST /run — started ingest run for %s", name)
        return JSONResponse(status_code=200, content={"status": "started"})

    @app.get("/health")
    async def health() -> dict[str, str]:
        """Liveness probe — always returns 200 + {"status": "ok"}."""
        return {"status": "ok"}

    return app
