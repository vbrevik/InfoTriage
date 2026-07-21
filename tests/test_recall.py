"""tests/test_recall.py — Phase 9 recall CLI tests."""
from __future__ import annotations

import datetime
import json
import sys
from unittest.mock import MagicMock, patch

import pytest

import recall


@pytest.fixture
def fake_store():
    store = MagicMock()
    store.__enter__ = MagicMock(return_value=store)
    store.__exit__ = MagicMock(return_value=None)
    store.get_item.return_value = None
    store.recall_items.return_value = [
        {
            "item_id": "id1",
            "title": "Arctic security article",
            "source": "NRK",
            "url": "https://example.com/1",
            "ccir": "PIR-2",
            "score": 8,
            "similarity": 0.89,
        },
        {
            "item_id": "id2",
            "title": "NATO summit",
            "source": "Aftenposten",
            "url": "https://example.com/2",
            "ccir": "PIR-3",
            "score": 7,
            "similarity": 0.85,
        },
    ]
    return store


def _run_recall(*args, fake_store, fake_embedding=None, fake_llm=None):
    with patch("recall.PostgresStore", return_value=fake_store):
        with patch("recall._get_embedding", return_value=fake_embedding or [0.1] * 1024):
            with patch("recall._llm", return_value=fake_llm or "synthesized answer"):
                with patch.object(sys, "argv", ["recall.py", *args]):
                    recall.main()


def test_recall_default_markdown_output(capsys, fake_store):
    _run_recall("--topic", "Arctic security", fake_store=fake_store)
    out = capsys.readouterr().out
    assert "Recall: \"Arctic security\"" in out
    assert "Arctic security article" in out
    assert "NATO summit" in out
    assert "0.890" in out


def test_recall_json_output(capsys, fake_store):
    _run_recall("--topic", "Arctic security", "--json", fake_store=fake_store)
    out = capsys.readouterr().out
    data = json.loads(out)
    assert isinstance(data, list)
    assert len(data) == 2
    assert data[0]["item_id"] == "id1"


def test_recall_json_include_body_strips_body(capsys, fake_store):
    item = MagicMock()
    item.summary = "the summary"
    item.body_ref = "deadbeef" * 8
    fake_store.get_item.return_value = item
    fake_store.get_blob.return_value = b"full article body text"
    _run_recall("--topic", "Arctic security", "--json", "--include-body", fake_store=fake_store)
    out = capsys.readouterr().out
    data = json.loads(out)
    assert "body" not in data[0]
    assert "full article body text" not in out
    assert data[0]["summary"] == "the summary"


def test_recall_filter_arguments(fake_store):
    _run_recall(
        "--topic",
        "Arctic security",
        "--since",
        "2026-07-01",
        "--ccir",
        "PIR-2",
        "--bucket",
        "keep",
        "--limit",
        "10",
        fake_store=fake_store,
    )
    call = fake_store.recall_items.call_args
    assert call.kwargs["ccir"] == "PIR-2"
    assert call.kwargs["bucket"] == "keep"
    assert call.kwargs["limit"] == 10
    assert call.kwargs["since"] is not None


def test_recall_no_results(capsys, fake_store):
    fake_store.recall_items.return_value = []
    _run_recall("--topic", "xyz", fake_store=fake_store)
    out = capsys.readouterr().out
    assert "No results found" in out


def test_recall_synthesis_calls_llm(capsys, fake_store):
    _run_recall("--topic", "Arctic security", "--synthesize", fake_store=fake_store, fake_llm="synthesis text")
    out = capsys.readouterr().out
    assert "## Synthesis" in out
    assert "synthesis text" in out


def test_recall_since_relative(fake_store):
    _run_recall("--topic", "Arctic security", "--since", "7d", fake_store=fake_store)
    call = fake_store.recall_items.call_args
    assert call.kwargs["since"] is not None
    assert call.kwargs["since"] < datetime.datetime.now(tz=datetime.timezone.utc)


def test_recall_obsidian_output(tmp_path, capsys, fake_store):
    vault = tmp_path / "vault"
    _run_recall("--topic", "Arctic security", "--obsidian", str(vault), fake_store=fake_store)
    out = capsys.readouterr().out
    assert "Obsidian note written to" in out
    notes = list(vault.glob("recall-Arctic-security-*.md"))
    assert len(notes) == 1
    text = notes[0].read_text(encoding="utf-8")
    parts = text.split("---", 2)
    assert len(parts) >= 3, "Front matter must be delimited by ---"
    assert '"topic": "Arctic security"' in parts[1]
    assert "Arctic security article" in text
