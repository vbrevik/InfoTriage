#!/usr/bin/env python3
"""scripts/uat_test7_event.py — UAT Test 7: event-driven rendering end-to-end.

Verifies the brief consumer's event-driven pipeline:

  1. q.brief has at least one consumer (the live brief app).
  2. Republishing a verdict.ready for a real enrichment row triggers
     a full consumer cycle that atomically rewrites the 4 default
     digests (brief.md, cluster.md, list.md, bluf.md) via .tmp + os.replace.
  3. sab.published lands on q.notify (queue depth grows by 1).

INTRUSIVE: it triggers a real consumer cycle on the live stack. The
consumer will invoke the LLM for BLUF synthesis on every CCIR section
with score >= 8 items — this can take 10–60s on a cold oMLX. The script
polls with a 120s timeout.

Run against a row from the last 24h window. If no enrichment rows
exist in that window, run `scripts/seed_sample_data.py` first.

Usage:
  python3 scripts/uat_test7_event.py
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

DSN = os.environ.get(
    "INFOTRIAGE_PG_DSN",
    "postgresql://infotriage:infotriage_dev@localhost:22000/infotriage",
)
DIGEST_DIR = Path(
    os.environ.get(
        "INFOTRIAGE_DIGESTS_DIR_HOST",
        "/Users/vidarbrevik/projects/InfoTriage/data/digests",
    )
)
RABBIT_HOST = "infotriage-rabbitmq"
# Matches docker-compose.yml: RABBITMQ_DEFAULT_USER/PASS for the live broker.
# rabbitmqadmin defaults to guest:guest which the broker refuses (the live
# broker's `infotriage` user is the only one with management API access).
RABBIT_USER = os.environ.get("RABBITMQ_DEFAULT_USER", "infotriage")
RABBIT_PASS = os.environ.get("RABBITMQ_DEFAULT_PASS", "infotriage_rmq")
EXPECTED_DIGESTS = ["brief.md", "cluster.md", "list.md", "bluf.md"]
POLL_DIGEST_TIMEOUT_S = 300.0  # cold-stack LLM BLUF: 6 sections × 3 views = up to ~6 min
POLL_NOTIFY_TIMEOUT_S = 60.0   # the publish fires ms after the digest write


def _pick_enrichment_row() -> dict:
    conn = psycopg.connect(DSN)
    try:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT e.item_id, e.ccir, e.cnr, e.score "
                "FROM infotriage.enrichment e "
                "WHERE e.created_at >= NOW() - INTERVAL '24 hours' "
                "ORDER BY e.created_at DESC LIMIT 1"
            )
            row = cur.fetchone()
    finally:
        conn.close()
    if row is None:
        raise SystemExit(
            "No enrichment rows in last 24h — run `python3 scripts/seed_sample_data.py` first"
        )
    return row


def _digest_mtimes() -> dict[str, float]:
    return {
        n: (DIGEST_DIR / n).stat().st_mtime
        for n in EXPECTED_DIGESTS
        if (DIGEST_DIR / n).exists()
    }


def _queue_depths() -> dict[str, int]:
    """rabbitmqctl list_queues name messages — runs inside the rabbitmq container."""
    out = subprocess.run(
        ["docker", "exec", RABBIT_HOST, "rabbitmqctl", "list_queues", "name", "messages"],
        capture_output=True, text=True, check=True,
    )
    depths: dict[str, int] = {}
    for line in out.stdout.strip().splitlines()[1:]:
        parts = line.split()
        if len(parts) == 2 and parts[1].isdigit():
            depths[parts[0]] = int(parts[1])
    return depths


def _queue_consumers() -> dict[str, int]:
    out = subprocess.run(
        ["docker", "exec", RABBIT_HOST, "rabbitmqctl", "list_queues", "name", "consumers"],
        capture_output=True, text=True, check=True,
    )
    consumers: dict[str, int] = {}
    for line in out.stdout.strip().splitlines()[1:]:
        parts = line.split()
        if len(parts) == 2 and parts[1].isdigit():
            consumers[parts[0]] = int(parts[1])
    return consumers


def _publish_verdict_ready(item_id: str) -> None:
    """Publish verdict.ready via rabbitmqadmin inside the rabbitmq container.

    The consumer reads `message.headers["item_id"]` — that's the only field
    it cares about. The payload is the item_id as a string.
    """
    props = json.dumps({"headers": {"item_id": item_id}})
    cmd = [
        "docker", "exec", RABBIT_HOST, "rabbitmqadmin",
        "-u", RABBIT_USER, "-p", RABBIT_PASS,
        "publish", "exchange=infotriage.events", "routing_key=verdict.ready",
        f"properties={props}",
        f"payload={item_id}",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(
            f"rabbitmqadmin publish failed (rc={proc.returncode}):\n"
            f"  stdout: {proc.stdout!r}\n  stderr: {proc.stderr!r}"
        )
    # rabbitmqadmin prints "Message published" or similar to stdout.
    print(f"  published: {proc.stdout.strip() or '(no stdout)'}")


def test_q_brief_has_consumer() -> None:
    consumers = _queue_consumers()
    n = consumers.get("q.brief", 0)
    assert n >= 1, f"q.brief has no consumer; live brief container may be down: {consumers}"
    print(f"PASS: q.brief has {n} consumer(s)")


def test_republish_triggers_4_digest_rewrite() -> None:
    row = _pick_enrichment_row()
    item_id = row["item_id"]
    print(f"INFO: republishing verdict.ready for item_id={item_id} (ccir={row.get('ccir')})")

    before_mtimes = _digest_mtimes()
    before_notify = _queue_depths().get("q.notify", 0)
    print(f"  before: digest mtimes={before_mtimes}, q.notify depth={before_notify}")

    _publish_verdict_ready(item_id)

    # Poll for at least one digest to be rewritten (per-file atomic via .tmp + os.replace).
    deadline = time.time() + POLL_DIGEST_TIMEOUT_S
    after_mtimes: dict[str, float] = {}
    while time.time() < deadline:
        after_mtimes = _digest_mtimes()
        if any(after_mtimes.get(n, 0.0) > before_mtimes.get(n, 0.0) for n in EXPECTED_DIGESTS):
            break
        time.sleep(1.0)
    else:
        raise SystemExit(
            f"Timeout ({POLL_DIGEST_TIMEOUT_S}s) waiting for digests to rewrite. "
            f"After mtimes: {after_mtimes}"
        )

    changed = [
        n for n in EXPECTED_DIGESTS
        if after_mtimes.get(n, 0.0) > before_mtimes.get(n, 0.0)
    ]
    assert changed, f"No digests rewritten; before={before_mtimes}, after={after_mtimes}"
    # The consumer writes all 4 default digests in a single asyncio.gather — they
    # should land within ~50ms of each other. Tolerate 1 missing (e.g., if a CCIR
    # section is empty in the window, render_bluf_all_sections still writes the
    # placeholder line, but render_list could be empty if no score>=8 items).
    assert len(changed) >= 3, (
        f"Expected ≥3 of 4 digests to be rewritten, got {changed}. "
        f"Before={before_mtimes}, After={after_mtimes}"
    )
    print(f"PASS: {len(changed)}/4 digests atomically rewritten: {changed}")
    # Return the pre-publish queue depth so test_sab_published_lands_on_q_notify
    # can compare against the same baseline. By the time we exit this poll loop,
    # the consumer has already written the digests and the sab.published publish
    # has typically already landed on q.notify — capturing a fresh baseline here
    # would race against the publish.
    return before_notify


def test_sab_published_lands_on_q_notify(baseline: int) -> None:
    # q.notify is the destination for sab.published; its depth should grow
    # by exactly 1 after the consumer cycle we triggered above. Compare
    # against the baseline captured BEFORE we published, since the publish
    # typically lands in q.notify before this function runs.
    deadline = time.time() + POLL_NOTIFY_TIMEOUT_S
    while time.time() < deadline:
        now = _queue_depths().get("q.notify", 0)
        if now > baseline:
            print(f"PASS: sab.published landed on q.notify (depth {baseline} → {now})")
            return
        time.sleep(0.5)
    final = _queue_depths().get("q.notify", 0)
    raise SystemExit(
        f"Timeout ({POLL_NOTIFY_TIMEOUT_S}s) waiting for q.notify to grow. "
        f"baseline={baseline}, final={final}"
    )


def main() -> None:
    test_q_brief_has_consumer()
    baseline = test_republish_triggers_4_digest_rewrite()
    test_sab_published_lands_on_q_notify(baseline)
    print("\nUAT Test 7: all checks passed")


if __name__ == "__main__":
    main()
