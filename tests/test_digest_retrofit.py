#!/usr/bin/env python3
"""tests/test_digest_retrofit.py — unit tests for the digest.py store retrofit (R6).

Exercises the verdict→Item mapping and store-backed persistence seam against an
InMemoryStore (no live DB required). Mirrors the InMemoryStore test pattern from
test_store_contract.py.

Verdict dict shape (from fetch_window + score_item):
    title, source, summary, ccir, cnr, pmesii, tessoc, score, why, bucket
    id (fever item id), url, t (epoch seconds)
"""
import datetime

import pytest

from digest import map_verdict_to_item  # resolved via apps/triage on pythonpath
from store import InMemoryStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_verdict(
    *,
    title="NATO utvider øst",
    source="NRK Nyheter",
    url="https://nrk.no/1",
    t=1_700_000_000,
    summary="NATO holder ekstraordinært møte.",
    ccir="PIR-3",
    cnr="II",
    pmesii=None,
    tessoc=None,
    score=8,
    why="Svarer direkte på PIR-3 NATO-beredskap",
    bucket="read",
    fever_id=42,
) -> dict:
    """Build a representative verdict dict mirroring fetch_window output."""
    return {
        "title": title,
        "source": source,
        "url": url,
        "t": t,
        "summary": summary,
        "ccir": ccir,
        "cnr": cnr,
        "pmesii": pmesii or {"Political": 4, "Military": 3},
        "tessoc": tessoc or ["alliance", "security"],
        "score": score,
        "why": why,
        "bucket": bucket,
        "id": fever_id,
    }


# ---------------------------------------------------------------------------
# Mapping correctness
# ---------------------------------------------------------------------------

class TestMapVerdictToItem:
    """Verify verdict→Item field mapping without touching a store."""

    def test_core_fields_mapped_correctly(self):
        v = _make_verdict()
        item = map_verdict_to_item(v)

        assert item.source == "NRK Nyheter"
        assert item.source_type == "rss"
        assert item.url == "https://nrk.no/1"
        assert item.title == "NATO utvider øst"
        assert item.lang == "no"
        assert item.summary == "NATO holder ekstraordinært møte."
        assert item.body_ref is None

    def test_timestamp_is_utc_aware(self):
        v = _make_verdict(t=1_700_000_000)
        item = map_verdict_to_item(v)

        expected = datetime.datetime.fromtimestamp(
            1_700_000_000, tz=datetime.timezone.utc
        )
        assert item.ts == expected
        assert item.ts.tzinfo is not None

    def test_payload_carries_score_fields(self):
        v = _make_verdict(
            ccir="PIR-1",
            cnr="I",
            score=9,
            why="Direkte operasjonell relevans",
            bucket="read",
        )
        item = map_verdict_to_item(v)

        assert item.payload["ccir"] == "PIR-1"
        assert item.payload["cnr"] == "I"
        assert item.payload["score"] == 9
        assert item.payload["why"] == "Direkte operasjonell relevans"
        assert item.payload["bucket"] == "read"

    def test_payload_carries_pmesii_tessoc(self):
        v = _make_verdict(
            pmesii={"Political": 5, "Military": 4},
            tessoc=["war", "politics"],
        )
        item = map_verdict_to_item(v)

        assert item.payload["pmesii"] == {"Political": 5, "Military": 4}
        assert item.payload["tessoc"] == ["war", "politics"]

    def test_payload_carries_fever_id(self):
        v = _make_verdict(fever_id=99)
        item = map_verdict_to_item(v)

        assert item.payload["fever_id"] == 99

    def test_id_is_sha256_of_source_type_url_title(self):
        import hashlib
        v = _make_verdict(url="https://nrk.no/1", title="NATO utvider øst")
        item = map_verdict_to_item(v)

        raw = "rss\x00https://nrk.no/1\x00NATO utvider øst"
        expected_id = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        assert item.id == expected_id

    def test_missing_optional_fields_default_gracefully(self):
        v = {
            "title": "Minimal item",
            "source": "Test Feed",
            "t": 0,
        }
        item = map_verdict_to_item(v)

        assert item.url == ""
        assert item.summary is None
        assert item.payload["ccir"] is None
        assert item.payload["score"] is None
        assert item.payload["fever_id"] is None


# ---------------------------------------------------------------------------
# Store-backed persistence (InMemoryStore as test double — no DB)
# ---------------------------------------------------------------------------

class TestStorePersistence:
    """Verify verdicts flow through the store and are retrievable (R6)."""

    def test_persisted_item_retrievable_via_get_item(self, tmp_path):
        v = _make_verdict()
        item = map_verdict_to_item(v)

        with InMemoryStore(blob_root=tmp_path / "blobs") as store:
            store.init_schema()
            store.put_item(item)
            result = store.get_item(item.id)

        assert result is not None
        assert result.id == item.id
        assert result.title == "NATO utvider øst"
        assert result.source == "NRK Nyheter"

    def test_payload_preserved_after_roundtrip(self, tmp_path):
        v = _make_verdict(ccir="PIR-1", score=9, cnr="I")
        item = map_verdict_to_item(v)

        with InMemoryStore(blob_root=tmp_path / "blobs") as store:
            store.put_item(item)
            result = store.get_item(item.id)

        assert result.payload["ccir"] == "PIR-1"
        assert result.payload["score"] == 9
        assert result.payload["cnr"] == "I"
        assert result.payload["fever_id"] == 42

    def test_multiple_verdicts_all_retrievable(self, tmp_path):
        verdicts = [
            _make_verdict(title=f"Item {i}", url=f"https://nrk.no/{i}", fever_id=i)
            for i in range(3)
        ]
        items = [map_verdict_to_item(v) for v in verdicts]

        with InMemoryStore(blob_root=tmp_path / "blobs") as store:
            store.init_schema()
            for item in items:
                store.put_item(item)
            results = [store.get_item(item.id) for item in items]

        assert all(r is not None for r in results)
        titles = {r.title for r in results}
        assert titles == {"Item 0", "Item 1", "Item 2"}

    def test_same_identity_verdicts_upsert_to_one_entry(self, tmp_path):
        """Two verdicts with the same source_type+url+title collapse to one item (R5 upsert)."""
        v1 = _make_verdict(score=7, fever_id=10)
        v2 = _make_verdict(score=9, fever_id=11)  # same url+title → same item.id

        item1 = map_verdict_to_item(v1)
        item2 = map_verdict_to_item(v2)

        # Same identity key
        assert item1.id == item2.id

        with InMemoryStore(blob_root=tmp_path / "blobs") as store:
            store.put_item(item1)
            store.put_item(item2)
            result = store.get_item(item1.id)
            all_items = store.list_items()

        # Only one entry stored (last-write-wins upsert)
        assert len(all_items) == 1
        assert result is not None
        # Last write wins: score=9 from item2
        assert result.payload["score"] == 9
        assert result.payload["fever_id"] == 11

    def test_missed_id_returns_none(self, tmp_path):
        with InMemoryStore(blob_root=tmp_path / "blobs") as store:
            result = store.get_item("nonexistent" * 4)

        assert result is None
