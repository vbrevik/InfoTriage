"""tests/test_prefilter.py — Phase 9 CCIR pre-filter integration tests."""

from __future__ import annotations

import asyncio
import datetime
import os
from typing import Callable

import pytest

from contracts import Item
from store import InMemoryStore
from worker import process_item


VEC = [1.0, 0.0]


class FakeBus:
    def __init__(self) -> None:
        self.published: list[dict] = []

    async def publish(self, routing_key: str, item_id: str, payload: dict) -> None:
        self.published.append(
            {"routing_key": routing_key, "item_id": item_id, "payload": payload}
        )


@pytest.fixture
def store(tmp_path):
    return InMemoryStore(blob_root=tmp_path / "blobs")


@pytest.fixture
def bus():
    return FakeBus()


def _item(title: str = "Test Item", summary: str = "A summary") -> Item:
    return Item(
        source="Test Source",
        source_type="rss",
        url=f"https://example.com/{title.lower().replace(' ', '-')}",
        title=title,
        ts=datetime.datetime(2026, 6, 30, tzinfo=datetime.timezone.utc),
        lang="en",
        summary=summary,
    )


def _fake_score(fields: dict) -> Callable[[dict], dict]:
    def _score(it: dict) -> dict:
        return {**it, **fields}

    return _score


def test_prefilter_skip_calls_no_llm(store, bus):
    """Low CCIR similarity causes pre-filter skip; LLM scorer is not called."""
    item = _item()
    store.put_item(item)
    # Orthogonal to the item embedding -> cosine 0.0 < default threshold 0.50
    store.put_ccir_vector("PIR-2", [0.0, 1.0])

    score_calls = []

    def score(it):
        score_calls.append(it)
        return {
            **it,
            "ccir": "PIR-2",
            "cnr": "II",
            "score": 7,
            "bucket": "keep",
            "why": "should not run",
            "pmesii": "Military",
            "tessoc": "Espionage",
        }

    asyncio.run(process_item(item.id, store, bus, embed=lambda text: VEC, score=score))

    assert score_calls == []
    enrichment = store.get_enrichment(item.id)
    assert enrichment["bucket"] == "skip"
    assert "pre-filter" in enrichment["why"]
    assert len(bus.published) == 1
    assert bus.published[0]["payload"]["bucket"] == "skip"
    assert len(store._audit) == 1
    assert store._audit[0]["op"] == "pre_filter_skip"
    assert store._audit[0]["details"]["best_ccir"] == "PIR-2"


def test_prefilter_pass_calls_llm(store, bus):
    """High CCIR similarity passes the gate and runs LLM scoring."""
    item = _item()
    store.put_item(item)
    store.put_ccir_vector("PIR-2", VEC)

    score_calls = []

    def score(it):
        score_calls.append(it)
        return {
            **it,
            "ccir": "PIR-2",
            "cnr": "II",
            "score": 7,
            "bucket": "keep",
            "why": "llm scored",
            "pmesii": "Military",
            "tessoc": "Espionage",
        }

    asyncio.run(process_item(item.id, store, bus, embed=lambda text: VEC, score=score))

    assert len(score_calls) == 1
    enrichment = store.get_enrichment(item.id)
    assert enrichment["bucket"] == "keep"
    assert enrichment["why"] == "llm scored"
    assert len(store._audit) == 0


def test_prefilter_no_ccir_vectors_falls_through(store, bus):
    """Empty CCIR table falls through to LLM scoring."""
    item = _item()
    store.put_item(item)

    score_calls = []

    def score(it):
        score_calls.append(it)
        return {
            **it,
            "ccir": "PIR-1",
            "cnr": "II",
            "score": 6,
            "bucket": "maybe",
            "why": "llm",
            "pmesii": "Military",
            "tessoc": "Espionage",
        }

    asyncio.run(process_item(item.id, store, bus, embed=lambda text: VEC, score=score))

    assert len(score_calls) == 1


def test_prefilter_db_failure_falls_through_to_llm(store, bus):
    """find_similar_ccir raising an exception falls through to LLM scoring."""
    item = _item()
    store.put_item(item)

    def boom(*args, **kwargs):
        raise RuntimeError("DB down")

    score_calls = []

    def score(it):
        score_calls.append(it)
        return {
            **it,
            "ccir": "PIR-1",
            "cnr": "II",
            "score": 6,
            "bucket": "maybe",
            "why": "llm",
            "pmesii": "Military",
            "tessoc": "Espionage",
        }

    store.find_similar_ccir = boom
    asyncio.run(process_item(item.id, store, bus, embed=lambda text: VEC, score=score))

    assert len(score_calls) == 1


def test_prefilter_threshold_configurable(store, bus):
    """INFOTRIAGE_PREFILTER_THRESHOLD changes the gate."""
    item = _item()
    store.put_item(item)
    # vector identical to CCIR -> similarity 1.0
    store.put_ccir_vector("PIR-2", VEC)

    score_calls = []

    def score(it):
        score_calls.append(it)
        return {
            **it,
            "ccir": "PIR-2",
            "cnr": "II",
            "score": 7,
            "bucket": "keep",
            "why": "llm",
            "pmesii": "Military",
            "tessoc": "Espionage",
        }

    # threshold below the observed similarity -> item passes the gate
    env_orig = os.environ.get("INFOTRIAGE_PREFILTER_THRESHOLD")
    try:
        os.environ["INFOTRIAGE_PREFILTER_THRESHOLD"] = "0.9"
        asyncio.run(
            process_item(item.id, store, bus, embed=lambda text: VEC, score=score)
        )
        assert len(score_calls) == 1
    finally:
        if env_orig is not None:
            os.environ["INFOTRIAGE_PREFILTER_THRESHOLD"] = env_orig
        else:
            os.environ.pop("INFOTRIAGE_PREFILTER_THRESHOLD", None)


def test_prefilter_threshold_above_similarity_skips(store, bus):
    """A threshold above the observed similarity causes a skip."""
    item = _item()
    store.put_item(item)
    # similarity to the CCIR vector will be exactly 0.5
    store.put_ccir_vector("PIR-2", [1.0, 0.0])

    score_calls = []

    def score(it):
        score_calls.append(it)
        return {
            **it,
            "ccir": "PIR-2",
            "cnr": "II",
            "score": 7,
            "bucket": "keep",
            "why": "llm",
            "pmesii": "Military",
            "tessoc": "Espionage",
        }

    env_orig = os.environ.get("INFOTRIAGE_PREFILTER_THRESHOLD")
    try:
        os.environ["INFOTRIAGE_PREFILTER_THRESHOLD"] = "0.9"
        asyncio.run(
            process_item(
                item.id, store, bus, embed=lambda text: [0.0, 1.0], score=score
            )
        )
        assert len(score_calls) == 0
    finally:
        if env_orig is not None:
            os.environ["INFOTRIAGE_PREFILTER_THRESHOLD"] = env_orig
        else:
            os.environ.pop("INFOTRIAGE_PREFILTER_THRESHOLD", None)


def test_prefilter_entity_resolution_still_runs(store, bus):
    """Pre-filter skip path still runs entity resolution."""
    item = _item("NATO Summit")
    store.put_item(item)
    store.put_ccir_vector("PIR-3", VEC)

    def fake_ner_chat(messages, max_tokens=800):
        return '[{"name": "NATO", "type": "ORG"}]'

    asyncio.run(
        process_item(
            item.id,
            store,
            bus,
            embed=lambda text: VEC,
            score=lambda it: it,
            ner_chat=fake_ner_chat,
        )
    )

    links = store.get_entity_links(item.id)
    assert any(l["name"] == "NATO" for l in links)
