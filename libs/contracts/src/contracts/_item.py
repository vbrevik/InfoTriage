#!/usr/bin/env python3
"""_item.py — canonical information item schema for InfoTriage.

Usage:
    from contracts import Item
    item = Item(source="NRK", source_type="rss", url="https://nrk.no/1",
                title="Test", ts=datetime.datetime.now(tz=datetime.timezone.utc),
                lang="no")
    print(item.id)  # sha256 hex — stable dedup key
"""
import hashlib
from typing import Optional

from pydantic import AwareDatetime, BaseModel, Field, computed_field


class Item(BaseModel):
    """Canonical information item — single source of truth across all InfoTriage apps.

    The id field is a read-only SHA-256 computed from source_type, url, and title.
    It is the idempotency key used by InMemoryBus and the Postgres dedup layer.
    """

    # Core fields
    source: str  # human-readable source name ("NRK Nyheter")
    source_type: str  # machine-readable type ("rss", "imap", "yt")
    url: str = ""  # empty string when absent (per SPEC R1)
    title: str
    ts: AwareDatetime  # requires tz-aware — naive datetime raises ValidationError
    lang: str

    # Content fields
    summary: Optional[str] = None
    body_ref: Optional[str] = None

    # Phase 11: collection discipline + Admiralty reliability rating
    discipline: Optional[str] = Field(
        default=None,
        pattern=r"^(OSINT|SOCMINT|MASINT|GEOINT|SIGINT|HUMINT|MASINT/AIS)$",
        description="Collection discipline tag (e.g. OSINT, SOCMINT, MASINT/AIS)",
    )
    admiralty_reliability: Optional[str] = Field(
        default=None,
        pattern=r"^[A-F][1-6]$",
        description="Admiralty reliability rating (A-F + 1-6, e.g. A1, B2)",
    )

    # Rich / open
    payload: dict = {}  # open dict — Phase 5 writes ccir, cnr, score, bucket, why
    attachments: list = []

    @computed_field  # type: ignore[prop-decorator]
    @property
    def id(self) -> str:
        """SHA-256 of normalized source_type + NUL + url + NUL + title.

        Content-stable dedup key. Empty url contributes an empty string to the hash.
        """
        raw = f"{self.source_type}\x00{self.url}\x00{self.title}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()
