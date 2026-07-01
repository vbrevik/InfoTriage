#!/usr/bin/env python3
"""worker.py — InfoTriage triage worker (D-01 entry point).

Consumes item.ingested, dedups against mE5-large embeddings, scores non-duplicates
against ccir.md with the local LLM (qwen36/qwen80b, ADR-004), persists enrichment,
and publishes verdict.ready — alongside a stdlib /health server (D-04) so the
container's liveness check stays responsive even during a long (up to 120s) LLM call.

Usage:
    python3 worker.py        # runs the consumer + health server forever

Env: INFOTRIAGE_PG_DSN, INFOTRIAGE_BLOB_ROOT, INFOTRIAGE_AMQP_DSN,
     LLM_BASE_URL, LLM_API_KEY, LLM_MODEL (same vars as triage_score.llm()).
"""
import asyncio
import datetime
import json
import logging
import os
import urllib.request
from pathlib import Path

from contracts import RabbitMQBus, VerdictReady
from store import PostgresStore
from triage_score import score_item

log = logging.getLogger(__name__)

HEALTH_HOST = "0.0.0.0"
HEALTH_PORT = 22030


# ---------------------------------------------------------------------------
# Embedding call (mirrors triage_score.llm() exactly — same env vars, ADR-004)
# ---------------------------------------------------------------------------

def get_embedding(text: str) -> list[float]:
    """POST text to LLM_BASE_URL + '/embeddings' (local oMLX/Spark — no cloud host).

    Mirrors triage_score.llm()'s env var pattern and timeout. Returns the
    embedding vector for data[0] (D-06, mE5-large multilingual-e5-large).
    """
    base = os.environ.get("LLM_BASE_URL", "http://127.0.0.1:8000/v1")
    key = os.environ.get("LLM_API_KEY", "omlx")
    body = json.dumps({
        "model": "intfloat/multilingual-e5-large",
        "input": text,
    }).encode()
    req = urllib.request.Request(
        base.rstrip("/") + "/embeddings", data=body,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)["data"][0]["embedding"]


# ---------------------------------------------------------------------------
# Vocabulary mapping — raw score_item vocabulary -> VerdictReady vocabulary
# Enrichment rows store RAW vocabulary (cnr none|I|II, bucket read|maybe|skip);
# these mappers are applied ONLY when constructing the VerdictReady event.
# ---------------------------------------------------------------------------

def map_cnr(cnr: str) -> str:
    """Map raw score_item cnr ('none'|'I'|'II') to VerdictReady's Literal."""
    return "Routine" if cnr == "none" else cnr


def map_bucket(bucket: str) -> str:
    """Map raw score_item bucket ('read'|'maybe'|'skip') to VerdictReady's Literal."""
    return "keep" if bucket == "read" else bucket


def clamp_score(value) -> int:
    """Clamp value to the int range [0, 10] so the Postgres CHECK constraint never rejects it.

    Non-int/None values coerce safely to 0.
    """
    try:
        v = int(value)
    except (TypeError, ValueError):
        v = 0
    return max(0, min(10, v))


# ---------------------------------------------------------------------------
# process_item — the testable async core (R2, R3, R4, R5)
# ---------------------------------------------------------------------------

async def process_item(item_id, store, bus, *, embed=get_embedding, score=score_item) -> None:
    """Fetch, dedup, score, persist, and publish a single item.ingested item.

    Each blocking call (store I/O, embedding HTTP call, LLM HTTP call) runs via
    asyncio.to_thread so the stdlib health server's event loop is never starved
    during a long-running scoring call (R7). bus.publish() runs on the calling
    event loop directly (it is already async).

    A missing article (get_item returns None) logs a warning and returns
    normally — no exception, so the caller's message.process() acks (R2).
    If store.put_enrichment raises, the exception propagates so the caller's
    message.process() nacks — no verdict.ready is published (R2/R5 prohibition).
    """
    item = await asyncio.to_thread(store.get_item, item_id)
    if item is None:
        log.warning("item.ingested for unknown item_id=%s — acking, nothing to score", item_id)
        return

    text = item.title + " " + (item.summary or "")[:512]
    vec = await asyncio.to_thread(embed, text)
    dup = await asyncio.to_thread(store.find_near_duplicate, vec)

    if dup:
        fields = {
            "ccir": "none", "cnr": "none", "score": 0, "bucket": "skip",
            "why": f"duplicate of {dup}", "pmesii": "none", "tessoc": "none",
        }
    else:
        result = await asyncio.to_thread(
            score, {"title": item.title, "source": item.source, "summary": item.summary}
        )
        fields = {
            "ccir": result.get("ccir"),
            "cnr": result.get("cnr"),
            "score": clamp_score(result.get("score")),
            "bucket": result.get("bucket"),
            "why": result.get("why"),
            "pmesii": result.get("pmesii"),
            "tessoc": result.get("tessoc"),
        }

    # Enrichment write MUST commit before verdict.ready is published (R2/R5 prohibition):
    # a crash or exception here propagates without ever reaching bus.publish below.
    await asyncio.to_thread(store.put_enrichment, item_id, fields)
    await asyncio.to_thread(store.put_embedding, item_id, vec)

    payload = VerdictReady(
        event="verdict.ready",
        item_id=item_id,
        ccir=fields.get("ccir"),
        cnr=map_cnr(fields.get("cnr") or "none"),
        score=fields.get("score", 0),
        bucket=map_bucket(fields.get("bucket") or "skip"),
        why=fields.get("why") or "",
        ts=datetime.datetime.now(tz=datetime.timezone.utc),
    )
    await bus.publish("verdict.ready", item_id, payload.model_dump(mode="json"))


# ---------------------------------------------------------------------------
# on_message — RabbitMQ consumer callback (D-03)
# ---------------------------------------------------------------------------

async def on_message(message, store, bus) -> None:
    """Decode an item.ingested message and run process_item; ack only on clean exit.

    message.process() acks on clean return, and nacks (requeue=False -> DLQ) if
    process_item raises — e.g. on an enrichment-write failure (R2 prohibition).
    RabbitMQBus.publish() puts item_id in the AMQP message headers, not the JSON
    body (the body is only the {source, source_type, ts} payload) — read it from
    message.headers, not from the decoded body.
    Logs only item_id/event names — never the DSN (T-05-02).
    """
    async with message.process():
        item_id = message.headers["item_id"]
        log.info("item.ingested item_id=%s", item_id)
        await process_item(item_id, store, bus)


# ---------------------------------------------------------------------------
# run_consumer — wires on_message to the bus's persistent consumer (D-01, D-03)
# ---------------------------------------------------------------------------

async def run_consumer(bus, store) -> None:
    """Register the item.ingested consumer and run forever.

    prefetch_count=1 serializes message handling so the single store connection
    is never used concurrently (R2 concurrency edge / T-05-05).
    """
    await bus._ensure_connection()

    async def _handler(message) -> None:
        await on_message(message, store, bus)

    await bus.consume("item.ingested", _handler, prefetch_count=1)
    await asyncio.Future()  # run forever


# ---------------------------------------------------------------------------
# run_health_server — stdlib liveness-only /health (D-04, filled in Task 3)
# ---------------------------------------------------------------------------

async def _handle_health(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    """Connection handler for the liveness-only /health endpoint (D-04).

    Module-level (not nested) so tests can drive it directly via
    asyncio.start_server(_handle_health, ...) on an ephemeral port — see
    tests/test_triage_health.py. Does NOT touch the bus or DB: liveness only.
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
    """Serve a liveness-only GET /health -> 200 forever (D-04).

    Does NOT depend on bus or DB state — connect_robust handles AMQP reconnect
    on its own.
    """
    server = await asyncio.start_server(_handle_health, host, port)
    async with server:
        await server.serve_forever()


# ---------------------------------------------------------------------------
# main — D-03: asyncio.gather of consumer + health server under asyncio.run
# ---------------------------------------------------------------------------

async def main() -> None:
    pg_dsn = os.environ["INFOTRIAGE_PG_DSN"]
    blob_root = Path(os.environ.get("INFOTRIAGE_BLOB_ROOT", "/data/blobs"))
    amqp_dsn = os.environ.get(
        "INFOTRIAGE_AMQP_DSN", "amqp://infotriage:infotriage_rmq@127.0.0.1:22001"
    )
    bus = RabbitMQBus(amqp_url=amqp_dsn)
    with PostgresStore(dsn=pg_dsn, blob_root=blob_root) as store:
        await asyncio.gather(run_consumer(bus, store), run_health_server())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
