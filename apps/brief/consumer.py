#!/usr/bin/env python3
"""consumer.py — RabbitMQ consumer for verdict.ready events (Phase 6).

Consumes verdict.ready from RabbitMQ, enriches items from Postgres, renders
the SAB, and publishes SabPublished.

Env: INFOTRIAGE_PG_DSN, INFOTRIAGE_AMQP_DSN (same as worker.py)
"""
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

from contracts import RabbitMQBus, SabPublished

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from store import PostgresStore  # noqa: E402
from apps.brief.renderer import (  # noqa: E402
    render_brief,
    render_list,
    render_bluf,
    render_cluster,
)

log = logging.getLogger(__name__)

OUT_ROOT = Path(os.environ.get("INFOTRIAGE_BLOB_ROOT", "/data/blobs"))
DATA_DIR = OUT_ROOT / "digests"


# ---------------------------------------------------------------------------
# process_verdict — core async handler (R1-R5)
# ---------------------------------------------------------------------------


async def process_verdict(
    item_id: str,
    store: PostgresStore,
    bus: RabbitMQBus,
    *,
    snap_day: str,
) -> SabPublished | None:
    """Process a verdict.ready for item_id: fetch enrichment, render SAB, publish event.
    
    Returns the SabPublished event on success, None if item not found.
    
    R1: Consumes verdict.ready from q.brief
    R2: Renders brief.md, cluster.md, list.md, bluf.md from Postgres enrichment rows
    R5: Publishes SabPublished with topic BLUFs and item refs
    """
    # Fetch enrichment row from Postgres
    async def _fetch():
        with store.cursor() as cur:
            cur.execute(
                "SELECT item_id, ccir, cnr, score, bucket, why, pmesii, tessoc, "
                "title, summary, source FROM infotriage.enrichment WHERE item_id = %s",
                (item_id,),
            )
            return cur.fetchone()

    row = await asyncio.to_thread(_fetch)
    if row is None:
        log.warning("verdict.ready for unknown item_id=%s — nothing to render", item_id)
        return None

    # Map row to enrichment dict
    from psycopg.rows import dict_row  # noqa: E402
    
    def _fetch_all():
        with store.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT item_id, ccir, cnr, score, bucket, why, pmesii, tessoc, "
                "title, summary, source FROM infotriage.enrichment ORDER BY score DESC"
            )
            return cur.fetchall()

    enrichment_rows = await asyncio.to_thread(_fetch_all)

    # Render all four outputs
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    brief_md, cluster_md, list_md, bluf_md = await asyncio.gather(
        asyncio.to_thread(render_brief, enrichment_rows),
        asyncio.to_thread(render_cluster, enrichment_rows),
        asyncio.to_thread(render_list, enrichment_rows),
        asyncio.to_thread(_render_bluf_all_sections, enrichment_rows),
    )

    # Write atomically (BACKSTOP: concurrent SAB writes via .tmp + os.replace)
    files = {
        "brief.md": brief_md,
        "cluster.md": cluster_md,
        "list.md": list_md,
        "bluf.md": bluf_md,
    }

    for name, content in files.items():
        fpath = DATA_DIR / name
        tmp = fpath.with_suffix(".tmp")
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, fpath)
        log.info("wrote %s", fpath)

    # Publish SabPublished event
    ccir_topics = sorted({
        (r.get("ccir") or "none").upper()
        for r in enrichment_rows
        if (r.get("ccir") or "none").lower() != "none"
    })

    # Count bluf topics (topics that got a BLUF)
    bluf_by_topic: dict[str, str] = {}
    for r in enrichment_rows:
        ccir = (r.get("ccir") or "none").upper()
        if ccir in ccir_topics and r.get("score", 0) >= 8:
            if ccir not in bluf_by_topic:
                bluf_by_topic[ccir] = "_(awaiting LLM synthesis)_"
    
    item_refs = [
        {
            "item_id": r["item_id"],
            "ccir": (r.get("ccir") or "none").upper(),
            "cnr": r.get("cnr", "none"),
            "n": r.get("score", 0),
            "title": r.get("title", ""),
            "source": r.get("source", ""),
            "url": "",
            "ts": "",
        }
        for r in enrichment_rows[:50]  # top 50 refs
    ]

    event = SabPublished(
        event="sab.published",
        pub_ts=__import__("datetime").datetime.now(tz=__import__("datetime").timezone.utc),
        snapshot_day=snap_day,
        ccir_topics=ccir_topics,
        bluf_by_topic=bluf_by_topic,
        item_refs=item_refs,
        total_keep=sum(1 for r in enrichment_rows if r.get("score", 0) >= 8),
    )

    await bus.publish(
        "sab.published",
        item_id,
        event.model_dump(mode="json"),
    )
    log.info("published SabPublished for day=%s, %d items", snap_day, len(enrichment_rows))
    return event


async def _render_bluf_all_sections(enrichment_rows: list[dict]) -> str:
    """Render BLUF for all CCIR sections with items score >= 8."""
    from apps.brief.renderer import CCIR_ORDER, render_bluf  # noqa: E402
    
    lines = ["# InfoTriage · BLUF", ""]
    by_ccir: dict[str, list[dict]] = {}
    for r in enrichment_rows:
        ccir = (r.get("ccir") or "none").upper()
        if ccir in dict(CCIR_ORDER) and r.get("score", 0) >= 8:
            by_ccir.setdefault(ccir, []).append(r)
    
    for ccir, title in CCIR_ORDER:
        items = by_ccir.get(ccir, [])
        if not items:
            lines.append(f"## {ccir} · {title}")
            lines.append("_(ingen saker i vinduet)_\n")
            continue
        bluf = render_bluf(items, ccir_title=title, ccir_id=ccir, top_n=5)
        lines.append(f"## {ccir} · {title}")
        lines.append(bluf)
        lines.append("")
    
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# on_verdict_message — RabbitMQ consumer callback
# ---------------------------------------------------------------------------


async def on_verdict_message(message, store, bus) -> None:
    """Decode a verdict.ready message and run process_verdict.
    
    message.process() acks on clean return, nacks (requeue=False -> DLQ) on error.
    """
    async with message.process():
        item_id = message.headers["item_id"]
        log.info("verdict.ready item_id=%s", item_id)
        
        snap_day = __import__("datetime").date.today().isoformat()
        try:
            await process_verdict(item_id, store, bus, snap_day=snap_day)
        except Exception as e:
            log.error("process_verdict failed for item_id=%s: %s", item_id, e, exc_info=True)
            raise  # re-raise so message.process() nacks


# ---------------------------------------------------------------------------
# run_consumer — wires on_verdict_message to the bus's persistent consumer
# ---------------------------------------------------------------------------


async def run_consumer(bus, store) -> None:
    """Register the verdict.ready consumer and run forever."""
    await bus._ensure_connection()

    async def _handler(message) -> None:
        await on_verdict_message(message, store, bus)

    await bus.consume("verdict.ready", _handler, prefetch_count=1)
    await asyncio.Future()  # run forever


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


async def main() -> None:
    pg_dsn = os.environ["INFOTRIAGE_PG_DSN"]
    blob_root = Path(os.environ.get("INFOTRIAGE_BLOB_ROOT", "/data/blobs"))
    amqp_dsn = os.environ.get(
        "INFOTRIAGE_AMQP_DSN", "amqp://infotriage:infotriage_rmq@127.0.0.1:22001"
    )
    bus = RabbitMQBus(amqp_url=amqp_dsn)
    with PostgresStore(dsn=pg_dsn, blob_root=blob_root) as store:
        await run_consumer(bus, store)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
