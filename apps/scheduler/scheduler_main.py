"""
scheduler_main.py — APScheduler 3.x cron scheduler for InfoTriage adapters.

Fires each adapter's POST /run on a per-adapter cron schedule.
- 200: adapter started  → log info "[name] started (200)"
- 409: already running  → log info "[name] skipped — already running (409)"
- other: unexpected     → log warning
- connection error      → log error; never re-raise (D-04, SPEC R5)

IMPORTANT: APScheduler 3.x jobs run in a thread-pool (no event loop).
Use httpx.Client (SYNC) — async HTTP client is forbidden here (RESEARCH Pitfall 1).
"""
import logging
import os
import time

import httpx
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from contracts import setup_logging

setup_logging("scheduler")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Adapter registry: name → (cron expression, internal Docker URL)
# Inter-container calls use service name + internal port 8000 (D-03).
# Host-side ports (22010–22014) are NOT used here.
# ---------------------------------------------------------------------------
ADAPTERS: dict[str, tuple[str, str]] = {
    "ingest-imap": (
        os.getenv("SCHEDULE_IMAP", "0 */2 * * *"),
        "http://ingest-imap:8000/run",
    ),
    "ingest-youtube": (
        os.getenv("SCHEDULE_YOUTUBE", "0 */4 * * *"),
        "http://ingest-youtube:8000/run",
    ),
    "ingest-gmail": (
        os.getenv("SCHEDULE_GMAIL", "0 */2 * * *"),
        "http://ingest-gmail:8000/run",
    ),
    "ingest-obsidian": (
        os.getenv("SCHEDULE_OBSIDIAN", "*/30 * * * *"),
        "http://ingest-obsidian:8000/run",
    ),
}


def fire_adapter(name: str, url: str) -> None:
    """Fire one adapter trigger and log the result.

    Uses a sync httpx.Client (APScheduler 3.x jobs are thread-pool, not async).
    Never raises — all exceptions are caught and logged.
    """
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.post(url)
        if r.status_code == 200:
            log.info("[%s] started (200)", name)
        elif r.status_code == 409:
            log.info("[%s] skipped — already running (409)", name)
        else:
            log.warning("[%s] unexpected status %d", name, r.status_code)
    except httpx.RequestError as exc:
        log.error("[%s] connection error: %s", name, exc)


def build_scheduler() -> BackgroundScheduler:
    """Build and return a configured BackgroundScheduler (not started yet)."""
    scheduler = BackgroundScheduler()
    for name, (cron, url) in ADAPTERS.items():
        scheduler.add_job(
            fire_adapter,
            CronTrigger.from_crontab(cron),
            args=[name, url],
            id=name,
        )
    return scheduler
