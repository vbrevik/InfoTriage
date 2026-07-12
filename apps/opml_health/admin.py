"""opml-health admin dashboard — aggregated health endpoint for all services.

Polls all containerized services' /health endpoints and returns aggregated status.
"""

import asyncio
import logging
import os
import sys
from typing import Any

import httpx
from contracts import LOGGING_CONFIG, setup_logging
from fastapi import FastAPI, Response

setup_logging("opml-health-admin")
log = logging.getLogger("opml.health.admin")


app = FastAPI(title="opml-health-admin", version="0.1.0")

# Service registry: service_name -> (host, port, health_path)
SERVICES: list[tuple[str, str, int, str]] = [
    ("ingest-imap", "ingest-imap", 22010, "/health"),
    ("ingest-youtube", "ingest-youtube", 22011, "/health"),
    ("ingest-obsidian", "ingest-obsidian", 22012, "/health"),
    ("triage", "triage", 22030, "/health"),
    ("brief", "brief", 22040, "/health"),
    ("freshrss", "freshrss", 8088, "/"),
    ("rssbridge", "rssbridge", 3000, "/"),
    ("feeds", "feeds", 80, "/"),
]


async def _probe_health(host: str, port: int, path: str) -> dict[str, Any]:
    """Probe a single service's health endpoint."""
    url = f"http://{host}:{port}{path}"
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                return {"status": "up"}
            return {"status": "degraded", "code": resp.status_code}
    except Exception as exc:
        return {"status": "down", "error": str(exc)[:120]}


@app.get("/health")
async def health() -> Response:
    """Basic liveness check for this service."""
    return Response(content="ok", media_type="text/plain", status_code=200)


@app.get("/admin/health")
async def admin_health() -> dict:
    """Aggregate health of all services.

    Returns:
        {
            "status": "up" | "degraded" | "down",
            "services": {
                "ingest-imap": {"status": "up"},
                "triage": {"status": "up"},
                ...
            },
            "total_services": N,
            "up": N,
            "down": N,
        }
    """
    results: dict[str, dict] = {}
    coros = [_probe_health(host, port, path) for name, host, port, path in SERVICES]
    gathered = await asyncio.gather(*coros, return_exceptions=True)

    for i, res in enumerate(gathered):
        name = SERVICES[i][0]
        if isinstance(res, BaseException):
            results[name] = {"status": "down", "error": str(res)[:120]}
        else:
            results[name] = res

    up = sum(1 for r in results.values() if r.get("status") == "up")
    down = sum(1 for r in results.values() if r.get("status") == "down")

    if down == len(results) and len(results) > 0:
        overall = "down"
    elif down == 0:
        overall = "up"
    else:
        overall = "degraded"

    log.info(
        "Health check: %d up, %d down, overall=%s",
        up,
        down,
        overall,
    )

    return {
        "status": overall,
        "services": results,
        "total_services": len(results),
        "up": up,
        "down": down,
    }


if __name__ == "__main__":
    import uvicorn

    # Phase 7 07-02: route uvicorn's access / error / info loggers through the
    # JSONFormatter via contracts.LOGGING_CONFIG. `disable_existing_loggers=False`
    # keeps our setup_logging()'s root handlers (stdout + rotating file) alive.
    port = int(os.environ.get("INFOTRIAGE_OPML_HEALTH_PORT", "22032"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_config=LOGGING_CONFIG)
