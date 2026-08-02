#!/usr/bin/env python3
"""outbox.py — authenticated ntfy HTTP egress with in-process retry and a
terminal alerting dead-letter queue (SPEC R4, Phase 12 plan 12-06). The only
network egress this phase introduces (T-12-02).

Security: never log the token or the Authorization header value; the deliver
path never logs the full payload (method/topic/status code only), and the
dead-letter path never logs the payload body or a credential (T-12-30) —
item id and reason only.
"""
from __future__ import annotations

import asyncio
import json
import logging

import httpx

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 10.0

# SPEC R4-locked retry schedule: 1 second then 5 seconds between the 3 total
# attempts (1 initial + 2 retries). Data, not control flow — a fixed,
# SPEC-locked two-element schedule doesn't earn a new backoff pip dependency
# (RESEARCH §Don't Hand-Roll).
RETRY_SCHEDULE: tuple[int, ...] = (1, 5)

# Terminal alerting dead-letter routing key (Task 1's ROUTING_KEY_TO_QUEUE
# entry) — distinct from the project-wide infotriage.dlq (RESEARCH
# anti-pattern, SPEC R4).
DLX_ROUTING_KEY = "outbox.dlx"


class NtfyClient:
    """Minimal authenticated ntfy publisher for the CAT I alert payload."""

    def __init__(self, base_url: str, token: str, topic: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._topic = topic

    async def deliver(self, payload: dict, item_title: str = "") -> None:
        """POST payload to {base_url}/{topic} with bearer auth + ntfy headers.

        `item_title` is the item's own title (NOT part of the 7-key JSON
        payload body — SPEC R1 locks that to 7 keys) used only to derive the
        `X-Title` header, single line, truncated to 80 characters.

        Raises on non-2xx via httpx's raise_for_status().
        """
        url = f"{self._base_url}/{self._topic}"

        title_line = (
            (item_title or "").strip().splitlines()[0]
            if (item_title or "").strip()
            else ""
        )
        title = (
            title_line[:80]
            if title_line
            else (f"CAT {payload.get('cnr_tier', '')} Alert")
        )
        tags = ",".join(
            ["triangular_flag_on_post", *(payload.get("pmseii_tags") or [])]
        )

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._token}",
            "X-Title": title,
            "X-Priority": "5",
            "X-Tags": tags,
            "X-Click": payload.get("deep_link", ""),
        }

        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as http_client:
            response = await http_client.post(
                url, content=json.dumps(payload), headers=headers
            )
        response.raise_for_status()
        # Never log the token/Authorization header value or the full payload (T-12-02).
        log.info(
            "ntfy delivery method=POST topic=%s status=%s",
            self._topic,
            response.status_code,
        )


async def deliver_with_retry(
    client: NtfyClient,
    store,
    bus,
    payload: dict,
    *,
    item_id: str,
    item_title: str = "",
) -> None:
    """Deliver `payload` via `client`, retrying on the SPEC R4 1s/5s schedule.

    Three attempts total: the initial attempt, then one after RETRY_SCHEDULE[0]
    seconds, then one after RETRY_SCHEDULE[1] seconds. A non-2xx response
    (httpx.HTTPStatusError, raised by NtfyClient.deliver's raise_for_status())
    and a transport-level connection error (httpx.RequestError, e.g.
    httpx.ConnectError) are both treated as a failure and retried identically.

    On success, records the delivered outcome on the alert-state row (keyed
    by payload["dedupe_id"]) and returns. On exhaustion, calls dead_letter().

    Ordering matters and MUST be preserved: the durable dead-letter record is
    written (inside dead_letter, awaited below) before this coroutine
    returns — so the caller's `message.process()` context has NOT yet acked
    the trigger message. A crash anywhere before that point leaves the
    trigger message unacked and the broker redelivers it on restart — this is
    the entire mechanism behind SPEC R4's total-outage guarantee, and it is
    why there is no local spool. Do not move the ack earlier (e.g. by
    fire-and-forgetting this call) for throughput — that would reopen the
    loss window this plan closes.
    """
    dedupe_id = payload.get("dedupe_id")
    total_attempts = len(RETRY_SCHEDULE) + 1
    reason = ""
    attempts = 0

    for attempt_index in range(total_attempts):
        attempts = attempt_index + 1
        try:
            await client.deliver(payload, item_title=item_title)
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            reason = f"{type(exc).__name__}: {exc}"
            log.warning(
                "alerting: delivery attempt %s/%s failed item_id=%s error=%s",
                attempts,
                total_attempts,
                item_id,
                type(exc).__name__,
            )
        else:
            store.mark_alert_outcome(dedupe_id, outcome="delivered")
            return

        if attempt_index < len(RETRY_SCHEDULE):
            await asyncio.sleep(RETRY_SCHEDULE[attempt_index])

    await dead_letter(
        store, bus, payload, item_id=item_id, reason=reason, attempts=attempts
    )


async def dead_letter(
    store,
    bus,
    payload: dict,
    *,
    item_id: str,
    reason: str,
    attempts: int,
) -> None:
    """Durably record a terminal delivery failure. Three durable actions, in
    this order:

    1. Publish the full payload (plus `reason` and `attempts`) to the
       `outbox.dlx` routing key — the alert is reconstructable from the queue
       alone (SPEC R4).
    2. Write an audit row (`alert_dead_lettered`) naming the item, the
       dead-lettered alert_id/dedupe_id, the attempt count, and the reason.
    3. Record the dead-lettered outcome on the alert-state row.

    Logs at error level with the item id and reason only — never the payload
    body or a credential (T-12-30).
    """
    dlx_payload = {**payload, "reason": reason, "attempts": attempts}
    await bus.publish(DLX_ROUTING_KEY, item_id, dlx_payload)

    store.audit_write(
        op="alert_dead_lettered",
        table_name="alert_state",
        item_id=item_id,
        details={
            "alert_id": payload.get("alert_id"),
            "dedupe_id": payload.get("dedupe_id"),
            "attempts": attempts,
            "reason": reason,
        },
    )

    store.mark_alert_outcome(payload.get("dedupe_id"), outcome="dead_lettered")

    log.error(
        "alerting: dead-lettered item_id=%s reason=%s attempts=%s",
        item_id,
        reason,
        attempts,
    )
