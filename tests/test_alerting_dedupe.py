"""tests/test_alerting_dedupe.py — SPEC R2: dedupe_id formula + atomic claim TTL.

Drives the TTL boundary with an injected clock (never sleeps) against
InMemoryStore.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from store import InMemoryStore

from dedupe import claim, compute_dedupe_id


def test_compute_dedupe_id_stable_and_16_chars():
    first = compute_dedupe_id("item-1", "I")
    second = compute_dedupe_id("item-1", "I")

    assert first == second
    assert len(first) == 16


def test_compute_dedupe_id_matches_independent_sha256():
    item_id = "item-42"
    expected = hashlib.sha256(f"{item_id}|I".encode()).hexdigest()[:16]

    assert compute_dedupe_id(item_id, "I") == expected


def test_compute_dedupe_id_tier_sensitive():
    item_id = "item-9"

    assert compute_dedupe_id(item_id, "I") != compute_dedupe_id(item_id, "II")


def test_claim_true_first_then_false_on_immediate_repeat(tmp_path):
    store = InMemoryStore(blob_root=tmp_path)
    now = datetime.now(tz=timezone.utc)

    dedupe_id_1, claimed_1 = claim(
        store, item_id="item-1", cnr_tier="I", alert_id="alert-1", now=now
    )
    dedupe_id_2, claimed_2 = claim(
        store, item_id="item-1", cnr_tier="I", alert_id="alert-2", now=now
    )

    assert claimed_1 is True
    assert claimed_2 is False
    assert dedupe_id_1 == dedupe_id_2


def test_claim_true_again_after_ttl_expires(tmp_path):
    store = InMemoryStore(blob_root=tmp_path)
    now = datetime.now(tz=timezone.utc)

    _, claimed_1 = claim(
        store, item_id="item-1", cnr_tier="I", alert_id="alert-1", now=now
    )
    within_ttl = now + timedelta(hours=23)
    _, claimed_too_early = claim(
        store, item_id="item-1", cnr_tier="I", alert_id="alert-2", now=within_ttl
    )
    after_ttl = now + timedelta(hours=24, seconds=1)
    _, claimed_2 = claim(
        store, item_id="item-1", cnr_tier="I", alert_id="alert-3", now=after_ttl
    )

    assert claimed_1 is True
    assert claimed_too_early is False
    assert claimed_2 is True


def test_claim_does_not_cross_suppress_interleaved_identities(tmp_path):
    store = InMemoryStore(blob_root=tmp_path)
    now = datetime.now(tz=timezone.utc)

    _, claimed_a1 = claim(
        store, item_id="item-a", cnr_tier="I", alert_id="alert-a1", now=now
    )
    _, claimed_b1 = claim(
        store, item_id="item-b", cnr_tier="I", alert_id="alert-b1", now=now
    )
    _, claimed_a2 = claim(
        store, item_id="item-a", cnr_tier="I", alert_id="alert-a2", now=now
    )
    _, claimed_b2 = claim(
        store, item_id="item-b", cnr_tier="I", alert_id="alert-b2", now=now
    )

    assert claimed_a1 is True
    assert claimed_b1 is True
    assert claimed_a2 is False
    assert claimed_b2 is False
