#!/usr/bin/env python3
"""emitter.py — CAT I verdict.ready -> ntfy 7-field payload + event consumer.

The wire `verdict.ready` event carries no pmesii/title/summary (see
`libs/contracts/src/contracts/_events.py::VerdictReady`), so the alert
payload cannot be built from the message alone — this module joins the
event's item_id against the Store for the enrichment (`why`, `pmesii`) and
item (`summary`) fields it needs (RESEARCH.md Finding 1).

Only CAT I (`cnr == "I"`) verdicts produce egress (ADR-015 D1).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import uuid

from deep_link import item_note_link, sab_note_link

log = logging.getLogger(__name__)

CAT_I = "I"
MAX_EXCERPT_CHARS = 500


def build_alert_payload(item, enrichment: dict, item_id: str, cnr_tier: str) -> dict:
    """Build the exact 7-key SPEC R1 payload dict.

    Keys (spelled exactly as SPEC R1 locks them, `pmseii_tags` is the SPEC's
    literal spelling and MUST NOT be normalized): alert_id, sab_excerpt,
    dedupe_id, cnr_tier, item_link, pmseii_tags, deep_link.
    """
    why = (enrichment.get("why") or "").strip()
    summary = (getattr(item, "summary", None) or "").strip()
    sab_excerpt = (why or summary or "")[:MAX_EXCERPT_CHARS]

    dedupe_id = hashlib.sha256(f"{item_id}|{cnr_tier}".encode()).hexdigest()[:16]

    pmesii_raw = (enrichment.get("pmesii") or "").strip()
    pmseii_tags = (
        [tag.strip() for tag in pmesii_raw.split(",") if tag.strip()]
        if pmesii_raw
        else []
    )

    return {
        "alert_id": uuid.uuid4().hex,
        "sab_excerpt": sab_excerpt,
        "dedupe_id": dedupe_id,
        "cnr_tier": cnr_tier,
        "item_link": sab_note_link(),
        "pmseii_tags": pmseii_tags,
        "deep_link": item_note_link(item_id),
    }


async def handle_trigger(item_id: str, payload: dict, store, client) -> None:
    """Handle one verdict.ready trigger — CAT I only, else no egress at all."""
    cnr_tier = payload.get("cnr")
    if cnr_tier != CAT_I:
        return

    item = store.get_item(item_id)
    enrichment = store.get_enrichment(item_id)
    if item is None or enrichment is None:
        log.warning(
            "alerting: missing item or enrichment for item_id=%s — skipping alert",
            item_id,
        )
        return

    alert_payload = build_alert_payload(item, enrichment, item_id, cnr_tier)
    await client.deliver(alert_payload)


async def run_consumer(bus, store, client) -> None:
    """Consume verdict.ready off q.alerting and fire handle_trigger per message.

    Mirrors apps/wiki/wiki_worker.py's consumer shape.
    """
    await bus._ensure_connection()

    async def _handler(message) -> None:
        async with message.process():
            body = json.loads(message.body.decode())
            item_id = message.headers["item_id"]
            await handle_trigger(item_id, body, store, client)

    await bus.consume(
        "verdict.ready", _handler, prefetch_count=1, queue_name="q.alerting"
    )
    await asyncio.Future()  # run forever
