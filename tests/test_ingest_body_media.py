#!/usr/bin/env python3
"""test_ingest_body_media.py — SPEC R7 producer-side body write path: youtube, telegram, obsidian.

Covers plan 12-08 Task 2: all three adapters set Item.body at their single
construction site. YouTube's transcript-less case must persist NULL (not the
stub placeholder text). Telegram's photo-only-no-caption case must persist
NULL. Obsidian's empty/whitespace-only note must persist NULL. No adapter
truncates, caps, or sanitizes body; summary derivations are unchanged.

Assertions read the persisted value back through store.get_item(), matching
the plan's instruction that the store's coercion is part of what is proven.
"""
import datetime
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from store import InMemoryStore

# telegram lives under a hyphenated dir not on the shared pytest pythonpath.
sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "apps" / "ingest-telegram")
)
import telegram_ingest  # noqa: E402


# ===========================================================================
# YouTube — single construction site (youtube_ingest.py)
# ===========================================================================

OVERSIZED_TRANSCRIPT = "word " * 220_000  # >= 1_100_000 characters


@pytest.mark.asyncio
async def test_youtube_transcript_persists_full_body(tmp_path, monkeypatch):
    """A youtube item with a transcript persists the full transcript as body."""
    from contracts import InMemoryBus

    import youtube_ingest

    store = InMemoryStore(blob_root=tmp_path / "blobs")
    bus = InMemoryBus()
    monkeypatch.setattr(youtube_ingest, "build_store", lambda: store)
    monkeypatch.setattr(youtube_ingest, "build_bus", lambda: bus)
    monkeypatch.setenv(
        "YT_CHANNELS",
        '[{"channel": "https://youtube.com/@test", "name": "TestChan", "max_n": 1, "transcribe": true}]',
    )
    monkeypatch.setattr(youtube_ingest, "OUT_DIR", str(tmp_path / "feeds"))
    monkeypatch.setattr(
        youtube_ingest, "yt_dlp_list", lambda channel, max_n: [("vid1", "Video One")]
    )
    monkeypatch.setattr(
        youtube_ingest,
        "_download_audio",
        lambda video_id: (str(tmp_path), str(tmp_path / "audio.mp3")),
    )
    monkeypatch.setattr(
        youtube_ingest,
        "_transcribe_audio",
        lambda audio_path, model_name="tiny": "This is the real transcript text.",
    )

    await youtube_ingest.ingest()

    items = store.list_items(source_type_in=["yt"])
    assert len(items) == 1
    retrieved = store.get_item(items[0].id)
    assert retrieved.body == "This is the real transcript text."
    assert retrieved.summary == "This is the real transcript text."[:500]


@pytest.mark.asyncio
async def test_youtube_no_transcript_persists_null_body(tmp_path, monkeypatch):
    """A youtube item with transcription disabled persists a NULL body (not the stub text)."""
    from contracts import InMemoryBus

    import youtube_ingest

    store = InMemoryStore(blob_root=tmp_path / "blobs")
    bus = InMemoryBus()
    monkeypatch.setattr(youtube_ingest, "build_store", lambda: store)
    monkeypatch.setattr(youtube_ingest, "build_bus", lambda: bus)
    monkeypatch.delenv("INFOTRIAGE_YOUTUBE_TRANSCRIBE", raising=False)
    monkeypatch.setenv(
        "YT_CHANNELS",
        '[{"channel": "https://youtube.com/@test", "name": "TestChan", "max_n": 1}]',
    )
    monkeypatch.setattr(youtube_ingest, "OUT_DIR", str(tmp_path / "feeds"))
    monkeypatch.setattr(
        youtube_ingest, "yt_dlp_list", lambda channel, max_n: [("vid2", "Video Two")]
    )

    await youtube_ingest.ingest()

    items = store.list_items(source_type_in=["yt"])
    assert len(items) == 1
    retrieved = store.get_item(items[0].id)
    assert retrieved.body is None
    # The stub display text is still the (unchanged) summary derivation.
    assert retrieved.summary.startswith("(transcription disabled")


@pytest.mark.asyncio
async def test_youtube_oversized_transcript_round_trips_with_no_truncation(
    tmp_path, monkeypatch
):
    """A >=1.1M-char transcript round-trips byte-identical — SPEC R7's no-size-cap backstop."""
    from contracts import InMemoryBus

    import youtube_ingest

    assert len(OVERSIZED_TRANSCRIPT) >= 1_100_000

    store = InMemoryStore(blob_root=tmp_path / "blobs")
    bus = InMemoryBus()
    monkeypatch.setattr(youtube_ingest, "build_store", lambda: store)
    monkeypatch.setattr(youtube_ingest, "build_bus", lambda: bus)
    monkeypatch.setenv(
        "YT_CHANNELS",
        '[{"channel": "https://youtube.com/@test", "name": "TestChan", "max_n": 1, "transcribe": true}]',
    )
    monkeypatch.setattr(youtube_ingest, "OUT_DIR", str(tmp_path / "feeds"))
    monkeypatch.setattr(
        youtube_ingest, "yt_dlp_list", lambda channel, max_n: [("vid3", "Video Three")]
    )
    monkeypatch.setattr(
        youtube_ingest,
        "_download_audio",
        lambda video_id: (str(tmp_path), str(tmp_path / "audio.mp3")),
    )
    monkeypatch.setattr(
        youtube_ingest,
        "_transcribe_audio",
        lambda audio_path, model_name="tiny": OVERSIZED_TRANSCRIPT,
    )

    await youtube_ingest.ingest()

    items = store.list_items(source_type_in=["yt"])
    assert len(items) == 1
    retrieved = store.get_item(items[0].id)
    assert retrieved.body is not None
    assert len(retrieved.body) == len(OVERSIZED_TRANSCRIPT)
    assert retrieved.body == OVERSIZED_TRANSCRIPT


def test_transcribe_returns_stub_and_false_when_disabled():
    """transcribe() returns (stub_text, False) when transcription is not wanted."""
    import youtube_ingest

    text, is_real = youtube_ingest.transcribe("vid", transcribe_wanted=False)
    assert is_real is False
    assert text.startswith("(transcription disabled")


# ===========================================================================
# Telegram — single construction site (telegram_ingest.py)
# ===========================================================================


@pytest.mark.asyncio
async def test_telegram_message_text_persists_full_body(tmp_path):
    """A telegram post with message text persists that text as body."""
    message = SimpleNamespace(
        id=1,
        date=datetime.datetime.now(tz=datetime.timezone.utc),
        text="Breaking: convoy spotted moving north.\nMore details to follow.",
    )
    item = telegram_ingest._message_to_item("testchannel", message)

    store = InMemoryStore(blob_root=tmp_path / "blobs")
    store.put_item(item)
    retrieved = store.get_item(item.id)
    assert retrieved.body == message.text
    assert retrieved.summary == message.text[:500]


@pytest.mark.asyncio
async def test_telegram_photo_only_no_caption_persists_null_body(tmp_path):
    """A photo-only post with no caption persists a NULL body (SPEC R7 named case)."""
    message = SimpleNamespace(
        id=2,
        date=datetime.datetime.now(tz=datetime.timezone.utc),
        text="",
    )
    item = telegram_ingest._message_to_item("testchannel", message)

    store = InMemoryStore(blob_root=tmp_path / "blobs")
    store.put_item(item)
    retrieved = store.get_item(item.id)
    assert retrieved.body is None


# ===========================================================================
# Obsidian — single construction site (obsidian_ingest.py)
# ===========================================================================

CLIP_WITH_BODY = """\
---
title: Arctic Shipping Update
url: https://example.com/arctic
date: 2026-06-05T09:00:00+00:00
site: Example News
description: Short summary of the update
---

Full note content describing the Arctic shipping situation in detail,
across several lines of text that make up the note body.
"""

CLIP_NO_BODY = """\
---
title: No Body Clip
url: https://example.com/nobody
date: 2026-06-06T09:00:00+00:00
site: Example News
description: Has no note content
---
"""


def _write_clip(path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


@pytest.mark.asyncio
async def test_obsidian_note_persists_full_text(tmp_path, monkeypatch):
    """An obsidian note persists its full note text (content after frontmatter) as body."""
    from contracts import InMemoryBus

    import obsidian_ingest

    inbox = tmp_path / "articles-inbox"
    inbox.mkdir()
    _write_clip(inbox / "clip.md", CLIP_WITH_BODY)

    store = InMemoryStore(blob_root=tmp_path / "blobs")
    bus = InMemoryBus()
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(tmp_path))
    monkeypatch.setattr(obsidian_ingest, "build_store", lambda: store)
    monkeypatch.setattr(obsidian_ingest, "build_bus", lambda: bus)

    await obsidian_ingest.ingest()

    items = store.list_items()
    assert len(items) == 1
    retrieved = store.get_item(items[0].id)
    expected_body = obsidian_ingest._extract_note_body(CLIP_WITH_BODY)
    assert retrieved.body == expected_body
    assert "Full note content" in retrieved.body
    assert retrieved.summary == "Short summary of the update"


@pytest.mark.asyncio
async def test_obsidian_empty_note_persists_null_body(tmp_path, monkeypatch):
    """A note with no content after frontmatter persists a NULL body."""
    from contracts import InMemoryBus

    import obsidian_ingest

    inbox = tmp_path / "articles-inbox"
    inbox.mkdir()
    _write_clip(inbox / "clip.md", CLIP_NO_BODY)

    store = InMemoryStore(blob_root=tmp_path / "blobs")
    bus = InMemoryBus()
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(tmp_path))
    monkeypatch.setattr(obsidian_ingest, "build_store", lambda: store)
    monkeypatch.setattr(obsidian_ingest, "build_bus", lambda: bus)

    await obsidian_ingest.ingest()

    items = store.list_items()
    assert len(items) == 1
    retrieved = store.get_item(items[0].id)
    assert retrieved.body is None
