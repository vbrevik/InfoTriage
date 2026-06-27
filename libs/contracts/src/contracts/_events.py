#!/usr/bin/env python3
"""_events.py — bus event schemas for InfoTriage.

Four event models covering the complete lifecycle from ingest to SAB publication.
Each event carries a Literal `event` field used as the bus routing key discriminator.

Usage:
    from contracts import ItemIngested, VerdictReady, SabPublished, FeedUnhealthy
"""
from typing import Literal, Optional

from pydantic import AwareDatetime, BaseModel, Field


class ItemIngested(BaseModel):
    """Published by Phase 4 ingest adapters when an item enters the pipeline."""

    event: Literal["item.ingested"]
    item_id: str          # sha256 hex — FK to Item.id
    source: str           # human-readable source name for inline display
    ts: AwareDatetime


class VerdictReady(BaseModel):
    """Published by Phase 5 triage when an item has been scored by the LLM."""

    event: Literal["verdict.ready"]
    item_id: str
    ccir: Optional[str] = None          # None = not CCIR-relevant
    cnr: Literal["I", "II", "Routine"]  # Commander's Notification Requirement
    score: int                           # 0–10 triage score
    bucket: Literal["keep", "maybe", "skip"]
    why: str                             # LLM rationale
    ts: AwareDatetime


class SabPublished(BaseModel):
    """Published by Phase 6 brief app when a Situational Awareness Brief is rendered."""

    event: Literal["sab.published"]
    pub_ts: AwareDatetime               # SAB publication timestamp
    snapshot_day: str                   # ISO-8601 date string, e.g. "2026-06-27"
    ccir_topics: list[str]              # CCIR/PIR/FFIR topics covered
    bluf_by_topic: dict[str, str]       # topic_key → BLUF paragraph with [N] citation refs
    item_refs: list[dict]               # [{item_id, ccir, cnr, n, title, source, url, ts}, ...]
    total_keep: int                     # item count badge ("N new")
    since_ts: Optional[AwareDatetime] = None   # cutoff; None = full-corpus SAB


class FeedUnhealthy(BaseModel):
    """Published by Phase 7 opml-health worker when a source feed has gone silent."""

    event: Literal["feed.unhealthy"]
    feed_url: str
    feed_name: str
    reason: str = Field(max_length=120)  # human-readable, ≤120 chars (UI-SPEC §2)
    last_ok_at: Optional[AwareDatetime] = None   # None = never seen healthy
    ts: AwareDatetime
