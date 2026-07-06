"""opml-health — scheduled feed health-check worker.

Probes every feed in ``opml/feeds.opml``, classifies live/broken/unreachable,
and emits ``FeedUnhealthy`` events to ``q.ops`` via RabbitMQ for any
non-live feed.

When run as an async main (scheduled worker mode):
  - loads OPML, probes in parallel, emits unhealthy events
When imported as a library:
  - exports ``run_health_check()`` for callers

Usage (standalone):
    python -m apps.opml-health                # probe + emit, exit 0/1
    python -m apps.opml-health --hours 4      # only flags feeds last-seen > 4h ago

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
from typing import Optional

from fastapi import FastAPI, Response

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

# --- event model (inline, avoids contracts import cost) ---
class FeedUnhealthy:
    """Simplified FeedUnhealthy for local emission."""

    def __init__(
        self,
        feed_url: str,
        feed_name: str,
        reason: str,
        last_ok_at: Optional[datetime.datetime] = None,
        ts: Optional[datetime.datetime] = None,
    ):
        self.feed_url = feed_url
        self.feed_name = feed_name
        self.reason = reason[:120]
        self.last_ok_at = last_ok_at
        self.ts = ts or datetime.datetime.now(datetime.timezone.utc)

    def to_dict(self) -> dict:
        ts = self.ts
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=datetime.timezone.utc)
        d = {
            "event": "feed.unhealthy",
            "feed_url": self.feed_url,
            "feed_name": self.feed_name,
            "reason": self.reason,
            "ts": ts.isoformat(),
        }
        if self.last_ok_at:
            lo = self.last_ok_at
            if lo.tzinfo is None:
                lo = lo.replace(tzinfo=datetime.timezone.utc)
            d["last_ok_at"] = lo.isoformat()
        return d


# --- health-check dispatcher ---
def run_health_check(
    opml_path: Optional[str] = None,
    ua: str = DEFAULT_UA,
    timeout: int = DEFAULT_TIMEOUT,
    since_hours: float = 24,
) -> list[dict]:
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
        futures = {ex.submit(probe_and_classify, o, ua, timeout): (cat, o)
                   for cat, o in flat}
        for fut in concurrent.futures.as_completed(futures):
            _cat, o = futures[fut]
            try:
                text, url, emoji, reason = fut.result()
            except Exception as e:
                text, url, emoji, reason = "", "", "❌", f"probe exception: {e}"
            results.append({"text": text, "url": url, "emoji": emoji, "reason": reason})
            if emoji not in ("✅", "🟡"):
                unhealthy.append(FeedUnhealthy(
                    feed_url=url,
                    feed_name=text,
                    reason=f"{emoji} {reason}",
                ))
    return results, unhealthy


# --- RabbitMQ publisher (async) ---
async def emit_unhealthy_events(unhealthy: list[FeedUnhealthy]) -> None:
    """Publish each unhealthy event to q.ops via RabbitMQ bus."""
    from libs.contracts.src.contracts._bus_rabbitmq import RabbitMQBus
    from libs.contracts.src.contracts._events import FeedUnhealthy as ContractEvent

    amqp_url = os.environ.get(
        "INFOTRIAGE_OPML_HEALTH_RABBITMQ_URL",
        os.environ.get("RABBITMQ_URL", "amqp://guest:guest@localhost:5672"),
    )
    bus = RabbitMQBus(amqp_url=amqp_url)
    try:
        await bus.connect()
        for evt in unhealthy:
            d = evt.to_dict()
            item_id = d.get("item_id", f"uh-{abs(hash(d['feed_url'])) % (10**12)}")
            await bus.publish("feed.unhealthy", item_id=item_id, payload={
                "event": "feed.unhealthy",
                "feed_url": d["feed_url"],
                "feed_name": d["feed_name"],
                "reason": d["reason"],
                "last_ok_at": d.get("last_ok_at"),
                "ts": d["ts"],
            })
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
    ap = argparse.ArgumentParser(description="opml-health: probe feeds, emit unhealthy events")
    ap.add_argument("--opml", default=None, help="path to feeds.opml")
    ap.add_argument("--no-emit", action="store_true", help="probe but don't emit to RabbitMQ")
    ap.add_argument("--since-hours", type=float, default=24, help="flag feeds silent > N hours")
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
