#!/usr/bin/env python3
"""dedupe.py — the reproducible alert identity and the atomic claim wrapper.

`compute_dedupe_id` is the single definition of the dedupe identity (SPEC
R2): sha256(f"{item_id}|{cnr_tier}") truncated to the first 16 hex
characters. Truncating a 64-hex-char sha256 digest to 16 hex characters
(64 bits of the digest) is accepted at the volume this phase actually sees —
at most 5 CAT I alerts per day (SPEC §Constraints) — so a future reader
should not "fix" this into a longer or untruncated value; the collision risk
at 5/day is not a real risk at this scale.

`claim` performs no read before the write — the Store's `claim_alert` is a
single INSERT-ON-CONFLICT statement and is the entire race window (SPEC R1
"atomic check-and-set, no race window"). Do NOT add an in-process set, lock,
or cache in front of it: an in-process guard is invisible across a restart
and across the two trigger paths (verdict.ready / sab.published), which is
precisely the failure mode this design avoids.
"""
from __future__ import annotations

import datetime
import hashlib


def compute_dedupe_id(item_id: str, cnr_tier: str) -> str:
    """Return the reproducible 16-hex-character dedupe identity for (item_id, cnr_tier).

    Same (item_id, cnr_tier) always hashes to the same value; a different
    cnr_tier for the same item_id hashes to a different value (SPEC R2).
    """
    return hashlib.sha256(f"{item_id}|{cnr_tier}".encode()).hexdigest()[:16]


def claim(
    store,
    *,
    item_id: str,
    cnr_tier: str,
    alert_id: str,
    ttl_seconds: int = 86400,
    now: datetime.datetime | None = None,
) -> tuple[str, bool]:
    """Atomically claim (item_id, cnr_tier) for alert_id via the Store's claim_alert.

    Computes the dedupe id and delegates straight to `store.claim_alert` — no
    read-before-write. Returns (dedupe_id, claimed) where claimed is True iff
    the alert should fire: a fresh identity always claims, a conflicting
    identity within ttl_seconds of `now` is suppressed (False), and a
    conflicting identity past the TTL re-fires (True).
    """
    dedupe_id = compute_dedupe_id(item_id, cnr_tier)
    claimed = store.claim_alert(
        dedupe_id,
        item_id,
        cnr_tier,
        alert_id,
        ttl_seconds=ttl_seconds,
        now=now,
    )
    return dedupe_id, claimed
