#!/usr/bin/env python3
"""emitter.py — CAT I verdict.ready / sab.published -> ntfy 7-field payload,
gated by the atomic dedupe claim (SPEC R1 exactly-once, R2 dedupe_id + TTL).

The wire `verdict.ready` event carries no pmesii/title/summary (see
`libs/contracts/src/contracts/_events.py::VerdictReady`), so the alert
payload cannot be built from the message alone — this module joins the
event's item_id against the Store for the enrichment (`why`, `pmesii`) and
item (`summary`) fields it needs (RESEARCH.md Finding 1).

Only CAT I (`cnr == "I"`) verdicts produce egress (ADR-015 D1). Both
`verdict.ready` and `sab.published` are bound to `q.alerting` (D-01);
`sab.published` is a fallback second look at the CAT I set, never an
authoritative list — its item_refs array is capped at the top 50 refs by
score on the producer side (apps/brief/consumer.py), so a low-scoring CAT I
item can be absent from it (RESEARCH finding 2). `dedupe.claim` is the only
ordering guarantee between the two triggers; whichever arrives second is
collapsed by the atomic claim before any egress happens.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Iterator

from deep_link import item_note_link, sab_note_link
from dedupe import claim, compute_dedupe_id
from outbox import deliver_with_retry
from throttle import check_throttle

log = logging.getLogger(__name__)

CAT_I = "I"
MAX_EXCERPT_CHARS = 500


def build_alert_payload(
    item,
    enrichment: dict,
    item_id: str,
    cnr_tier: str,
    *,
    alert_id: str | None = None,
    dedupe_id: str | None = None,
) -> dict:
    """Build the exact 7-key SPEC R1 payload dict.

    Keys (spelled exactly as SPEC R1 locks them, `pmseii_tags` is the SPEC's
    literal spelling and MUST NOT be normalized): alert_id, sab_excerpt,
    dedupe_id, cnr_tier, item_link, pmseii_tags, deep_link.

    `alert_id`/`dedupe_id` default to freshly generated/computed values so
    direct callers (e.g. the tracer test) keep working unchanged; the
    dual-trigger emit path passes both through from its winning `claim()`
    call so the payload's alert id and the stored row agree.
    """
    why = (enrichment.get("why") or "").strip()
    summary = (getattr(item, "summary", None) or "").strip()
    sab_excerpt = (why or summary or "")[:MAX_EXCERPT_CHARS]

    pmesii_raw = (enrichment.get("pmesii") or "").strip()
    pmseii_tags = (
        [tag.strip() for tag in pmesii_raw.split(",") if tag.strip()]
        if pmesii_raw
        else []
    )

    return {
        "alert_id": alert_id or uuid.uuid4().hex,
        "sab_excerpt": sab_excerpt,
        "dedupe_id": dedupe_id or compute_dedupe_id(item_id, cnr_tier),
        "cnr_tier": cnr_tier,
        "item_link": sab_note_link(),
        "pmseii_tags": pmseii_tags,
        "deep_link": item_note_link(item_id),
    }


async def _emit_if_claimed(
    item_id: str, cnr_tier: str, store, client, *, bus=None, now=None
) -> None:
    """Shared emit path: claim first, egress only on a winning claim.

    No read of the item/enrichment happens before the claim — the claim
    itself is the single atomic check-and-set (SPEC R1). A losing claim
    (the second of two racing triggers, or a re-fire within the TTL) returns
    immediately with zero egress.

    After a winning claim, the item/enrichment rows are read (needed both
    for the payload AND for the suppression record, since a throttled alert
    still needs its pmesii/title recorded), then the sliding-window throttle
    gate runs (RESEARCH.md priority ordering: dedupe, then throttle, then
    digest). A throttled alert is marked suppressed rather than dropped
    (SPEC R3) — it is not lost, it is pending the next hourly digest — and
    the message is still acked by the caller; only the egress is skipped.

    `bus` defaults to None so pre-12-06 direct callers (the tracer test,
    the throttle/emitter test suites) keep working unchanged — none of them
    exercise the delivery-exhaustion path, so deliver_with_retry never
    reaches for it. run_consumer always passes the real bus (SPEC R4).
    """
    alert_id = uuid.uuid4().hex
    dedupe_id, claimed = claim(
        store, item_id=item_id, cnr_tier=cnr_tier, alert_id=alert_id, now=now
    )
    if not claimed:
        return

    item = store.get_item(item_id)
    enrichment = store.get_enrichment(item_id)
    if item is None or enrichment is None:
        log.warning(
            "alerting: missing item or enrichment for item_id=%s — skipping alert",
            item_id,
        )
        return

    item_title = getattr(item, "title", None) or ""

    verdict = check_throttle(store, now=now)
    if not verdict.passed:
        pmesii_text = (enrichment.get("pmesii") or "").strip() or None
        store.mark_alert_suppressed(dedupe_id, pmesii=pmesii_text, title=item_title)
        log.info(
            "alerting: throttled item_id=%s dedupe_id=%s tier=%s — suppressed, "
            "pending next digest",
            item_id,
            dedupe_id,
            verdict.tier,
        )
        return

    alert_payload = build_alert_payload(
        item, enrichment, item_id, cnr_tier, alert_id=alert_id, dedupe_id=dedupe_id
    )
    await deliver_with_retry(
        client, store, bus, alert_payload, item_id=item_id, item_title=item_title
    )


async def handle_verdict_ready(
    payload: dict, store, client, *, bus=None, now=None
) -> None:
    """Handle one verdict.ready trigger — CAT I only, else no egress at all.

    Reads the item id and the cnr value off the decoded event body itself
    (VerdictReady carries item_id — see _events.py), not off the message
    header.
    """
    cnr_tier = payload.get("cnr")
    if cnr_tier != CAT_I:
        return
    item_id = payload.get("item_id")
    if not item_id:
        return
    await _emit_if_claimed(item_id, cnr_tier, store, client, bus=bus, now=now)


def _extract_cat_i_item_ids(payload: dict) -> Iterator[str]:
    """Yield item ids from a sab.published event's item_refs whose ref-level
    cnr is the CAT I string.

    This array is capped at the top 50 refs by score on the producer side
    (apps/brief/consumer.py), so a low-scoring CAT I item can be absent from
    it — sab.published is a fallback second look, never an authoritative
    CAT I list (RESEARCH finding 2).
    """
    for ref in payload.get("item_refs") or []:
        if ref.get("cnr") == CAT_I:
            item_id = ref.get("item_id")
            if item_id:
                yield item_id


async def handle_sab_published(
    payload: dict, store, client, *, bus=None, now=None
) -> None:
    """Handle one sab.published trigger — the fallback second look at CAT I refs.

    Does NOT read the message header for an item id: for this event the
    header identifies the SAB snapshot, not an article.
    """
    for item_id in _extract_cat_i_item_ids(payload):
        await _emit_if_claimed(item_id, CAT_I, store, client, bus=bus, now=now)


async def handle_trigger(
    item_id: str, payload: dict, store, client, *, bus=None, now=None
) -> None:
    """Back-compat shim for the pre-12-04 tracer call shape (item_id passed
    explicitly, sourced from the message header).

    Superseded by `handle_verdict_ready` (reads item_id off the decoded
    payload body) for the dual-trigger consumer wired in `run_consumer`.
    Kept so tests/test_alerting_tracer.py's direct calls keep exercising the
    same CAT-I-gate + claim + deliver path unchanged.
    """
    cnr_tier = payload.get("cnr")
    if cnr_tier != CAT_I:
        return
    await _emit_if_claimed(item_id, cnr_tier, store, client, bus=bus, now=now)


async def run_consumer(bus, store, client) -> None:
    """Consume verdict.ready AND sab.published off the shared q.alerting queue.

    Both routing keys are bound to q.alerting (D-01). A single shared
    handler is registered for both consume() calls and dispatches on the
    decoded event's own "event" field — NOT on which consume() call
    delivered the message. RabbitMQ round-robins competing consumers
    attached to the same queue, so two DIFFERENT handler functions here
    would let either message shape land on either handler; using the same
    handler for both registrations makes that irrelevant.
    """
    await bus._ensure_connection()

    async def _handler(message) -> None:
        # message.process() acks on clean exit, nacks on exception. The
        # delivery outcome (delivered or dead-lettered) is recorded durably
        # inside deliver_with_retry/dead_letter BEFORE this block returns —
        # see outbox.py's deliver_with_retry docstring. Do not swallow any
        # exception raised below; a crash here must propagate so this
        # context nacks/leaves the message unacked rather than falsely
        # acking a trigger whose outcome was never durably recorded.
        async with message.process():
            body = json.loads(message.body.decode())
            event = body.get("event")
            if event == "verdict.ready":
                await handle_verdict_ready(body, store, client, bus=bus)
            elif event == "sab.published":
                await handle_sab_published(body, store, client, bus=bus)
            else:
                log.warning(
                    "alerting: unrecognized event=%s on q.alerting — ignoring", event
                )

    await bus.consume(
        "verdict.ready", _handler, prefetch_count=1, queue_name="q.alerting"
    )
    await bus.consume(
        "sab.published", _handler, prefetch_count=1, queue_name="q.alerting"
    )
    await asyncio.Future()  # run forever
