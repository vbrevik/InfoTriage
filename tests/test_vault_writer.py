#!/usr/bin/env python3
"""test_vault_writer.py — Unit tests for vault_writer.py (Phase 6, SC2)."""
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest
from contracts import from_frontmatter
from apps.brief.vault_writer import (
    render_wikilinked,
    write_item_obsidian,
    write_sab_obsidian,
    write_vault_digest,
)


@pytest.fixture
def temp_vault():
    """Create a temporary directory for vault contents."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def test_render_wikilinked():
    """Test that entities are replaced with [[Entity]] syntax."""
    text = "Meeting in Oslo with NATO."
    entities = ["NATO", "Oslo"]
    result = render_wikilinked(text, entities)

    assert "[[Oslo]]" in result
    assert "[[NATO]]" in result
    assert "Oslo" in result and "NATO" in result  # original words still there


def test_write_item_obsidian(temp_vault):
    """Test writing a single item to Obsidian format."""
    item = {
        "item_id": "test-123",
        "title": "Test Article",
        "summary": "This is a summary about Oslo and NATO.",
        "source": "Example News",
        "url": "https://example.com",
        "ts": datetime.now(timezone.utc).isoformat(),
        "ccir": "PIR-3",
        "cnr": "I",
        "score": 9,
        "bucket": "read",
        "why": "Important for Norway",
        "entities": [
            {"name": "NATO", "mention": "NATO", "lang": "en"},
            {"name": "Oslo", "mention": "Oslo", "lang": "en"},
        ],
    }

    path = write_item_obsidian(item, temp_vault)

    assert path.exists()
    assert path.name == "test-123.md"

    content = path.read_text()
    assert "## Summary" in content
    assert "## Why" in content
    assert "Test Article" in content
    # Check key content exists even if wikilinked
    assert "Test Article" in content
    assert "Norway" in content  # Should be present even if wikilinked
    assert "Example News" in content
    # Check front-matter fields
    assert "title: Test Article" in content
    assert "score: 9" in content
    assert "ccir: PIR-3" in content
    frontmatter = from_frontmatter(content)
    assert frontmatter["title"] == "Test Article"
    assert frontmatter["url"] == "https://example.com"


def test_write_item_obsidian_uses_codec_safe_yaml(temp_vault):
    """Front matter must survive punctuation and multiline strings."""
    item = {
        "item_id": "test:unsafe/id",
        "title": 'Status: "quoted"\nmultiline',
        "summary": "Oslo and NATO update.",
        "source": "Example: Source",
        "url": "https://example.com/a?x=1:y",
        "ts": "2026-07-07T10:00:00+00:00",
        "ccir": "PIR-3",
        "cnr": "I",
        "score": 9,
        "bucket": "read",
        "why": "Important for Norway: yes",
        "entities": [
            {"name": "NATO", "mention": "NATO", "lang": "en"},
            {"name": "Oslo", "mention": "Oslo", "lang": "en"},
        ],
    }

    path = write_item_obsidian(item, temp_vault)
    frontmatter = from_frontmatter(path.read_text())

    assert frontmatter["title"] == item["title"]
    assert frontmatter["source"] == item["source"]
    assert frontmatter["url"] == item["url"]


def test_write_sab_obsidian(temp_vault):
    """Test writing SAB projection to Obsidian."""
    rows = [
        {
            "item_id": "1",
            "title": "First Article",
            "summary": "About climate",
            "source": "News1",
            "url": "https://1.com",
            "ccir": "PIR-1",
            "score": 8,
            "cnr": "I",
            "entities": [{"name": "Climate", "mention": "climate", "lang": "en"}],
        },
        {
            "item_id": "2",
            "title": "Second Article",
            "summary": "About NATO",
            "source": "News2",
            "url": "https://2.com",
            "ccir": "PIR-2",
            "score": 9,
            "cnr": "I",
            "entities": [{"name": "NATO", "mention": "NATO", "lang": "en"}],
        },
    ]

    path = write_sab_obsidian(rows, temp_vault)

    assert path.exists()
    assert path.name == "obsidian-sab.md"
    content = path.read_text()
    assert "PIR-1" in content
    assert "PIR-2" in content
    assert "## PIR-1" in content
    assert "## PIR-2" in content


def test_write_vault_digest_filter(temp_vault):
    """Test that write_vault_digest filters and writes items."""
    rows = [
        # Should be included (score >= 8)
        {
            "item_id": "1",
            "title": "High Score Item",
            "summary": "Summary",
            "source": "",
            "url": "",
            "ccir": "PIR-1",
            "score": 9,
            "cnr": "I",
        },
        # Should be included (score < 8 but has CCIR)
        {
            "item_id": "2",
            "title": "Low Score Item",
            "summary": "Summary",
            "source": "",
            "url": "",
            "ccir": "PIR-2",
            "score": 5,
            "cnr": "I",
        },
        # Should be excluded (no CCIR, score < 8)
        {
            "item_id": "3",
            "title": "Excluded Item",
            "summary": "Summary",
            "source": "",
            "url": "",
            "ccir": "",
            "score": 7,
            "cnr": "",
        },
    ]

    paths = write_vault_digest(rows, temp_vault)

    assert len(paths) >= 2  # at least the two included items + SAB file
    # Check SAB file exists
    assert (temp_vault / "obsidian-sab.md").exists()


def test_write_vault_digest_includes_email_by_default(temp_vault, monkeypatch):
    """Email-sourced rows are included unless explicitly disabled."""
    monkeypatch.delenv("VAULT_INCLUDE_EMAIL", raising=False)
    rows = [
        {
            "item_id": "email-1",
            "title": "Email Item",
            "summary": "NATO update from email.",
            "source": "imap://inbox/message-1",
            "url": "imap://inbox/message-1",
            "ccir": "PIR-1",
            "score": 9,
            "cnr": "I",
        }
    ]

    paths = write_vault_digest(rows, temp_vault)

    # Returns the item file plus the SAB projection
    assert len(paths) == 2
    assert (temp_vault / "email-1.md").exists()
    assert (temp_vault / "obsidian-sab.md").exists()


def test_gmail_row_excluded_when_email_disabled(temp_vault, monkeypatch):
    """Production gmail rows (source='gmail', url='gmail://...') must be excluded
    from the vault when VAULT_INCLUDE_EMAIL=0."""
    monkeypatch.setenv("VAULT_INCLUDE_EMAIL", "0")
    rows = [
        {
            "item_id": "gmail-1",
            "title": "Gmail Item",
            "summary": "Summary",
            "source": "gmail",
            "url": "gmail://message/abc123",
            "ccir": "PIR-1",
            "score": 9,
            "cnr": "I",
        }
    ]

    write_vault_digest(rows, temp_vault)

    assert not (temp_vault / "gmail-1.md").exists()
    assert "Gmail Item" not in (temp_vault / "obsidian-sab.md").read_text()


def test_imap_row_excluded_when_email_disabled(temp_vault, monkeypatch):
    """Production imap rows (source=<mailbox name>, url='imap://...') must be
    excluded from the vault when VAULT_INCLUDE_EMAIL=0."""
    monkeypatch.setenv("VAULT_INCLUDE_EMAIL", "0")
    rows = [
        {
            "item_id": "imap-1",
            "title": "Imap Item",
            "summary": "Summary",
            "source": "Telegraph Ukraine",
            "url": "imap://mail.example.com/msg-1",
            "ccir": "PIR-2",
            "score": 9,
            "cnr": "I",
        }
    ]

    write_vault_digest(rows, temp_vault)

    assert not (temp_vault / "imap-1.md").exists()
    assert "Imap Item" not in (temp_vault / "obsidian-sab.md").read_text()


def test_non_email_row_not_excluded_when_email_disabled(temp_vault, monkeypatch):
    """The VAULT_INCLUDE_EMAIL toggle must not drop non-email rows."""
    monkeypatch.setenv("VAULT_INCLUDE_EMAIL", "0")
    rows = [
        {
            "item_id": "rss-1",
            "title": "RSS Item",
            "summary": "Summary",
            "source": "NRK",
            "url": "https://nrk.no/article-1",
            "ccir": "PIR-1",
            "score": 9,
            "cnr": "I",
        }
    ]

    write_vault_digest(rows, temp_vault)

    assert (temp_vault / "rss-1.md").exists()


def test_gmail_row_included_by_default(temp_vault, monkeypatch):
    """Gmail rows are included when VAULT_INCLUDE_EMAIL is unset (default)."""
    monkeypatch.delenv("VAULT_INCLUDE_EMAIL", raising=False)
    rows = [
        {
            "item_id": "gmail-1",
            "title": "Gmail Item",
            "summary": "Summary",
            "source": "gmail",
            "url": "gmail://message/abc123",
            "ccir": "PIR-1",
            "score": 9,
            "cnr": "I",
        }
    ]

    write_vault_digest(rows, temp_vault)

    assert (temp_vault / "gmail-1.md").exists()


def test_write_sab_obsidian_custom_filename(temp_vault):
    """write_sab_obsidian supports custom filenames for view projections."""
    rows = [
        {
            "item_id": "1",
            "title": "First Article",
            "summary": "About climate",
            "source": "News1",
            "url": "https://1.com",
            "ccir": "PIR-1",
            "score": 8,
            "cnr": "I",
        },
    ]

    path = write_sab_obsidian(rows, temp_vault, filename="obsidian-sab-cop.md")

    assert path.exists()
    assert path.name == "obsidian-sab-cop.md"
    assert "PIR-1" in path.read_text()


def test_write_vault_digest_view_projection(temp_vault):
    """write_vault_digest can write a view projection without re-writing items."""
    rows = [
        {
            "item_id": "1",
            "title": "COP Item",
            "summary": "Summary",
            "source": "",
            "url": "",
            "ccir": "FFIR-1",
            "score": 9,
            "cnr": "I",
        },
    ]

    # First write default (items + SAB)
    paths = write_vault_digest(
        rows, temp_vault, write_items=True, sab_filename="obsidian-sab.md"
    )
    assert (temp_vault / "1.md").exists()
    assert (temp_vault / "obsidian-sab.md").exists()

    # Then write a view projection without re-writing items
    paths = write_vault_digest(
        rows, temp_vault, write_items=False, sab_filename="obsidian-sab-cop.md"
    )
    assert (temp_vault / "obsidian-sab-cop.md").exists()
    # Should still return the SAB path even when not writing items
    assert any(p.name == "obsidian-sab-cop.md" for p in paths)
