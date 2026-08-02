#!/usr/bin/env python3
"""poller.py — InfoTriage MVP: one synchronous loop instead of the event bus.

Replaces the entire event-driven middle (6 ingest adapters + scheduler +
RabbitMQ + triage worker + alerting consumer + DLQ consumer) with a single
asyncio loop that runs the full value chain synchronously:

    FreshRSS (Fever API) -> score (local LLM, ccir.md) -> Postgres
        -> CAT I push (ntfy, shipped alerting lane, bus=None)
        -> Obsidian item notes + SAB

Everything here is a WIRING JOB over existing, tested modules — nothing is
reimplemented. `triage_score.score_item` is the exact scorer the triage
worker used; `emitter.handle_verdict_ready` is the exact CAT I emit path
(claim -> throttle -> retry -> dead-letter) that Phase 12 shipped — it runs
fine with `bus=None` because the poller's synchronous loop needs no broker
(verified: the only bus use is the DLX publish on delivery exhaustion, which
a solo MVP accepts as a logged terminal failure rather than a queue).

Usage:
    python3 poller.py           # poll forever (MVP_POLL_INTERVAL, default 300s)

Env: INFOTRIAGE_PG_DSN, INFOTRIAGE_BLOB_ROOT (store); FRESHRSS_URL,
     FRESHRSS_FEVER_USER, FRESHRSS_FEVER_API_PASSWORD (Fever poll);
     NTFY_URL, NTFY_TOKEN, NTFY_TOPIC_PREFIX (push, same vars as alerting);
     INFOTRIAGE_VAULT_PATH, INFOTRIAGE_ALERT_NOTE_SUBDIR (notes);
     LLM_BASE_URL, LLM_API_KEY, LLM_MODEL (scorer, same vars as triage).
"""
from __future__ import annotations

import asyncio
import datetime
import hashlib
import json
import logging
import os
import urllib.request
import urllib.parse
from pathlib import Path

from contracts import Item, setup_logging
from store import PostgresStore

from triage_score import score_item
from emitter import handle_verdict_ready
from outbox import NtfyClient

setup_logging("mvp")
log = logging.getLogger(__name__)

HEALTH_HOST = "0.0.0.0"
HEALTH_PORT = 22017
DEFAULT_POLL_INTERVAL = 300
FEVER_ENDPOINT = "/api/fever.php"


def _fever_url(base_url: str) -> str:
    return base_url.rstrip("/") + FEVER_ENDPOINT


def _fever_api_key(user: str, password: str) -> str:
    """Fever protocol auth: md5("<user>:<api-password>")."""
    return hashlib.md5(f"{user}:{password}".encode()).hexdigest()


def fetch_new_items(
    base_url: str, user: str, password: str, since_id: int
) -> list[dict]:
    """GET the Fever API for items newer than `since_id`.

    Returns the parsed `items` array (empty on any HTTP/parse error — a
    transient FreshRSS hiccup must not kill the poll loop). Non-2xx raises,
    mirroring triage_score.llm's fail-fast style; callers treat that as a
    skip-this-cycle signal.
    """
    params = {
        "api": "",
        "items": "",
        "since_id": str(since_id),
        "api_key": _fever_api_key(user, password),
    }
    url = _fever_url(base_url) + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.load(resp)
    return payload.get("items") or []


def _summary_from_html(html: str, limit: int = 500) -> str:
    """Crude HTML-to-text for the scorer input (title + summary contract)."""
    import re

    text = re.sub(r"<[^>]+>", " ", html or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _build_item(raw: dict) -> Item:
    """Map one Fever item dict onto the canonical Item contract.

    Fever's `html` field holds the article content (RSS feed content or a
    link-preview snippet); `author` is the per-item byline when present.
    Item.id is derived from source+url by the contract, so re-polling the
    same item yields the same id — that is the dedupe key.
    """
    title = (raw.get("title") or "").strip() or "(untitled)"
    url = (raw.get("url") or "").strip()
    summary = _summary_from_html(raw.get("html") or "")
    ts_epoch = raw.get("created_on_time") or 0
    ts = datetime.datetime.fromtimestamp(float(ts_epoch), tz=datetime.timezone.utc)
    return Item(
        source=(raw.get("author") or "freshrss").strip() or "freshrss",
        source_type="rss",
        url=url or f"fever://item/{raw.get('id', 'unknown')}",
        title=title,
        ts=ts,
        lang="en",  # Fever API does not carry language; scorer is multilingual
        summary=summary,
    )


def _kept(item_id: str, store) -> bool:
    """True if this item id is already known to the store (dedupe)."""
    return store.get_item(item_id) is not None


class _PollState:
    """Persist the highest-seen Fever item id so restarts don't refetch."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._since_id = 0
        if path.exists():
            try:
                self._since_id = int(json.loads(path.read_text()).get("since_id", 0))
            except Exception:
                self._since_id = 0

    @property
    def since_id(self) -> int:
        return self._since_id

    def advance(self, item_id: int) -> None:
        self._since_id = max(self._since_id, item_id)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"since_id": self._since_id}))
        tmp.replace(self.path)


async def poll_once(
    store,
    client,
    *,
    base_url: str,
    user: str,
    password: str,
    vault_path: Path,
    state: _PollState,
) -> dict:
    """One full poll cycle; returns a summary dict for tests/logging.

    Each blocking call (Fever HTTP, LLM scoring, store I/O, vault writes)
    runs via asyncio.to_thread so the health server's event loop is never
    starved — mirroring apps/triage/worker.py's pattern.
    """
    fetched = await asyncio.to_thread(
        fetch_new_items, base_url, user, password, state.since_id
    )
    log.info("mvp: fetched %d new item(s) since_id=%s", len(fetched), state.since_id)

    pushed = skipped = scored = 0
    new_items: list[Item] = []
    for raw in sorted(fetched, key=lambda r: int(r.get("id") or 0)):
        fever_id = int(raw.get("id") or 0)
        try:
            item = _build_item(raw)
            if _kept(item.id, store):
                skipped += 1
                state.advance(fever_id)
                continue

            # Score (local LLM via the exact triage scorer).
            result = await asyncio.to_thread(
                score_item,
                {"title": item.title, "source": item.source, "summary": item.summary},
            )
            fields = {
                "ccir": result.get("ccir"),
                "cnr": result.get("cnr"),
                "score": result.get("score"),
                "bucket": result.get("bucket"),
                "why": result.get("why"),
                "pmesii": result.get("pmesii"),
                "tessoc": result.get("tessoc"),
            }

            # Persist BEFORE alerting (same ordering guarantee as the old lane).
            await asyncio.to_thread(store.put_item, item)
            await asyncio.to_thread(store.put_enrichment, item.id, fields)
            scored += 1
            new_items.append(item)

            # CAT I -> the shipped alerting emit path, synchronously, bus=None.
            if fields.get("cnr") == "I":
                await handle_verdict_ready(
                    {"event": "verdict.ready", "item_id": item.id, "cnr": "I"},
                    store,
                    client,
                    bus=None,
                )
                pushed += 1

            state.advance(fever_id)
        except Exception as exc:
            # One bad item must not kill the cycle — log and retry next poll.
            # since_id is NOT advanced on failure, so the item re-fetches.
            log.error(
                "mvp: item %s failed, will retry next cycle: %s",
                fever_id,
                exc,
                exc_info=True,
            )

    # Obsidian notes + SAB for kept items (same filter brief used). A vault
    # write error must not take the whole cycle down; notes are best-effort.
    if new_items:
        try:
            await asyncio.to_thread(_write_notes, store, new_items, vault_path)
        except Exception as exc:
            log.error("mvp: vault note write failed: %s", exc, exc_info=True)

    log.info(
        "mvp: cycle done — scored=%d pushed=%d skipped=%d",
        scored,
        pushed,
        skipped,
    )
    return {
        "scored": scored,
        "pushed": pushed,
        "skipped": skipped,
        "fetched": len(fetched),
    }


def _write_notes(store, items: list[Item], vault_path: Path) -> None:
    """Write Obsidian item notes + refresh the SAB for the cycle's new items.

    Reuses apps/brief/vault_writer's filters (score >= 8 or ccir != none).
    """
    from apps.brief.vault_writer import write_sab_obsidian, write_item_obsidian

    rows: list[dict] = []
    for item in items:
        enr = store.get_enrichment(item.id) or {}
        score = enr.get("score") or 0
        ccir = (enr.get("ccir") or "none").lower()
        if score >= 8 or ccir != "none":
            rows.append(
                {
                    "item_id": item.id,
                    "title": item.title,
                    "summary": item.summary,
                    "source": item.source,
                    "url": getattr(item, "url", ""),
                    "ts": item.ts.isoformat(),
                    "ccir": enr.get("ccir"),
                    "cnr": enr.get("cnr"),
                    "score": score,
                    "bucket": enr.get("bucket"),
                    "why": enr.get("why"),
                    "pmesii": enr.get("pmesii"),
                    "tessoc": enr.get("tessoc"),
                    "lang": getattr(item, "lang", "en"),
                }
            )
            write_item_obsidian(rows[-1], vault_path)
    if rows:
        write_sab_obsidian(rows, vault_path)


async def _handle_health(
    reader: asyncio.StreamReader, writer: asyncio.StreamWriter
) -> None:
    """Connection handler for the liveness-only /health endpoint.

    Module-level (not nested) so tests can drive it directly via
    asyncio.start_server(_handle_health, ...) on an ephemeral port — mirroring
    apps/triage/worker.py's proven pattern. Does NOT touch the bus or DB.
    """
    await reader.read(1024)
    body = b"OK"
    response = (
        b"HTTP/1.1 200 OK\r\n"
        b"Content-Length: " + str(len(body)).encode() + b"\r\n"
        b"Connection: close\r\n\r\n" + body
    )
    writer.write(response)
    await writer.drain()
    writer.close()


async def run_health_server(host: str = HEALTH_HOST, port: int = HEALTH_PORT) -> None:
    """Serve a liveness-only GET /health -> 200 forever."""
    server = await asyncio.start_server(_handle_health, host, port)
    async with server:
        await server.serve_forever()


async def main() -> None:
    pg_dsn = os.environ["INFOTRIAGE_PG_DSN"]
    blob_root = Path(os.environ.get("INFOTRIAGE_BLOB_ROOT", "/data/blobs"))
    interval = float(os.environ.get("MVP_POLL_INTERVAL", DEFAULT_POLL_INTERVAL))

    fr_url = os.environ.get("FRESHRSS_URL", "http://freshrss:80")
    fr_user = os.environ.get("FRESHRSS_FEVER_USER", "admin")
    fr_password = os.environ["FRESHRSS_FEVER_API_PASSWORD"]

    ntfy_url = os.environ.get("NTFY_URL", "http://ntfy:80")
    ntfy_token = os.environ["NTFY_TOKEN"]  # fail-closed, same as alerting
    ntfy_topic = os.environ.get("NTFY_TOPIC_PREFIX", "cnr-cat-i")

    vault_path = Path(os.environ.get("INFOTRIAGE_VAULT_PATH", "/vault/brief-outbox"))
    state = _PollState(Path(os.environ.get("MVP_STATE_PATH", "/data/mvp/state.json")))

    # Liveness endpoint for the compose healthcheck — runs alongside the loop.
    health_task = asyncio.create_task(run_health_server())

    with PostgresStore(dsn=pg_dsn, blob_root=blob_root) as store:
        client = NtfyClient(ntfy_url, ntfy_token, ntfy_topic)
        while True:
            try:
                await poll_once(
                    store,
                    client,
                    base_url=fr_url,
                    user=fr_user,
                    password=fr_password,
                    vault_path=vault_path,
                    state=state,
                )
            except Exception as exc:
                log.error("mvp: poll cycle failed: %s", exc, exc_info=True)
            await asyncio.sleep(interval)


if __name__ == "__main__":
    asyncio.run(main())
