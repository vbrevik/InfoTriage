#!/usr/bin/env python3
"""digest.py — hourly PMESII-grouped digest of throttled CAT I alerts (D-03).

Implements D-03 verbatim: the alerting service runs its own asyncio hourly
tick — no `apps/scheduler` container coupling, no piggybacking on the next
alert event. When suppressed alerts exist since the last digest, publish
exactly ONE grouped message through the same authenticated `NtfyClient` the
alert path uses; an empty hour emits nothing at all.

SPEC R3's hard property carries through here: a throttled alert is never
silently dropped — it is enumerated by `alert_id` in this digest. Rows are
marked digested only AFTER a successful delivery, so a failed digest is
retried whole on the next tick rather than silently consuming rows it never
actually delivered.
"""
from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict

from deep_link import item_note_link

log = logging.getLogger(__name__)

UNCLASSIFIED_HEADING = "Unclassified"
DEFAULT_DIGEST_INTERVAL = 3600


def group_by_pmesii(rows: list[dict]) -> "OrderedDict[str, list[dict]]":
    """Group suppressed-alert rows by their primary PMESII tag.

    Splits each row's stored `pmesii` text on commas and uses the first
    non-empty element as the primary domain heading. A row whose pmesii is
    None, empty, or entirely comma/whitespace groups under
    UNCLASSIFIED_HEADING — it is NEVER dropped for lacking a tag; SPEC R3
    forbids losing a suppressed alert, and losing it inside this builder
    would count. Heading insertion order follows first-seen order across
    `rows`, matching the Store's stable pmesii/fired_at ordering.
    """
    grouped: "OrderedDict[str, list[dict]]" = OrderedDict()
    for row in rows:
        raw = (row.get("pmesii") or "").strip()
        primary = UNCLASSIFIED_HEADING
        if raw:
            for part in raw.split(","):
                part = part.strip()
                if part:
                    primary = part
                    break
        grouped.setdefault(primary, []).append(row)
    return grouped


def build_digest_message(rows: list[dict]) -> tuple[str, str]:
    """Return (title, body) for the digest message covering `rows`.

    Title follows D-03 verbatim: a warning glyph, the suppressed count, and
    the words identifying them as suppressed CAT I alerts —
    `"⚠ N suppressed CAT I alerts"`. Body renders one section per PMESII
    group (including the explicit Unclassified heading), each entry on its
    own line carrying the item title, its obsidian:// deep link, and its
    alert_id — plain text that reads correctly in a mobile push
    (formatting details beyond the grouped structure are Claude's
    Discretion per D-03).
    """
    count = len(rows)
    title = f"⚠ {count} suppressed CAT I alerts"

    grouped = group_by_pmesii(rows)
    lines: list[str] = []
    for heading, group_rows in grouped.items():
        lines.append(f"[{heading}]")
        for row in group_rows:
            item_title = (row.get("title") or "").strip() or "(untitled)"
            link = item_note_link(row["item_id"])
            lines.append(f"- {item_title} — {link} (alert_id={row['alert_id']})")
        lines.append("")
    body = "\n".join(lines).rstrip("\n")
    return title, body


async def publish_digest(store, client, rows: list[dict]) -> None:
    """Deliver one digest message covering `rows`, then mark them digested.

    Delivers through the same NtfyClient the alert path uses (one message
    to the same primary topic). `mark_alerts_digested` runs ONLY after a
    successful `deliver()` — if delivery raises, this function propagates
    the exception and no row is marked, so the next tick retries the same
    rows whole. No-op for an empty `rows` list (no request, no store call).
    """
    if not rows:
        return
    title, body = build_digest_message(rows)
    payload = {
        "cnr_tier": "digest",
        "sab_excerpt": f"{title}\n\n{body}",
        "pmseii_tags": [],
        "deep_link": "",
    }
    # NtfyClient's X-Title header goes through httpx's strict ASCII header
    # encoding, so the literal D-03 warning glyph (⚠) cannot ride an HTTP
    # header value — outbox.py's _ascii_safe_title choke point handles that
    # transliteration for every caller, including this digest title. The
    # JSON payload body above (no such constraint) carries the exact D-03
    # title text; the header carries the ASCII-safe form.
    await client.deliver(payload, item_title=title)
    await asyncio.to_thread(
        store.mark_alerts_digested, [row["dedupe_id"] for row in rows]
    )


async def run_digest_tick(
    store, client, *, interval: int = DEFAULT_DIGEST_INTERVAL
) -> None:
    """D-03's hourly tick: publish a digest when suppressed rows exist.

    Reads the undigested suppressed rows through the wiki-periodic-task's
    thread-offload shape (`asyncio.to_thread`, since Store calls are
    blocking), publishes when non-empty, does nothing when empty, catches
    and logs any exception so one bad hour never kills the task, then
    sleeps `interval`. Never couples to `apps/scheduler` and is never
    triggered from an incoming alert event (D-03) — the only caller is this
    loop's own sleep cycle.
    """
    while True:
        try:
            rows = await asyncio.to_thread(store.list_undigested_suppressed)
            if rows:
                await publish_digest(store, client, rows)
        except Exception as exc:
            log.error("alerting: digest tick failed: %s", exc)
        await asyncio.sleep(interval)
