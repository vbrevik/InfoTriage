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
from functools import partial
from pathlib import Path

from contracts import RabbitMQBus, SabPublished

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from store import PostgresStore, PostgresTranslationCache  # noqa: E402
from apps.brief.renderer import (  # noqa: E402
    render_brief,
    render_list,
    render_bluf,
    render_cluster,
)
from apps.brief.vault_writer import write_vault_digest  # noqa: E402
from apps.brief.views import filter_rows  # noqa: E402

log = logging.getLogger(__name__)

# Same env + default as main.py — consumer writes where the HTTP server serves (D-03)
DATA_DIR = Path(os.environ.get("INFOTRIAGE_DIGESTS_DIR", "data/digests"))

# Module-level SQL constant (mirrors main.py::_ENRICHMENT_SQL). Hoisting from
# inside process_verdict enables static SQL-grammar regression tests and
# avoids re-building the constant string per verdict.ready message.
_SELECT = "SELECT e.item_id, e.ccir, e.cnr, e.score, e.bucket, e.why, e.pmesii, e.tessoc, a.title, a.summary, a.body, a.source, a.url, a.ts, emb.embedding FROM infotriage.enrichment e JOIN infotriage.articles a ON a.id = e.item_id LEFT JOIN infotriage.embeddings emb ON emb.item_id = e.item_id "


# ---------------------------------------------------------------------------
# process_verdict — core async handler (R1-R5)
# ---------------------------------------------------------------------------


async def process_verdict(
    item_id: str,
    store: PostgresStore,
    bus: RabbitMQBus,
    *,
    snap_day: str,
    cluster_threshold: float = 0.75,
) -> SabPublished | None:
    """Process a verdict.ready for item_id: fetch enrichment, render SAB, publish event.

    Returns the SabPublished event on success, None if item not found.

    R1: Consumes verdict.ready from q.brief
    R2: Renders brief.md, cluster.md, list.md, bluf.md from Postgres enrichment rows
    R5: Publishes SabPublished with topic BLUFs and item refs
    """
    # Fetch enrichment row from Postgres.

    def _fetch():  # plain def — runs inside asyncio.to_thread
        with store.cursor() as cur:
            try:
                cur.execute(_SELECT + "WHERE e.item_id = %s", (item_id,))
                row = cur.fetchone()
                cur.connection.commit()  # end read txn
                return row
            except Exception:
                cur.connection.rollback()  # un-poison shared connection for next message
                raise

    row = await asyncio.to_thread(_fetch)
    if row is None:
        log.warning("verdict.ready for unknown item_id=%s — nothing to render", item_id)
        return None

    # Map row to enrichment dict
    from psycopg.rows import dict_row  # noqa: E402

    def _fetch_all():
        with store.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute(_SELECT + "ORDER BY e.score DESC")
                rows = cur.fetchall()
                cur.connection.commit()  # end read txn
                return rows
            except Exception:
                cur.connection.rollback()
                raise

    enrichment_rows = await asyncio.to_thread(_fetch_all)

    # Phase 8: project entity graph links into each enrichment row for the vault.
    def _attach_entities(rows: list[dict]) -> list[dict]:
        for row in rows:
            item_id = row["item_id"]
            row["entities"] = store.get_entity_links(item_id)
        return rows

    enrichment_rows = await asyncio.to_thread(_attach_entities, enrichment_rows)

    # Compute view-filtered row sets (ADR-012)
    cop_rows = filter_rows(enrichment_rows, "cop")
    cip_rows = filter_rows(enrichment_rows, "cip")

    # Persistent translation cache backed by Postgres (Phase 11 Wave 4)
    cache = PostgresTranslationCache(store)

    # Render all four outputs for default, COP, and CIP views
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    async def _render_view(rows: list[dict], suffix: str) -> dict[str, str]:
        """Render the four digest files for a given row set."""
        brief_md, cluster_md, list_md, bluf_md = await asyncio.gather(
            asyncio.to_thread(
                partial(
                    render_brief,
                    rows,
                    cluster_threshold=cluster_threshold,
                    cache=cache,
                )
            ),
            asyncio.to_thread(
                partial(
                    render_cluster,
                    rows,
                    cluster_threshold=cluster_threshold,
                    cache=cache,
                )
            ),
            asyncio.to_thread(partial(render_list, rows, cache=cache)),
            asyncio.to_thread(partial(_render_bluf_all_sections, rows)),
        )
        return {
            f"brief{suffix}.md": brief_md,
            f"cluster{suffix}.md": cluster_md,
            f"list{suffix}.md": list_md,
            f"bluf{suffix}.md": bluf_md,
        }

    # Default view
    files = await _render_view(enrichment_rows, "")
    # COP and CIP views
    files.update(await _render_view(cop_rows, "-cop"))
    files.update(await _render_view(cip_rows, "-cip"))

    # Write atomically (BACKSTOP: concurrent SAB writes via .tmp + os.replace)
    for name, content in files.items():
        fpath = DATA_DIR / name
        tmp = fpath.with_suffix(".tmp")
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, fpath)
        log.info("wrote %s", fpath)

    # Write Obsidian vault projection (SC2, SC3)
    vault_dir = Path(os.environ.get("INFOTRIAGE_VAULT_PATH", "data/obsidian"))
    await asyncio.to_thread(
        write_vault_digest,
        enrichment_rows,
        vault_dir,
        write_items=True,
        sab_filename="obsidian-sab.md",
        store=store,
        cache=cache,
    )
    await asyncio.to_thread(
        write_vault_digest,
        cop_rows,
        vault_dir,
        write_items=False,
        sab_filename="obsidian-sab-cop.md",
        store=store,
        cache=cache,
    )
    await asyncio.to_thread(
        write_vault_digest,
        cip_rows,
        vault_dir,
        write_items=False,
        sab_filename="obsidian-sab-cip.md",
        store=store,
        cache=cache,
    )
    log.info("wrote Obsidian vault projections (default, cop, cip)")

    # Publish SabPublished event
    ccir_topics = sorted(
        {
            (r.get("ccir") or "none").upper()
            for r in enrichment_rows
            if (r.get("ccir") or "none").lower() != "none"
        }
    )

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
            "url": r.get("url", ""),
            "ts": r.get("ts", ""),
        }
        for r in enrichment_rows[:50]  # top 50 refs
    ]

    event = SabPublished(
        event="sab.published",
        pub_ts=__import__("datetime").datetime.now(
            tz=__import__("datetime").timezone.utc
        ),
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
    log.info(
        "published SabPublished for day=%s, %d items", snap_day, len(enrichment_rows)
    )
    return event


def _render_bluf_all_sections(enrichment_rows: list[dict]) -> str:
    # plain def — runs inside asyncio.to_thread; async def here returned an
    # un-awaited coroutine to write_text (TypeError: data must be str)
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


async def on_verdict_message(
    message, store, bus, *, cluster_threshold: float = 0.75
) -> None:
    """Decode a verdict.ready message and run process_verdict.

    message.process() acks on clean return, nacks (requeue=False -> DLQ) on error.
    """
    async with message.process():
        item_id = message.headers["item_id"]
        log.info("verdict.ready item_id=%s", item_id)

        snap_day = __import__("datetime").date.today().isoformat()
        try:
            await process_verdict(
                item_id,
                store,
                bus,
                snap_day=snap_day,
                cluster_threshold=cluster_threshold,
            )
        except Exception as e:
            log.error(
                "process_verdict failed for item_id=%s: %s", item_id, e, exc_info=True
            )
            raise  # re-raise so message.process() nacks


# ---------------------------------------------------------------------------
# run_consumer — wires on_verdict_message to the bus's persistent consumer
# ---------------------------------------------------------------------------


async def run_consumer(bus, store, *, cluster_threshold: float = 0.75) -> None:
    """Register the verdict.ready consumer and run forever."""
    await bus._ensure_connection()

    async def _handler(message) -> None:
        await on_verdict_message(
            message, store, bus, cluster_threshold=cluster_threshold
        )

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
