#!/usr/bin/env python3
"""test_ingest_obsidian.py — R4: Obsidian Web Clipper clip ingestion tests.

Covers:
  - D-09 field mapping: title→title, url→url, date→ts, site→source, description→summary
  - lang inference: æ/ø/å in title → "no"; otherwise "en"; empty → "und"
  - source_type is always "obsidian"
  - missing required fields (title/url/date) fall back to defaults; clip not rejected
  - running ingest() twice: same row count, bus event published only once (R4 idempotency)
"""
import datetime
import logging
import pathlib

import pytest

from contracts import InMemoryBus
from store import InMemoryStore

# ---------------------------------------------------------------------------
# Sample clip files
# ---------------------------------------------------------------------------

# Full frontmatter — all fields present; English title
CLIP_FULL = """\
---
title: Climate Change Report 2026
url: https://example.com/climate
date: 2026-06-01T12:00:00+00:00
site: Example News
description: A summary of climate findings
tags: [climate, environment]
---

Body text here.
"""

# Norwegian title containing æ, ø, å — lang should be inferred as "no"
CLIP_NORWEGIAN = """\
---
title: Norsk nyhetsartikkel med æ, ø og å
url: https://nrk.no/article/1
date: 2026-06-02T08:00:00+00:00
site: NRK
description: En norsk artikkel om nyheter
---

Norsk tekst her.
"""

# Empty frontmatter — no fields at all; all fallback values apply
CLIP_MISSING_FIELDS = """\
---
---

This clip has no frontmatter fields at all.
"""


def _write_clip(path: pathlib.Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingest_d09_field_mapping(tmp_path: pathlib.Path, monkeypatch) -> None:
    """Two clips ingested; D-09 field mapping (title, url, site, description) verified.

    The Norwegian clip must have lang='no'; the English clip lang='en'.
    source_type must be 'obsidian' on both.
    """
    inbox = tmp_path / "articles-inbox"
    inbox.mkdir()
    _write_clip(inbox / "clip_full.md", CLIP_FULL)
    _write_clip(inbox / "clip_norwegian.md", CLIP_NORWEGIAN)

    my_store = InMemoryStore(blob_root=tmp_path / "blobs")
    my_bus = InMemoryBus()

    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(tmp_path))

    import obsidian_ingest

    monkeypatch.setattr(obsidian_ingest, "build_store", lambda: my_store)
    monkeypatch.setattr(obsidian_ingest, "build_bus", lambda: my_bus)

    await obsidian_ingest.ingest()

    items = my_store.list_items()
    assert len(items) == 2, f"Expected 2 items, got {len(items)}"

    by_url = {item.url: item for item in items}

    # --- full clip assertions (D-09 mapping) ---
    full = by_url["https://example.com/climate"]
    assert full.source_type == "obsidian"
    assert full.source == "Example News"      # site → source
    assert full.title == "Climate Change Report 2026"
    assert full.summary == "A summary of climate findings"  # description → summary
    assert full.lang == "en"
    assert full.ts.tzinfo is not None          # tz-aware

    # --- Norwegian clip assertions ---
    no_item = by_url["https://nrk.no/article/1"]
    assert no_item.source_type == "obsidian"
    assert no_item.source == "NRK"
    assert no_item.lang == "no"                # æ/ø/å in title → "no"


@pytest.mark.asyncio
async def test_ingest_missing_fields_not_rejected(
    tmp_path: pathlib.Path, monkeypatch, caplog
) -> None:
    """Clip with empty frontmatter: falls back to safe defaults; not rejected; warning logged.

    Fallback values per D-09:
      title → ""
      url → ""
      ts → datetime.now(tz=utc)  [tz-aware]
      lang → "und"               [empty title]
    """
    inbox = tmp_path / "articles-inbox"
    inbox.mkdir()
    _write_clip(inbox / "clip_empty.md", CLIP_MISSING_FIELDS)

    my_store = InMemoryStore(blob_root=tmp_path / "blobs")
    my_bus = InMemoryBus()

    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(tmp_path))

    import obsidian_ingest

    monkeypatch.setattr(obsidian_ingest, "build_store", lambda: my_store)
    monkeypatch.setattr(obsidian_ingest, "build_bus", lambda: my_bus)

    with caplog.at_level(logging.WARNING, logger="obsidian_ingest"):
        await obsidian_ingest.ingest()

    # Clip is ingested — not rejected
    items = my_store.list_items()
    assert len(items) == 1, f"Expected 1 item (not rejected), got {len(items)}"

    item = items[0]
    assert item.source_type == "obsidian"
    assert item.title == ""              # fallback: empty string
    assert item.url == ""               # fallback: empty string
    assert item.ts.tzinfo is not None   # fallback ts is tz-aware
    assert item.lang == "und"           # empty title → indeterminate

    # Warning must have been logged (missing fields)
    warning_records = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert warning_records, "Expected a warning for missing fields, but none was logged"


@pytest.mark.asyncio
async def test_ingest_idempotency(tmp_path: pathlib.Path, monkeypatch) -> None:
    """Running ingest() twice over same clips: 1 row in store; bus event published once (R4)."""
    inbox = tmp_path / "articles-inbox"
    inbox.mkdir()
    _write_clip(inbox / "clip.md", CLIP_FULL)

    my_store = InMemoryStore(blob_root=tmp_path / "blobs")
    my_bus = InMemoryBus()

    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(tmp_path))

    import obsidian_ingest

    monkeypatch.setattr(obsidian_ingest, "build_store", lambda: my_store)
    monkeypatch.setattr(obsidian_ingest, "build_bus", lambda: my_bus)

    # First run
    await obsidian_ingest.ingest()
    # Second run — same files
    await obsidian_ingest.ingest()

    # Row count unchanged
    assert len(my_store.list_items()) == 1, "Expected exactly 1 row after two runs"

    # Bus event published exactly once
    messages = await my_bus.subscribe("item.ingested")
    assert len(messages) == 1, f"Expected 1 bus event, got {len(messages)}"
