#!/usr/bin/env python3
"""main.py — Brief app FastAPI server (Phase 6, Wave 2).

Serves the SAB on 127.0.0.1:22040 (D-14):
  GET /health           — liveness probe, always 200 (no DB dependency)
  GET /sab              — SAB HTML; regenerates when cached sab.html is ≥24h old (D-01)
  GET /sab?window=24h   — ad-hoc window render, served without touching the cache (D-10)
  GET /sab?mode=list    — list markdown (score >= 8) for the window; no separate file (SPEC)

Runs the verdict.ready consumer as a background task — SPEC scopes one container
hosting consumer + renderer + HTTP server. If RabbitMQ is unreachable the consumer
task logs and dies; HTTP serving stays up.

Run: uvicorn apps.brief.main:app --host 0.0.0.0 --port 22040
(compose publishes 127.0.0.1:22040 only)
"""
import asyncio
import contextlib
import datetime
import logging
import os
import re
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse

from apps.brief.html_renderer import build_html
from apps.brief.renderer import render_list

# default_cutoff (yesterday 16:00 Oslo) — same first-render default as digest.py (D-09)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "triage"))
from digest import default_cutoff  # noqa: E402

log = logging.getLogger("brief.main")

DATA_DIR = Path(os.environ.get("INFOTRIAGE_DIGESTS_DIR", "data/digests"))
SAB_HTML = DATA_DIR / "sab.html"
STALE_AFTER_S = 24 * 3600  # D-01
WINDOW_RE = re.compile(r"^(\d{1,3})h$")

# Clustering threshold (0.0–1.0, default 0.75)
CLUSTER_THRESHOLD = float(os.getenv("CLUSTER_THRESHOLD", "0.75"))
if not (0.0 <= CLUSTER_THRESHOLD <= 1.0):
    raise ValueError(f"CLUSTER_THRESHOLD must be 0.0–1.0, got {CLUSTER_THRESHOLD}")

_ENRICHMENT_SQL = (
    "SELECT e.item_id, e.ccir, e.cnr, e.score, e.bucket, e.why, e.pmesii, e.tessoc, "
    "a.title, a.summary, a.source, a.url "
    "FROM infotriage.enrichment e "
    "JOIN infotriage.articles a ON a.id = e.item_id "
    "WHERE e.created_at >= %s ORDER BY e.score DESC"
)

_state: dict = {"store": None, "consumer_task": None}


def _fetch_rows(since: datetime.datetime) -> list[dict]:
    """Fetch enrichment rows created since `since` (blocking — call via to_thread)."""
    from psycopg.rows import dict_row

    store = _state["store"]
    if store is None:
        raise RuntimeError("PostgresStore not initialised")
    with store.cursor(row_factory=dict_row) as cur:
        try:
            cur.execute(_ENRICHMENT_SQL, (since,))
            rows = cur.fetchall()
            cur.connection.commit()  # end read txn — avoid idle-in-transaction
            return rows
        except Exception:
            cur.connection.rollback()  # un-poison the shared connection
            raise


def _period_label(since: datetime.datetime) -> str:
    return f"siden {since.strftime('%Y-%m-%d %H:%M')}"


def _write_atomic(path: Path, content: str) -> None:
    """Atomic write: .tmp + os.replace — no partial reads on concurrent GETs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


def _parse_window(window: str) -> datetime.datetime:
    m = WINDOW_RE.match(window.strip())
    if not m:
        raise HTTPException(status_code=422, detail="window must look like '24h' (1-999 hours)")
    hours = int(m.group(1))
    return datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)


async def _render_sab(since: datetime.datetime, with_bluf: bool) -> str:
    rows = await asyncio.to_thread(_fetch_rows, since)
    return await asyncio.to_thread(
        build_html, rows, _period_label(since), with_bluf
    )


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    from pathlib import Path as _P

    from store import PostgresStore

    pg_dsn = os.environ["INFOTRIAGE_PG_DSN"]
    blob_root = _P(os.environ.get("INFOTRIAGE_BLOB_ROOT", "data/blobs"))
    with PostgresStore(dsn=pg_dsn, blob_root=blob_root) as store:
        _state["store"] = store
        if os.environ.get("BRIEF_CONSUME", "1") == "1":
            try:
                from contracts import RabbitMQBus

                from apps.brief.consumer import run_consumer

                amqp_dsn = os.environ.get(
                    "INFOTRIAGE_AMQP_DSN",
                    "amqp://infotriage:infotriage_rmq@127.0.0.1:22001",
                )
                bus = RabbitMQBus(amqp_url=amqp_dsn)
                _state["consumer_task"] = asyncio.create_task(run_consumer(bus, store))
                log.info("verdict.ready consumer started")
            except Exception as e:  # HTTP serving survives a dead consumer
                log.error("consumer failed to start: %s", e, exc_info=True)
        yield
        task = _state.get("consumer_task")
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        _state["store"] = None


app = FastAPI(title="InfoTriage Brief", lifespan=lifespan)


@app.get("/health")
async def health():
    """Liveness only — no DB/bus dependency (worker.py pattern)."""
    return {"status": "ok", "service": "brief"}


@app.get("/sab")
async def sab(window: str | None = None, mode: str | None = None):
    with_bluf = os.environ.get("BRIEF_WITH_BLUF", "1") == "1"

    # ?mode=list — list markdown for the window, never written to disk (SPEC)
    if mode == "list":
        since = _parse_window(window) if window else default_cutoff()
        rows = await asyncio.to_thread(_fetch_rows, since)
        return PlainTextResponse(render_list(rows), media_type="text/markdown")
    if mode is not None:
        raise HTTPException(status_code=422, detail="mode must be 'list'")

    # ?window=24h — ad-hoc render, serve without updating the cache (D-10)
    if window is not None:
        html = await _render_sab(_parse_window(window), with_bluf)
        return HTMLResponse(html)

    # Default path — staleness gate on file mtime (D-01)
    try:
        age = datetime.datetime.now().timestamp() - SAB_HTML.stat().st_mtime
        fresh = age < STALE_AFTER_S
    except FileNotFoundError:
        fresh = False
    if not fresh:
        html = await _render_sab(default_cutoff(), with_bluf)
        await asyncio.to_thread(_write_atomic, SAB_HTML, html)
    return FileResponse(SAB_HTML, media_type="text/html",
                        headers={"Cache-Control": "max-age=86400"})


if __name__ == "__main__":
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    uvicorn.run(app, host="127.0.0.1", port=22040)
