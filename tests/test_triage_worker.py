#!/usr/bin/env python3
"""tests/test_triage_worker.py — behavior tests for apps/triage/worker.py (R2, R3, R4, R5).

Drives the worker through its testable async core, process_item(item_id, store, bus,
embed=<fake>, score=<fake>), using InMemoryStore (no live Postgres) and a minimal fake
async bus (no live RabbitMQ). embed/score are injected callables so no live oMLX/LLM
call is ever made.

Tests are plain (non-async) pytest functions that drive the async core via
asyncio.run(...) — matches the existing codebase convention in
tests/test_bus_consume.py (no pytest-asyncio marker dependency).
"""
import asyncio
import datetime
import json

import pytest

from contracts import Item
from store import InMemoryStore
from worker import _clean_for_embedding, on_message, process_item

# ---------------------------------------------------------------------------
# Fixtures + helpers
# ---------------------------------------------------------------------------

VEC_A = [1.0, 0.0]  # orthogonal to VEC_B (cosine 0.0) — never a false dedup match
VEC_B = [0.0, 1.0]


def _fake_ner_chat(messages, max_tokens=800):
    """Fake qwen36 NER: return known entities present in the prompt as JSON."""
    import json as _json

    content = messages[0]["content"]
    known = [("NATO", "ORG"), ("Oslo", "GPE")]
    return _json.dumps([{"name": n, "type": t} for n, t in known if n in content])


class FakeBus:
    """Minimal async bus fake — records every publish() call for assertions."""

    def __init__(self) -> None:
        self.published: list[dict] = []

    async def publish(self, routing_key: str, item_id: str, payload: dict) -> None:
        self.published.append(
            {"routing_key": routing_key, "item_id": item_id, "payload": payload}
        )


class FakeMessage:
    """Minimal aio_pika.IncomingMessage fake — mirrors what RabbitMQBus.publish()
    actually produces: item_id lives in AMQP headers, body is only the
    {source, source_type, ts} payload (no item_id key in the body)."""

    def __init__(self, item_id: str, payload: dict) -> None:
        self.headers = {"routing_key": "item.ingested", "item_id": item_id}
        self.body = json.dumps(payload).encode()

    def process(self):
        return self._Ack()

    class _Ack:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False


def _ts() -> datetime.datetime:
    return datetime.datetime(2026, 6, 30, tzinfo=datetime.timezone.utc)


def _item(title: str, summary: str = "A summary") -> Item:
    return Item(
        source="Test Source",
        source_type="rss",
        url=f"https://example.com/{title.lower().replace(' ', '-')}",
        title=title,
        ts=_ts(),
        lang="en",
        summary=summary,
    )


def _fake_score(fields: dict):
    """Return a score() callable that ignores its input and returns fields merged in."""

    def _score(it: dict) -> dict:
        return {**it, **fields}

    return _score


@pytest.fixture
def store(tmp_path):
    return InMemoryStore(blob_root=tmp_path / "blobs")


@pytest.fixture
def bus():
    return FakeBus()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_missing_article_acks(store, bus):
    """process_item for an absent item_id logs a warning and returns normally — no crash."""
    asyncio.run(
        process_item(
            "missing-item-id",
            store,
            bus,
            embed=lambda text: VEC_A,
            score=_fake_score({}),
        )
    )
    assert store.get_enrichment("missing-item-id") is None
    assert bus.published == []


def test_enrichment_failure_nacks(store, bus):
    """A store whose put_enrichment raises causes process_item to propagate — no publish."""
    item = _item("Failing Item")
    store.put_item(item)

    def _raise(item_id, fields):
        raise RuntimeError("simulated put_enrichment failure")

    store.put_enrichment = _raise

    score = _fake_score(
        {
            "ccir": "PIR-1",
            "cnr": "II",
            "score": 6,
            "bucket": "maybe",
            "why": "test",
            "pmesii": "Military",
            "tessoc": "Terror",
        }
    )
    with pytest.raises(RuntimeError):
        asyncio.run(
            process_item(item.id, store, bus, embed=lambda text: VEC_A, score=score)
        )
    assert bus.published == []


def test_no_verdict_on_enrichment_failure(store, bus):
    """Same failure scenario — assert zero verdict.ready publishes (R5 prohibition)."""
    item = _item("Failing Item 2")
    store.put_item(item)

    def _raise(item_id, fields):
        raise RuntimeError("simulated put_enrichment failure")

    store.put_enrichment = _raise

    score = _fake_score(
        {
            "ccir": "PIR-1",
            "cnr": "II",
            "score": 6,
            "bucket": "maybe",
            "why": "test",
            "pmesii": "Military",
            "tessoc": "Terror",
        }
    )
    with pytest.raises(RuntimeError):
        asyncio.run(
            process_item(item.id, store, bus, embed=lambda text: VEC_A, score=score)
        )
    assert len(bus.published) == 0


def test_malformed_llm_fallback(store, bus):
    """Fallback dict from triage_score (malformed LLM output) writes enrichment + publishes."""
    item = _item("Malformed Item")
    store.put_item(item)

    fallback = {
        "ccir": "none",
        "cnr": "none",
        "pmesii": "none",
        "tessoc": "none",
        "score": 0,
        "bucket": "skip",
        "why": "uleselig modell-svar",
    }
    asyncio.run(
        process_item(
            item.id, store, bus, embed=lambda text: VEC_A, score=_fake_score(fallback)
        )
    )

    enrichment = store.get_enrichment(item.id)
    assert enrichment is not None
    assert enrichment["bucket"] == "skip"
    assert len(bus.published) == 1
    payload = bus.published[0]["payload"]
    assert payload["cnr"] == "Routine"
    assert payload["bucket"] == "skip"


def test_score_clamped(store, bus):
    """score=42 clamps to 10; score=-3 clamps to 0 — both in enrichment row and VerdictReady."""
    item_high = _item("High Score Item")
    store.put_item(item_high)
    score_high = _fake_score(
        {
            "ccir": "PIR-1",
            "cnr": "II",
            "score": 42,
            "bucket": "maybe",
            "why": "test",
            "pmesii": "Military",
            "tessoc": "Terror",
        }
    )
    asyncio.run(
        process_item(
            item_high.id, store, bus, embed=lambda text: VEC_A, score=score_high
        )
    )
    enrichment_high = store.get_enrichment(item_high.id)
    assert enrichment_high["score"] == 10
    assert bus.published[0]["payload"]["score"] == 10

    item_low = _item("Negative Score Item")
    store.put_item(item_low)
    score_low = _fake_score(
        {
            "ccir": "PIR-1",
            "cnr": "II",
            "score": -3,
            "bucket": "maybe",
            "why": "test",
            "pmesii": "Military",
            "tessoc": "Terror",
        }
    )
    asyncio.run(
        process_item(item_low.id, store, bus, embed=lambda text: VEC_B, score=score_low)
    )
    enrichment_low = store.get_enrichment(item_low.id)
    assert enrichment_low["score"] == 0
    assert bus.published[1]["payload"]["score"] == 0


def test_clean_for_embedding_strips_html_and_urls():
    """Newsletter/tracking chrome (HTML tags, beehiiv/medium URLs) must not
    dominate the embed text, or unrelated newsletter emails collapse into
    false near-duplicates on shared boilerplate (2026-07-24 regression:
    three distinct Kimi K3 articles chained as 'duplicate of' an unrelated
    'Claude Code Skills' article, purely via shared beehiiv image-URL text)."""
    raw = (
        "View image: (https://media.beehiiv.com/cdn-cgi/image/fit=scale-down"
        "/uploads/asset/file/abc123.png?t=1782957943) <b>Caption</b> text here"
    )
    cleaned = _clean_for_embedding(raw)
    assert "beehiiv.com" not in cleaned
    assert "<b>" not in cleaned and "</b>" not in cleaned
    assert "Caption text here" in cleaned


def test_clean_for_embedding_differentiates_previously_colliding_summaries():
    """Two unrelated articles whose raw summaries share only boilerplate URLs
    must no longer be textually identical after cleaning."""
    kimi_summary = (
        "View image: (https://media.beehiiv.com/cdn-cgi/image/fit=scale-down"
        "/uploads/asset/file/kimi.png?t=1) Kimi K3 tops open-source benchmarks"
    )
    skills_summary = (
        "View image: (https://media.beehiiv.com/cdn-cgi/image/fit=scale-down"
        "/uploads/asset/file/skills.png?t=1) Claude Code Skills explained"
    )
    assert _clean_for_embedding(kimi_summary) != _clean_for_embedding(skills_summary)


def test_dedup_threshold_defaults_to_090(store, bus, monkeypatch):
    """process_item must call find_near_duplicate with threshold=0.90 by default.

    2026-07-24: even after _clean_for_embedding, two DISTINCT short
    tech-newsletter headlines (a real Kimi K3 article vs an unrelated AI
    article) measured 0.8447 cosine similarity through the live mE5-large
    embedder — just above the old 0.84 threshold, so they still false-dedup'd
    pre-LLM. Bumped to 0.90 as an interim fix (real recalibration is backlog
    Phase 999.2). INFOTRIAGE_DEDUP_THRESHOLD overrides for tuning."""
    monkeypatch.delenv("INFOTRIAGE_DEDUP_THRESHOLD", raising=False)
    captured = {}
    orig = store.find_near_duplicate

    def spy(vector, **kwargs):
        captured.update(kwargs)
        return orig(vector, **kwargs)

    store.find_near_duplicate = spy
    item = _item("Threshold check")
    store.put_item(item)

    def score(it):
        return {
            **it,
            "ccir": "none",
            "cnr": "none",
            "score": 0,
            "bucket": "skip",
            "why": "stub",
            "pmesii": "none",
            "tessoc": "none",
        }

    asyncio.run(
        process_item(item.id, store, bus, embed=lambda text: VEC_A, score=score)
    )
    assert captured.get("threshold") == 0.90


def test_dedup_skip(store, bus):
    """A near-duplicate embedding skips the LLM, marks bucket=skip, why mentions 'duplicate'."""
    store.put_embedding("existing-item", VEC_A)
    item = _item("Duplicate Candidate")
    store.put_item(item)

    score_calls = []

    def score(it):
        score_calls.append(it)
        return {
            **it,
            "ccir": "PIR-1",
            "cnr": "II",
            "score": 7,
            "bucket": "maybe",
            "why": "must not be used",
            "pmesii": "Military",
            "tessoc": "Terror",
        }

    asyncio.run(
        process_item(item.id, store, bus, embed=lambda text: VEC_A, score=score)
    )

    enrichment = store.get_enrichment(item.id)
    assert enrichment is not None
    assert enrichment["bucket"] == "skip"
    assert "duplicate" in enrichment["why"]
    assert score_calls == [], "score callable must NOT be called on a dedup hit"
    assert (
        store._embeddings.get(item.id) == VEC_A
    ), "embedding must still be written for a duplicate"
    assert len(bus.published) == 1
    assert bus.published[0]["payload"]["bucket"] == "skip"


def test_dedup_distinct(store, bus):
    """Two distinct (orthogonal) embeddings → both items call score() and both get scored."""
    item_a = _item("Distinct Item A")
    item_b = _item("Distinct Item B")
    store.put_item(item_a)
    store.put_item(item_b)

    score_calls = []

    def score(it):
        score_calls.append(it)
        return {
            **it,
            "ccir": "PIR-1",
            "cnr": "II",
            "score": 6,
            "bucket": "maybe",
            "why": "distinct",
            "pmesii": "Military",
            "tessoc": "Terror",
        }

    asyncio.run(
        process_item(item_a.id, store, bus, embed=lambda text: VEC_A, score=score)
    )
    asyncio.run(
        process_item(item_b.id, store, bus, embed=lambda text: VEC_B, score=score)
    )

    assert len(score_calls) == 2, "both distinct items must reach score()"
    enrichment_a = store.get_enrichment(item_a.id)
    enrichment_b = store.get_enrichment(item_b.id)
    assert enrichment_a["bucket"] == "maybe"
    assert enrichment_b["bucket"] == "maybe"


def test_entity_resolution_links_entities(store, bus):
    """Phase 8: process_item extracts entities and links them to the item."""
    item = _item("NATO Summit in Oslo")
    store.put_item(item)
    score = _fake_score(
        {
            "ccir": "PIR-3",
            "cnr": "II",
            "score": 7,
            "bucket": "maybe",
            "why": "NATO toppmote",
            "pmesii": "Political",
            "tessoc": "Subversion",
        }
    )

    def fake_embed(text):
        # Distinct vectors so NATO and Oslo do not collapse via similarity.
        if "nato" in text.lower():
            return VEC_A
        if "oslo" in text.lower():
            return VEC_B
        return [0.5, 0.5]

    asyncio.run(
        process_item(
            item.id, store, bus, embed=fake_embed, score=score, ner_chat=_fake_ner_chat
        )
    )

    links = store.get_entity_links(item.id)
    names = {l["name"] for l in links}
    assert "NATO" in names
    assert "Oslo" in names


def test_verdict_ready_fields(store, bus):
    """A normal scored item produces a verdict.ready payload with all required fields."""
    item = _item("Normal Scored Item")
    store.put_item(item)
    score = _fake_score(
        {
            "ccir": "PIR-3",
            "cnr": "II",
            "score": 7,
            "bucket": "maybe",
            "why": "NATO toppmote",
            "pmesii": "Political",
            "tessoc": "Subversion",
        }
    )
    asyncio.run(
        process_item(item.id, store, bus, embed=lambda text: VEC_A, score=score)
    )

    assert len(bus.published) == 1
    record = bus.published[0]
    assert record["routing_key"] == "verdict.ready"
    payload = record["payload"]
    assert payload["item_id"] == item.id
    assert "ccir" in payload
    assert payload["cnr"] in {"I", "II", "Routine"}
    assert 0 <= payload["score"] <= 10
    assert payload["bucket"] in {"keep", "maybe", "skip"}
    assert "why" in payload
    assert "ts" in payload


def test_entity_resolution_failure_does_not_block_verdict(store, bus):
    """Entity resolution raises → verdict.ready still published (R5 prohibition)."""
    item = _item("Entity Error Item")
    store.put_item(item)
    score = _fake_score(
        {
            "ccir": "PIR-1",
            "cnr": "II",
            "score": 6,
            "bucket": "maybe",
            "why": "test",
            "pmesii": "Political",
            "tessoc": "Subversion",
        }
    )

    def boom_ner(messages, max_tokens=800):
        raise RuntimeError("NER model offline")

    asyncio.run(
        process_item(
            item.id,
            store,
            bus,
            embed=lambda text: VEC_A,
            score=score,
            ner_chat=boom_ner,
        )
    )

    assert len(bus.published) == 1
    assert bus.published[0]["routing_key"] == "verdict.ready"
    assert bus.published[0]["payload"]["item_id"] == item.id


def test_entity_resolution_timeout_does_not_block_verdict(store, bus):
    """Entity resolution hangs → asyncio.wait_for timeouts → verdict.ready still published.

    We replace resolve_entities_async with a coroutine that blocks on an
    asyncio.Event() that never resolves. Because this blocks at the event-
    loop level (not a thread pool), asyncio.wait_for can cancel it and
    the timeout fires immediately.
    """
    import asyncio
    import os
    from unittest.mock import patch

    item = _item("Timeout Item")
    store.put_item(item)
    score = _fake_score(
        {
            "ccir": "PIR-1",
            "cnr": "II",
            "score": 6,
            "bucket": "maybe",
            "why": "test",
            "pmesii": "Political",
            "tessoc": "Subversion",
        }
    )

    _never = asyncio.Event()  # never set → blocks forever

    env_orig = os.environ.get("INFOTRIAGE_ENTITY_NER_TIMEOUT")
    try:
        os.environ["INFOTRIAGE_ENTITY_NER_TIMEOUT"] = "0.01"
        # The timeout must be short so the test finishes fast.
        import time

        async def _hang(*args, **kwargs):
            await _never.wait()

        t0 = time.monotonic()
        with patch("worker.resolve_entities_async", _hang):
            asyncio.run(
                process_item(
                    item.id,
                    store,
                    bus,
                    embed=lambda text: VEC_A,
                    score=score,
                )
            )
        elapsed = time.monotonic() - t0
        # The timeout should fire quickly (~0.01s) not block for minutes
        assert elapsed < 2, f"timeout did not fire; took {elapsed:.1f}s"
    finally:
        if env_orig is not None:
            os.environ["INFOTRIAGE_ENTITY_NER_TIMEOUT"] = env_orig
        else:
            os.environ.pop("INFOTRIAGE_ENTITY_NER_TIMEOUT", None)

    assert len(bus.published) == 1
    assert bus.published[0]["routing_key"] == "verdict.ready"
    assert bus.published[0]["payload"]["item_id"] == item.id


def test_on_message_reads_item_id_from_headers_not_body(store, bus, monkeypatch):
    """on_message must extract item_id from message.headers — RabbitMQBus.publish()
    puts item_id only in AMQP headers, never in the JSON body. A regression here
    means every real item.ingested message dead-letters with KeyError('item_id')."""
    item = _item("Header Routed Item")
    store.put_item(item)

    calls = []

    async def fake_process_item(item_id, s, b):
        calls.append(item_id)

    monkeypatch.setattr("worker.process_item", fake_process_item)

    message = FakeMessage(
        item.id,
        {
            "source": item.source,
            "source_type": item.source_type,
            "ts": item.ts.isoformat(),
        },
    )
    assert "item_id" not in json.loads(
        message.body.decode()
    ), "test fixture must match publish()'s real wire format: no item_id in body"

    asyncio.run(on_message(message, store, bus))

    assert calls == [item.id]
