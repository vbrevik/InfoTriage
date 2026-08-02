"""tests/test_alerting_throttle.py — SPEC R3 sliding-window throttle (Task 1)
and the hourly PMESII-grouped digest (Task 2).

Every boundary is driven with an injected clock (`now=...`), never a real
`time.sleep`. Task 1 tests select via `-k "throttle or window or boundary"`
per the plan's Task 1 `<verify>`; Task 2 extends this file with the digest
cases and runs unfiltered.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from contracts import Item
from store import InMemoryStore

from emitter import handle_verdict_ready
from outbox import NtfyClient
from throttle import WINDOW_10MIN_CAP, WINDOW_60S_CAP, check_throttle


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_item(url_seed: str, title: str = "A CAT I test item") -> Item:
    return Item(
        source="Test Source",
        source_type="rss",
        url=f"https://example.com/{url_seed}",
        title=title,
        ts=datetime.now(tz=timezone.utc),
        lang="en",
        summary="fallback summary text",
    )


def _seed(
    store: InMemoryStore,
    item: Item,
    *,
    cnr: str = "I",
    pmesii: str = "",
    why: str = "rationale",
) -> str:
    store.put_item(item)
    store.put_enrichment(
        item.id,
        {
            "ccir": None,
            "cnr": cnr,
            "score": 9,
            "bucket": "keep",
            "why": why,
            "pmesii": pmesii,
            "tessoc": None,
        },
    )
    return item.id


def _verdict_ready(item_id: str) -> dict:
    return {"event": "verdict.ready", "item_id": item_id, "cnr": "I"}


async def _fire(store, client, item_id, *, now=None) -> None:
    await handle_verdict_ready(_verdict_ready(item_id), store, client, now=now)


# ===========================================================================
# Task 1 — check_throttle unit tests
# ===========================================================================


def test_check_throttle_60s_boundary_fifth_passes_sixth_throttles(tmp_path):
    """Tight cluster: alerts 1-5 land in the same 60s window; the 6th trips
    the 60-second tier (count_alerts_in_window includes each fired row —
    claim_alert already wrote it before check_throttle runs)."""
    store = InMemoryStore(blob_root=tmp_path)
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)

    for i, sec in enumerate([0, 1, 2, 3, 4]):
        now = base + timedelta(seconds=sec)
        store.claim_alert(f"dedupe-{i}", f"item-{i}", "I", f"alert-{i}", now=now)
        verdict = check_throttle(store, now=now)
        assert verdict.passed, f"alert #{i + 1} should pass (count<={WINDOW_60S_CAP})"

    sixth_now = base + timedelta(seconds=5)
    store.claim_alert("dedupe-5", "item-5", "I", "alert-5", now=sixth_now)
    verdict = check_throttle(store, now=sixth_now)
    assert not verdict.passed
    assert verdict.tier == "60s"


def test_check_throttle_sliding_window_passes_again_after_gap(tmp_path):
    """Advancing the injected clock past 60s from alert 1 lets a further
    alert pass again — sliding, not calendar-bucketed."""
    store = InMemoryStore(blob_root=tmp_path)
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)

    store.claim_alert("dedupe-0", "item-0", "I", "alert-0", now=base)
    assert check_throttle(store, now=base).passed

    later = base + timedelta(seconds=61)
    store.claim_alert("dedupe-1", "item-1", "I", "alert-1", now=later)
    verdict = check_throttle(store, now=later)
    assert verdict.passed


def test_check_throttle_sliding_window_catches_burst_spanning_a_bucket_edge(tmp_path):
    """No fixed-clock burst loophole (SPEC R3 Edge R3/precision): five
    alerts land well inside the trailing 60s window ending at the sixth's
    own timestamp, even though the sixth sits in what a NAIVE calendar
    bucket (floor(t/60)) would treat as a fresh bucket. A buggy
    bucketed implementation would reset the count to 1 for the 6th and
    incorrectly pass it; the sliding window correctly still sees all 5
    prior alerts (10, 20, 30, 40, 50 are all > 65-60=5) plus itself = 6,
    and throttles.
    """
    store = InMemoryStore(blob_root=tmp_path)
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)

    for i, sec in enumerate([10, 20, 30, 40, 50]):
        now = base + timedelta(seconds=sec)
        store.claim_alert(f"dedupe-{i}", f"item-{i}", "I", f"alert-{i}", now=now)
        assert check_throttle(store, now=now).passed

    sixth_now = base + timedelta(seconds=65)  # naive bucket = 1, sliding window = 6
    store.claim_alert("dedupe-5", "item-5", "I", "alert-5", now=sixth_now)
    verdict = check_throttle(store, now=sixth_now)
    assert not verdict.passed
    assert verdict.tier == "60s"


def test_check_throttle_600s_tier_throttles_eleventh_alert_spaced_alerts(tmp_path):
    """11 alerts spaced 30s apart never trip the 60s tier (at most 2 alerts
    ever share a 60s window at that spacing) but the 11th trips the 600s
    tier (count exceeds WINDOW_10MIN_CAP)."""
    store = InMemoryStore(blob_root=tmp_path)
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)

    for i in range(11):
        now = base + timedelta(seconds=30 * i)
        store.claim_alert(f"dedupe-{i}", f"item-{i}", "I", f"alert-{i}", now=now)
        verdict = check_throttle(store, now=now)
        if i < WINDOW_10MIN_CAP:
            assert verdict.passed, f"alert #{i + 1} should pass"
        else:
            assert not verdict.passed
            assert verdict.tier == "600s"


# ===========================================================================
# Task 1 — emitter integration tests (throttle wired into the emit path)
# ===========================================================================


def test_emitter_six_alerts_within_60s_window_produce_five_requests(
    stub_ntfy_server, tmp_path
):
    base_url, handler_cls = stub_ntfy_server
    store = InMemoryStore(blob_root=tmp_path)
    client = NtfyClient(base_url, "secret-token", "cnr-cat-i")
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)

    item_ids = [_seed(store, _make_item(f"vol-{i}")) for i in range(6)]
    for i, item_id in enumerate(item_ids):
        now = base + timedelta(seconds=i)
        asyncio.run(_fire(store, client, item_id, now=now))

    assert len(handler_cls.requests) == WINDOW_60S_CAP


def test_emitter_throttled_alert_marks_suppressed_row_with_pmesii_and_title(
    stub_ntfy_server, tmp_path
):
    base_url, handler_cls = stub_ntfy_server
    store = InMemoryStore(blob_root=tmp_path)
    client = NtfyClient(base_url, "secret-token", "cnr-cat-i")
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)

    item_ids = [
        _seed(store, _make_item(f"sup-{i}", title=f"Title {i}"), pmesii="Military")
        for i in range(6)
    ]
    for i, item_id in enumerate(item_ids):
        now = base + timedelta(seconds=i)
        asyncio.run(_fire(store, client, item_id, now=now))

    rows = store.list_undigested_suppressed()
    assert len(rows) == 1
    row = rows[0]
    assert row["item_id"] == item_ids[5]
    assert row["pmesii"] == "Military"
    assert row["title"] == "Title 5"


def test_emitter_throttled_alert_produces_zero_additional_requests(
    stub_ntfy_server, tmp_path
):
    base_url, handler_cls = stub_ntfy_server
    store = InMemoryStore(blob_root=tmp_path)
    client = NtfyClient(base_url, "secret-token", "cnr-cat-i")
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)

    item_ids = [_seed(store, _make_item(f"zero-{i}")) for i in range(6)]
    for i, item_id in enumerate(item_ids[:5]):
        asyncio.run(_fire(store, client, item_id, now=base + timedelta(seconds=i)))
    assert len(handler_cls.requests) == 5

    sixth_now = base + timedelta(seconds=5)
    asyncio.run(_fire(store, client, item_ids[5], now=sixth_now))

    assert len(handler_cls.requests) == 5  # unchanged — the 6th produced no egress


def test_emitter_suppressed_alert_stops_counting_toward_throttle_window(
    stub_ntfy_server, tmp_path
):
    """Once suppressed, a throttled alert's row is excluded from
    count_alerts_in_window, so it does not itself count against later
    evaluations."""
    base_url, handler_cls = stub_ntfy_server
    store = InMemoryStore(blob_root=tmp_path)
    client = NtfyClient(base_url, "secret-token", "cnr-cat-i")
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)

    item_ids = [_seed(store, _make_item(f"stop-{i}")) for i in range(6)]
    for i, item_id in enumerate(item_ids):
        asyncio.run(_fire(store, client, item_id, now=base + timedelta(seconds=i)))
    assert len(handler_cls.requests) == 5  # the 6th was throttled/suppressed

    # The suppressed 6th row must not itself count toward a fresh window check.
    same_now = base + timedelta(seconds=5)
    verdict = check_throttle(store, now=same_now)
    assert verdict.passed  # only 5 non-suppressed rows remain in the 60s window
