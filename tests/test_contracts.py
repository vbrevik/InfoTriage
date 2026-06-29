#!/usr/bin/env python3
"""test_contracts.py — tests for libs/contracts: Item, events, codec, bus."""
import hashlib
import datetime
import zoneinfo

import pytest
from contracts import Item, ItemIngested, VerdictReady, SabPublished, FeedUnhealthy
from contracts import to_frontmatter, from_frontmatter
from contracts import BusClient, InMemoryBus, RabbitMQBus
from pydantic import ValidationError

TS = datetime.datetime(2026, 6, 27, 10, 0, 0, tzinfo=datetime.timezone.utc)

# ---------------------------------------------------------------------------
# Item tests (R1)
# ---------------------------------------------------------------------------


def test_item_id_deterministic():
    """Same source_type+url+title -> same id (idempotent)."""
    a = Item(source="NRK", source_type="rss", url="https://nrk.no/1", title="Test", ts=TS, lang="no")
    b = Item(source="NRK", source_type="rss", url="https://nrk.no/1", title="Test", ts=TS, lang="no")
    assert a.id == b.id


def test_item_no_url_constructs():
    """url is optional — empty string contributes empty to id hash."""
    item = Item(source="NRK", source_type="rss", url="", title="Test", ts=TS, lang="no")
    expected = hashlib.sha256("rss\x00\x00Test".encode()).hexdigest()
    assert item.id == expected


def test_item_no_url_default_constructs():
    """url has default '' — item constructs without specifying url."""
    item = Item(source="NRK", source_type="rss", title="Test", ts=TS, lang="no")
    expected = hashlib.sha256("rss\x00\x00Test".encode()).hexdigest()
    assert item.id == expected


def test_item_missing_required_field_raises():
    """Omitting title (required) raises ValidationError."""
    with pytest.raises(ValidationError):
        Item(source="NRK", source_type="rss", url="", ts=TS, lang="no")  # missing title


def test_item_missing_source_type_raises():
    """Omitting source_type (required) raises ValidationError."""
    with pytest.raises(ValidationError):
        Item(source="NRK", url="", title="Test", ts=TS, lang="no")  # missing source_type


def test_item_naive_ts_raises():
    """A naive datetime for ts raises ValidationError (AwareDatetime enforcement)."""
    with pytest.raises(ValidationError):
        Item(
            source="NRK",
            source_type="rss",
            url="",
            title="Test",
            ts=datetime.datetime(2026, 6, 27, 10, 0, 0),  # naive — no tzinfo
            lang="no",
        )


def test_item_payload_open_dict():
    """payload is an open dict that accepts arbitrary scoring keys."""
    item = Item(
        source="NRK",
        source_type="rss",
        title="Test",
        ts=TS,
        lang="no",
        payload={"ccir": "PIR-1", "cnr": "I", "score": 8, "bucket": "keep", "why": "CCIR match"},
    )
    assert item.payload["ccir"] == "PIR-1"
    assert item.payload["score"] == 8


# ---------------------------------------------------------------------------
# Event model tests (R2)
# ---------------------------------------------------------------------------


def test_item_ingested_valid():
    """ItemIngested validates a well-formed payload."""
    ev = ItemIngested(event="item.ingested", item_id="abc123", source="NRK", ts=TS)
    assert ev.event == "item.ingested"
    assert ev.item_id == "abc123"


def test_item_ingested_missing_required_raises():
    """ItemIngested raises ValidationError on missing item_id."""
    with pytest.raises(ValidationError):
        ItemIngested(event="item.ingested", source="NRK", ts=TS)  # missing item_id


def test_verdict_ready_valid():
    """VerdictReady validates a well-formed payload."""
    ev = VerdictReady(
        event="verdict.ready",
        item_id="abc123",
        ccir="PIR-1",
        cnr="I",
        score=8,
        bucket="keep",
        why="Matches CCIR",
        ts=TS,
    )
    assert ev.cnr == "I"
    assert ev.bucket == "keep"


def test_verdict_ready_invalid_cnr_raises():
    """VerdictReady rejects an invalid cnr literal."""
    with pytest.raises(ValidationError):
        VerdictReady(
            event="verdict.ready",
            item_id="abc123",
            ccir=None,
            cnr="bogus",
            score=1,
            bucket="keep",
            why="w",
            ts=TS,
        )


def test_verdict_ready_invalid_bucket_raises():
    """VerdictReady rejects an invalid bucket literal."""
    with pytest.raises(ValidationError):
        VerdictReady(
            event="verdict.ready",
            item_id="abc123",
            ccir=None,
            cnr="I",
            score=1,
            bucket="discard",
            why="w",
            ts=TS,
        )


def test_verdict_ready_missing_required_raises():
    """VerdictReady raises ValidationError on missing score."""
    with pytest.raises(ValidationError):
        VerdictReady(
            event="verdict.ready",
            item_id="abc123",
            ccir=None,
            cnr="I",
            bucket="keep",
            why="w",
            ts=TS,
        )  # missing score


def test_sab_published_valid():
    """SabPublished validates when all required fields are present."""
    ev = SabPublished(
        event="sab.published",
        pub_ts=TS,
        snapshot_day="2026-06-27",
        ccir_topics=["PIR-1", "PIR-2"],
        bluf_by_topic={"PIR-1": "Russland angrep [1] infrastruktur."},
        item_refs=[{"item_id": "abc", "n": 1, "title": "Test", "source": "NRK", "url": "https://nrk.no/1", "ts": TS}],
        total_keep=5,
        since_ts=None,
    )
    assert ev.total_keep == 5
    assert ev.since_ts is None


def test_sab_published_missing_required_raises():
    """SabPublished raises ValidationError on missing total_keep."""
    with pytest.raises(ValidationError):
        SabPublished(
            event="sab.published",
            pub_ts=TS,
            snapshot_day="2026-06-27",
            ccir_topics=[],
            bluf_by_topic={},
            item_refs=[],
            since_ts=None,
        )  # missing total_keep


def test_feed_unhealthy_valid():
    """FeedUnhealthy validates a well-formed payload."""
    ev = FeedUnhealthy(
        event="feed.unhealthy",
        feed_url="https://nrk.no/feed",
        feed_name="NRK Nyheter",
        reason="HTTP 503 — server unavailable",
        last_ok_at=None,
        ts=TS,
    )
    assert ev.feed_name == "NRK Nyheter"


def test_feed_unhealthy_reason_max_length_ok():
    """FeedUnhealthy accepts reason of exactly 120 chars."""
    reason_120 = "x" * 120
    ev = FeedUnhealthy(
        event="feed.unhealthy",
        feed_url="u",
        feed_name="n",
        reason=reason_120,
        last_ok_at=None,
        ts=TS,
    )
    assert len(ev.reason) == 120


def test_feed_unhealthy_reason_too_long_raises():
    """FeedUnhealthy rejects reason longer than 120 characters."""
    with pytest.raises(ValidationError):
        FeedUnhealthy(
            event="feed.unhealthy",
            feed_url="u",
            feed_name="n",
            reason="x" * 121,
            last_ok_at=None,
            ts=TS,
        )


def test_feed_unhealthy_missing_required_raises():
    """FeedUnhealthy raises ValidationError on missing feed_url."""
    with pytest.raises(ValidationError):
        FeedUnhealthy(
            event="feed.unhealthy",
            feed_name="NRK",
            reason="timeout",
            last_ok_at=None,
            ts=TS,
        )  # missing feed_url


# ---------------------------------------------------------------------------
# Codec tests (R3)
# ---------------------------------------------------------------------------


def test_codec_round_trip():
    """Full round-trip: nested dict/list, None, Norwegian unicode, tz-aware datetime, [N] markers."""
    oslo = zoneinfo.ZoneInfo("Europe/Oslo")
    payload = {
        "ts": datetime.datetime(2026, 6, 27, 10, 30, 45, tzinfo=oslo),
        "bluf": "Russland angrep [1] kritisk infrastruktur [2].",
        "nested": {"ccir": "PIR-1", "cnr": "I"},
        "refs": ["[1] NRK Nyheter", "[2] BBC News"],
        "nothing": None,
        "name": "Åse Æriksen Ø-test",
    }
    text = to_frontmatter(payload)
    assert text.startswith("---\n")
    assert text.endswith("---\n")
    result = from_frontmatter(text)

    assert result["ts"] == payload["ts"]       # datetime VALUE preserved (UTC offset matches)
    assert result["bluf"] == payload["bluf"]   # [N] citation markers preserved
    assert result["nested"] == payload["nested"]
    assert result["refs"] == payload["refs"]
    assert result["nothing"] is None
    assert result["name"] == payload["name"]   # Norwegian unicode


def test_codec_from_frontmatter_no_delimiters_raises():
    """from_frontmatter raises ValueError when text has no frontmatter delimiters."""
    with pytest.raises(ValueError):
        from_frontmatter("no frontmatter here")


def test_codec_empty_frontmatter_returns_empty_dict():
    """from_frontmatter with empty YAML block between delimiters returns {}."""
    text = "---\n---\n"
    result = from_frontmatter(text)
    assert result == {}


# ---------------------------------------------------------------------------
# Bus tests (R4)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bus_dedup():
    """Re-publishing same item_id is a no-op (second publish not delivered)."""
    bus = InMemoryBus()
    await bus.publish("item.ingested", item_id="abc123", payload={"n": 1})
    await bus.publish("item.ingested", item_id="abc123", payload={"n": 2})  # ignored
    msgs = await bus.subscribe("item.ingested")
    assert len(msgs) == 1
    assert msgs[0]["n"] == 1


@pytest.mark.asyncio
async def test_bus_fifo():
    """Messages delivered in publish order (FIFO per routing_key)."""
    bus = InMemoryBus()
    await bus.publish("item.ingested", item_id="id1", payload={"n": 1})
    await bus.publish("item.ingested", item_id="id2", payload={"n": 2})
    await bus.publish("item.ingested", item_id="id3", payload={"n": 3})
    msgs = await bus.subscribe("item.ingested")
    assert [m["n"] for m in msgs] == [1, 2, 3]


@pytest.mark.asyncio
async def test_bus_empty_subscribe_no_op():
    """Subscribe on empty/unused queue returns [] (non-blocking no-op)."""
    bus = InMemoryBus()
    assert await bus.subscribe("item.ingested") == []
    assert await bus.subscribe("verdict.ready") == []


@pytest.mark.asyncio
async def test_bus_cross_routing_key_isolation():
    """Messages on different routing keys don't mix."""
    bus = InMemoryBus()
    await bus.publish("item.ingested", item_id="id1", payload={"event": "ingested"})
    await bus.publish("verdict.ready", item_id="id2", payload={"event": "verdict"})
    assert (await bus.subscribe("item.ingested"))[0]["event"] == "ingested"
    assert (await bus.subscribe("verdict.ready"))[0]["event"] == "verdict"


def test_bus_satisfies_protocol():
    """InMemoryBus structurally satisfies BusClient Protocol."""
    assert isinstance(InMemoryBus(), BusClient)


def test_rabbitmq_bus_protocol():
    """RabbitMQBus structurally satisfies BusClient Protocol (ADR-007)."""
    assert isinstance(RabbitMQBus(), BusClient)


# ---------------------------------------------------------------------------
# Phase 1 code-review regression tests (WR-01, WR-02)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bus_same_item_id_across_routing_keys_not_deduped():
    """Same item_id on different routing keys must both deliver (WR-01).

    The event lifecycle reuses Item.id across item.ingested -> verdict.ready,
    so dedup must be per (routing_key, item_id), not a global item_id set.
    """
    bus = InMemoryBus()
    await bus.publish("item.ingested", item_id="id1", payload={"event": "ingested"})
    await bus.publish("verdict.ready", item_id="id1", payload={"event": "verdict"})  # same id, different key
    assert (await bus.subscribe("item.ingested"))[0]["event"] == "ingested"
    assert (await bus.subscribe("verdict.ready"))[0]["event"] == "verdict"


def test_codec_value_containing_triple_dash_round_trips():
    """A frontmatter VALUE containing '---' must not corrupt the round-trip (WR-02)."""
    payload = {"note": "before---after", "title": "a - b --- c"}
    text = to_frontmatter(payload)
    result = from_frontmatter(text)
    assert result["note"] == "before---after"
    assert result["title"] == "a - b --- c"
