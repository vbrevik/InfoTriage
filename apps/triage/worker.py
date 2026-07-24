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
import re
import urllib.request
from pathlib import Path

from typing import Literal, cast

from contracts import RabbitMQBus, VerdictReady, setup_logging
from store import PostgresStore
from triage_score import llm, score_item
from entities import resolve_entities_async

setup_logging("triage")
log = logging.getLogger(__name__)

HEALTH_HOST = "0.0.0.0"
HEALTH_PORT = 22030


# ---------------------------------------------------------------------------
# Embedding call (mirrors triage_score.llm() exactly — same env vars, ADR-004)
# ---------------------------------------------------------------------------

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_URL_RE = re.compile(r"https?://\S+")
_WS_RE = re.compile(r"\s+")

# Known per-platform email-template phrases (beehiiv, Medium digests, generic
# transactional-email footers). These are static label/nav text emitted
# verbatim in EVERY newsletter from the platform — stripping the URL alone
# (above) leaves them behind, and at a 512-char budget they still dominate
# short article titles, collapsing topically-unrelated newsletters into false
# near-duplicates purely on shared chrome (2026-07-24: three separate Kimi K3
# articles still collided post-URL-strip on "View image: ... Follow image
# link: ..." / "Stories for Vidar Brevik @vbrevik ... ·Member ..."). Brittle
# by nature (new platforms need new phrases); revisit if false-dedup returns.
_BOILERPLATE_PHRASES = (
    "View image:",
    "Follow image link:",
    "View in browser",
    "Stories for Vidar Brevik @vbrevik",
    "·Member",
    "Today's highlights",
    "Please use an email client supporting HTML email",
)
_BOILERPLATE_RE = re.compile(
    "|".join(re.escape(p) for p in _BOILERPLATE_PHRASES), re.IGNORECASE
)


def _clean_for_embedding(text: str) -> str:
    """Strip HTML tags, URLs, and known newsletter-template chrome before embedding.

    Newsletter/tracking chrome (beehiiv image URLs, Medium digest nav links,
    raw undecoded HTML email bodies, per-platform template label text)
    otherwise dominates the first 512 chars of many email-sourced summaries.
    Since that chrome is near-identical across unrelated emails from the same
    platform, embedding it collapses topically-distinct articles into false
    near-duplicates (cosine similarity > the 0.84 dedup threshold) before the
    LLM scorer ever sees them — e.g. three separate Kimi K3 articles chained
    as "duplicates" of an unrelated "Claude Code Skills" article, purely on
    shared Medium/beehiiv boilerplate. Stripping tags/URLs/known chrome
    phrases before truncation keeps the 512-char budget on actual content.
    """
    text = _HTML_TAG_RE.sub(" ", text)
    text = _URL_RE.sub(" ", text)
    text = _BOILERPLATE_RE.sub(" ", text)
    return _WS_RE.sub(" ", text).strip()


def get_embedding(text: str) -> list[float]:
    """POST text to LLM_BASE_URL + '/embeddings' (local oMLX/Spark — no cloud host).

    Mirrors triage_score.llm()'s env var pattern and timeout. Returns the
    embedding vector for data[0] (D-06, mE5-large multilingual-e5-large).
    """
    base = os.environ.get("LLM_BASE_URL", "http://127.0.0.1:8000/v1")
    key = os.environ.get("LLM_API_KEY", "omlx")
    body = json.dumps(
        {
            "model": "intfloat/multilingual-e5-large",
            "input": text,
        }
    ).encode()
    req = urllib.request.Request(
        base.rstrip("/") + "/embeddings",
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return cast(list[float], json.load(r)["data"][0]["embedding"])


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


async def process_item(
    item_id, store, bus, *, embed=get_embedding, score=score_item, ner_chat=llm
) -> None:
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
        log.warning(
            "item.ingested for unknown item_id=%s — acking, nothing to score", item_id
        )
        return

    text = item.title + " " + _clean_for_embedding(item.summary or "")[:512]
    vec = cast(list[float], await asyncio.to_thread(embed, text))

    # Phase 9: CCIR pre-filter — skip clearly off-topic items before dedup/score.
    _prefilter_threshold = float(
        os.environ.get("INFOTRIAGE_PREFILTER_THRESHOLD", "0.50")
    )
    ccir_lookup_failed = False
    best_ccir: dict | None = None
    try:
        best_ccir = await asyncio.to_thread(store.find_similar_ccir, vec)
    except Exception as exc:
        log.warning("pre-filter CCIR search failed for item_id=%s: %s", item_id, exc)
        ccir_lookup_failed = True

    _prefilter_sim = best_ccir["similarity"] if best_ccir is not None else 0.0
    _prefilter_ccir_id = best_ccir["ccir_id"] if best_ccir is not None else "none"
    # If CCIR lookup fails or there are no CCIR vectors, fall through to the
    # LLM scorer rather than silently dropping the item (D-07).
    pre_filter_passes = (
        ccir_lookup_failed
        or best_ccir is None
        or _prefilter_sim >= _prefilter_threshold
    )
    if pre_filter_passes:
        log.info(
            "pre-filter PASS item_id=%s best_ccir=%s similarity=%.3f",
            item_id,
            _prefilter_ccir_id,
            _prefilter_sim,
        )
    else:
        log.info(
            "pre-filter SKIP item_id=%s best_ccir=%s similarity=%.3f",
            item_id,
            _prefilter_ccir_id,
            _prefilter_sim,
        )

    # Dedup + score only for items that pass the pre-filter.
    if pre_filter_passes:
        # Bumped 0.84 -> 0.90 (2026-07-24, interim): even after
        # _clean_for_embedding, short structurally-similar tech-newsletter
        # headlines (e.g. distinct Kimi K3 articles vs an unrelated AI
        # article) measured 0.8447 cosine similarity — just above the old
        # 0.84 threshold, so still false-dedup'd pre-LLM. 0.84 is the
        # spike-validated (Phase 00 R2) value; this raise trades some
        # missed real near-duplicates for fewer false collapses until the
        # full backlog Phase 999.2 recalibration (larger corpus, genuinely
        # off-topic controls) revisits it properly.
        _dedup_threshold = float(os.environ.get("INFOTRIAGE_DEDUP_THRESHOLD", "0.90"))
        dup = await asyncio.to_thread(
            store.find_near_duplicate, vec, threshold=_dedup_threshold
        )
        if dup:
            fields = {
                "ccir": "none",
                "cnr": "none",
                "score": 0,
                "bucket": "skip",
                "why": f"duplicate of {dup}",
                "pmesii": "none",
                "tessoc": "none",
            }
        else:
            result = await asyncio.to_thread(
                score,
                {"title": item.title, "source": item.source, "summary": item.summary},
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
    else:
        fields = {
            "ccir": "none",
            "cnr": "none",
            "score": 0,
            "bucket": "skip",
            "why": f"pre-filter: max_cosine={_prefilter_sim:.3f} < threshold",
            "pmesii": "none",
            "tessoc": "none",
        }

    # Persist enrichment and embedding before publishing verdict (R2/R5 prohibition).
    await asyncio.to_thread(store.put_enrichment, item_id, fields)
    await asyncio.to_thread(store.put_embedding, item_id, vec)

    # Audit pre-filter skips for later analysis / threshold tuning.
    if not pre_filter_passes:
        try:
            await asyncio.to_thread(
                store.audit_write,
                op="pre_filter_skip",
                table_name="enrichment",
                item_id=item_id,
                details={
                    "max_similarity": _prefilter_sim,
                    "threshold": _prefilter_threshold,
                    "best_ccir": _prefilter_ccir_id,
                },
            )
        except Exception as exc:
            log.warning(
                "pre-filter audit write failed for item_id=%s: %s", item_id, exc
            )

    # Phase 8: extract, embed, and link entities to this item.
    # This is best-effort: entity-linking failures (including timeouts) are
    # logged but must not prevent the verdict.ready event from being published.
    # A timeout guard ensures a hung LLM NER call cannot block the scoring
    # pipeline indefinitely (ADR-004, R5 prohibition).
    _ENTITY_NER_TIMEOUT = float(os.environ.get("INFOTRIAGE_ENTITY_NER_TIMEOUT", "15"))
    try:
        entity_text = item.title + " " + (item.summary or "")
        await asyncio.wait_for(
            resolve_entities_async(
                item_id, entity_text, item.lang or "en", store, embed, ner_chat
            ),
            timeout=_ENTITY_NER_TIMEOUT,
        )
    except asyncio.TimeoutError:
        log.warning(
            "entity resolution timed out after %.0fs for item_id=%s — verdict not blocked",
            _ENTITY_NER_TIMEOUT,
            item_id,
        )
    except Exception as exc:
        log.warning("entity resolution failed for item_id=%s: %s", item_id, exc)

    payload = VerdictReady(
        event="verdict.ready",
        item_id=item_id,
        ccir=cast("str | None", fields.get("ccir")),
        cnr=cast(
            Literal["I", "II", "Routine"],
            map_cnr(cast(str, fields.get("cnr") or "none")),
        ),
        score=cast(int, fields.get("score", 0)),
        bucket=cast(
            Literal["keep", "maybe", "skip"],
            map_bucket(cast(str, fields.get("bucket") or "skip")),
        ),
        why=cast(str, fields.get("why") or ""),
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


async def _handle_health(
    reader: asyncio.StreamReader, writer: asyncio.StreamWriter
) -> None:
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
    asyncio.run(main())
