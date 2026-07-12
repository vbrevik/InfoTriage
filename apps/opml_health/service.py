"""opml-health — scheduled feed health-check worker.

Probes every feed in ``opml/feeds.opml``, classifies live/broken/unreachable,
and emits ``FeedUnhealthy`` events to ``q.ops`` via RabbitMQ for any
non-live feed.

When run as an async main (scheduled worker mode):
  - loads OPML, probes in parallel, emits unhealthy events
When imported as a library:
  - exports ``run_health_check()`` for callers

Usage (standalone):
    python -m apps.opml_health                # probe + emit, exit 0/1
    python -m apps.opml_health --hours 4      # only flags feeds last-seen > 4h ago

Environment:
    INFOTRIAGE_OPML_PATH   path to feeds.opml (default: opml/feeds.opml)
    INFOTRIAGE_OPML_HEALTH_RABBITMQ_URL  AMQP_URL for RabbitMQ
    INFOTRIAGE_OPML_HEALTH_PORT          HTTP port (default: 22032)
    INFOTRIAGE_OPML_HEALTH_SINCE_HOURS   minimum silent hours before emitting (default: 24)
"""

import asyncio
import argparse
import concurrent.futures
import datetime
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Optional

from contracts import setup_logging, FeedUnhealthy
from fastapi import FastAPI, Response
from pydantic import ValidationError

setup_logging("opml-health")

# --- health-check core (re-uses apps/opml/_check.py helpers) ---
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from apps.opml._check import (  # noqa: E402
    DEFAULT_UA,
    DEFAULT_TIMEOUT,
    load_opml,
    probe,
    classify,
    probe_and_classify,
)

log = logging.getLogger("opml.health")


# --- health-check dispatcher ---
def run_health_check(
    opml_path: Optional[str] = None,
    ua: str = DEFAULT_UA,
    timeout: int = DEFAULT_TIMEOUT,
    since_hours: float = 24,
) -> tuple[list[dict[str, Any]], list[FeedUnhealthy]]:
    """Run a full health-check on OPML feeds.

    Returns ``(results, unhealthy_events)`` where results is a list of
    ``{"text", "url", "emoji", "reason"}`` dicts and unhealthy_events
    is a list of ``FeedUnhealthy`` instances for non-live feeds.
    """
    opml_path = opml_path or os.environ.get(
        "INFOTRIAGE_OPML_PATH",
        str(Path(__file__).resolve().parent.parent / "opml" / "feeds.opml"),
    )
    groups = load_opml(opml_path)
    flat = [(cat, o) for cat, outlines in groups for o in outlines]
    if not flat:
        return [], []

    results = []
    unhealthy = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        futures = {
            ex.submit(probe_and_classify, o, ua, timeout): (cat, o) for cat, o in flat
        }
        for fut in concurrent.futures.as_completed(futures):
            _cat, o = futures[fut]
            try:
                text, url, emoji, reason = fut.result()
            except Exception as e:
                text, url, emoji, reason = "", "", "❌", f"probe exception: {e}"
            results.append({"text": text, "url": url, "emoji": emoji, "reason": reason})
            if emoji not in ("✅", "🟡"):
                # Inner try/except (Option B): the canonical Pydantic model enforces
                # Field(max_length=120) on `reason`. If a probe's `reason` (e.g. a
                # stdlib error chain from urllib3/requests) exceeds 120 chars, the
                # prior exception handler (above) ONLY covers `fut.result()` -- the
                # unguarded FeedUnhealthy(...) construction here would propagate
                # ValidationError out of `as_completed`, terminating the thread-executor
                # loop mid-batch and crashing the entire `run_health_check()`. Trap
                # the ValidationError locally so a single over-long reason can't
                # cascade-kill the remaining feeds in the batch.
                try:
                    unhealthy.append(
                        FeedUnhealthy(
                            event="feed.unhealthy",
                            feed_url=url,
                            feed_name=text,
                            reason=f"{emoji} {reason}",
                            ts=datetime.datetime.now(datetime.timezone.utc),
                        )
                    )
                except ValidationError as e:
                    log.error(
                        "Discarding feed.unhealthy event for %s due to schema "
                        "validation failure (reason > 120 chars? malformed ts?): %s",
                        url,
                        e,
                    )
    return results, unhealthy


# --- RabbitMQ publisher (async) ---
async def emit_unhealthy_events(unhealthy: list[FeedUnhealthy]) -> None:
    """Publish each unhealthy event to q.ops via RabbitMQ bus."""
    from contracts import RabbitMQBus

    amqp_url = os.environ.get(
        "INFOTRIAGE_OPML_HEALTH_RABBITMQ_URL",
        os.environ.get("RABBITMQ_URL", "amqp://guest:guest@localhost:5672"),
    )
    bus = RabbitMQBus(amqp_url=amqp_url)
    try:
        await bus.connect()  # type: ignore[attr-defined]
        for evt in unhealthy:
            d = evt.model_dump(mode="json")
            item_id = d.get("item_id", f"uh-{abs(hash(d['feed_url'])) % (10**12)}")
            await bus.publish(
                "feed.unhealthy",
                item_id=item_id,
                payload={
                    "event": "feed.unhealthy",
                    "feed_url": d["feed_url"],
                    "feed_name": d["feed_name"],
                    "reason": d["reason"],
                    "last_ok_at": d.get("last_ok_at"),
                    "ts": d["ts"],
                },
            )
    finally:
        await bus.close()


# --- FastAPI app (HTTP layer on :22032) ---
app = FastAPI(title="opml-health", version="0.1.0")


@app.get("/health")
async def health() -> Response:
    return Response(content="ok", media_type="text/plain", status_code=200)


@app.get("/report")
async def report() -> dict:
    results, _unhealthy = run_health_check()
    return {"status": "ok", "feed_count": len(results), "results": results}


# --- standalone entry ---
async def run_main() -> None:
    """Async entry: probe, emit unhealthy events, exit."""
    ap = argparse.ArgumentParser(
        description="opml-health: probe feeds, emit unhealthy events"
    )
    ap.add_argument("--opml", default=None, help="path to feeds.opml")
    ap.add_argument(
        "--no-emit", action="store_true", help="probe but don't emit to RabbitMQ"
    )
    ap.add_argument(
        "--since-hours", type=float, default=24, help="flag feeds silent > N hours"
    )
    args = ap.parse_args()

    results, unhealthy = run_health_check(opml_path=args.opml)
    n_total = len(results)
    n_ok = sum(1 for r in results if r["emoji"] == "✅")
    n_bad = n_total - n_ok
    log.info("opml-health: probed %d feeds, %d OK, %d unhealthy", n_total, n_ok, n_bad)
    print(f"Probed {n_total} feeds · ✅ {n_ok} live · ❌ {n_bad} unhealthy")

    if unhealthy and not args.no_emit:
        log.info("Emitting %d unhealthy events to q.ops", len(unhealthy))
        await emit_unhealthy_events(unhealthy)
    elif not args.no_emit:
        log.info("No unhealthy feeds to emit")
    else:
        log.info("Emitted suppressed by --no-emit")

    if n_bad > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    asyncio.run(run_main())
