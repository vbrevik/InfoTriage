#!/usr/bin/env python3
"""Tests for apps.brief.consumer view-filtered rendering path (Phase 6).

These tests exercise process_verdict() with mocked Postgres/RabbitMQ dependencies,
verifying that the consumer renders default, COP, and CIP digest files plus the
matching vault projections.
"""
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from apps.brief.consumer import process_verdict  # noqa: E402


def _make_row(
    item_id: str = "item-1",
    ccir: str = "PIR-1",
    cnr: str = "II",
    score: int = 9,
    pmesii: str = "Military",
    tessoc: str = "Sabotage",
    title: str = "Test Title",
    source: str = "TestSource",
    url: str = "http://example.com",
    summary: str = "Test summary",
    ts: str = "2026-07-11T12:00:00",
) -> dict:
    return {
        "item_id": item_id,
        "ccir": ccir,
        "cnr": cnr,
        "score": score,
        "bucket": "keep",
        "why": "Test why",
        "pmesii": pmesii,
        "tessoc": tessoc,
        "title": title,
        "source": source,
        "url": url,
        "summary": summary,
        "ts": ts,
    }


@pytest.fixture
def sample_rows():
    """Rows that exercise default, COP, and CIP views."""
    return [
        # Default + CIP
        _make_row(
            item_id="pir-1",
            ccir="PIR-1",
            pmesii="Military",
            tessoc="Sabotage",
            title="CIP Item",
        ),
        # Default + COP
        _make_row(
            item_id="ffir-1",
            ccir="FFIR-1",
            pmesii="Political",
            tessoc="Espionage",
            title="COP Item",
        ),
        # Default only
        _make_row(
            item_id="pir-5",
            ccir="PIR-5",
            pmesii="Social",
            tessoc="none",
            title="Other Item",
        ),
    ]


@pytest.fixture
def mock_store(sample_rows):
    """PostgresStore mock that returns sample rows."""
    store = MagicMock()
    cursor = MagicMock()
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=None)

    # First call (fetchone) returns the first row; second call (fetchall) returns all rows.
    cursor.fetchone.return_value = sample_rows[0]
    cursor.fetchall.return_value = sample_rows

    store.cursor.return_value = cursor
    return store


@pytest.fixture
def mock_bus():
    """RabbitMQBus mock with an async publish method."""
    bus = AsyncMock()
    bus.publish = AsyncMock()
    return bus


@pytest.mark.asyncio
@patch("apps.brief.renderer.llm", return_value="Mocked BLUF")
async def test_process_verdict_renders_default_cop_cip_files(
    mock_llm, mock_store, mock_bus, sample_rows, tmp_path
):
    """Consumer should write default, COP, and CIP digest files."""
    vault_path = tmp_path / "vault"

    with patch("apps.brief.consumer.DATA_DIR", new=tmp_path), \
         patch.dict(os.environ, {"INFOTRIAGE_VAULT_PATH": str(vault_path)}):
        event = await process_verdict(
            "pir-1", mock_store, mock_bus, snap_day="2026-07-11"
        )

    assert event is not None
    assert event.event == "sab.published"
    assert event.snapshot_day == "2026-07-11"

    # All 12 digest files should be written (default + cop + cip)
    expected_files = [
        "brief.md",
        "cluster.md",
        "list.md",
        "bluf.md",
        "brief-cop.md",
        "cluster-cop.md",
        "list-cop.md",
        "bluf-cop.md",
        "brief-cip.md",
        "cluster-cip.md",
        "list-cip.md",
        "bluf-cip.md",
    ]
    for filename in expected_files:
        fpath = tmp_path / filename
        assert fpath.exists(), f"{filename} was not written"
        assert fpath.read_text(encoding="utf-8"), f"{filename} is empty"

    # Verify content is view-specific: COP file contains COP item, not CIP item
    cop_text = (tmp_path / "brief-cop.md").read_text(encoding="utf-8")
    assert "COP Item" in cop_text
    assert "CIP Item" not in cop_text

    cip_text = (tmp_path / "brief-cip.md").read_text(encoding="utf-8")
    assert "CIP Item" in cip_text
    assert "COP Item" not in cip_text

    # Default file contains all items
    default_text = (tmp_path / "brief.md").read_text(encoding="utf-8")
    assert "COP Item" in default_text
    assert "CIP Item" in default_text
    assert "Other Item" in default_text


@pytest.mark.asyncio
@patch("apps.brief.renderer.llm", return_value="Mocked BLUF")
async def test_process_verdict_writes_view_filtered_vault_projections(
    mock_llm, mock_store, mock_bus, sample_rows, tmp_path
):
    """Consumer should write default, COP, and CIP vault projections."""
    vault_path = tmp_path / "vault"

    with patch("apps.brief.consumer.DATA_DIR", new=tmp_path), \
         patch.dict(os.environ, {"INFOTRIAGE_VAULT_PATH": str(vault_path)}):
        await process_verdict("pir-1", mock_store, mock_bus, snap_day="2026-07-11")

    # Vault projections should be written
    assert (vault_path / "obsidian-sab.md").exists()
    assert (vault_path / "obsidian-sab-cop.md").exists()
    assert (vault_path / "obsidian-sab-cip.md").exists()

    # COP projection should only contain COP item
    cop_vault = (vault_path / "obsidian-sab-cop.md").read_text(encoding="utf-8")
    assert "COP Item" in cop_vault
    assert "CIP Item" not in cop_vault

    # CIP projection should only contain CIP item
    cip_vault = (vault_path / "obsidian-sab-cip.md").read_text(encoding="utf-8")
    assert "CIP Item" in cip_vault
    assert "COP Item" not in cip_vault


@pytest.mark.asyncio
@patch("apps.brief.renderer.llm", return_value="Mocked BLUF")
async def test_process_verdict_publishes_sab_published_event(
    mock_llm, mock_store, mock_bus, sample_rows, tmp_path
):
    """Consumer should publish a SabPublished event via RabbitMQBus."""
    vault_path = tmp_path / "vault"

    with patch("apps.brief.consumer.DATA_DIR", new=tmp_path), \
         patch.dict(os.environ, {"INFOTRIAGE_VAULT_PATH": str(vault_path)}):
        event = await process_verdict(
            "pir-1", mock_store, mock_bus, snap_day="2026-07-11"
        )

    mock_bus.publish.assert_awaited_once()
    topic, item_id, payload = mock_bus.publish.call_args[0]
    assert topic == "sab.published"
    assert item_id == "pir-1"
    assert payload["snapshot_day"] == "2026-07-11"
    assert payload["total_keep"] == 3
    assert event is not None
    assert event.event == "sab.published"
