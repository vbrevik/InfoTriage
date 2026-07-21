"""tests/test_wiki_generator.py — Phase 10 Wiki-LLM generator tests."""

from __future__ import annotations

import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

import generator
from generator import (
    CITATION_INSTRUCTION,
    CONTRADICTION_INSTRUCTION,
    CROSS_LANGUAGE_INSTRUCTION,
    WikiGenerator,
)


@pytest.fixture
def fake_store():
    store = MagicMock()
    store.recall_items.return_value = [
        {
            "item_id": "id1",
            "title": "Arctic security article",
            "source": "NRK",
            "url": "https://example.com/1",
            "ccir": "PIR-2",
            "score": 8,
            "similarity": 0.89,
            "lang": "en",
        },
        {
            "item_id": "id2",
            "title": "NATO summit",
            "source": "Aftenposten",
            "url": "https://example.com/2",
            "ccir": "PIR-3",
            "score": 7,
            "similarity": 0.85,
            "lang": "en",
        },
    ]
    return store


@pytest.fixture
def mock_embed():
    return lambda text: [0.1] * 1024


@pytest.fixture
def mock_llm():
    return lambda messages: "This is a synthesized answer with [id1] and [id2]."


def test_wiki_generator_writes_obsidian_page(
    tmp_path, fake_store, mock_embed, mock_llm
):
    vault = tmp_path / "vault"
    gen = WikiGenerator(
        fake_store,
        vault,
        embed=mock_embed,
        llm=mock_llm,
    )
    path = gen.generate_page("NATO")

    assert path.exists()
    assert path.parent == vault / "wiki" / "auto"
    text = path.read_text(encoding="utf-8")
    assert "---" in text
    assert "NATO" in text
    assert "This is a synthesized answer" in text
    assert "Arctic security article" in text
    assert "https://example.com/1" in text


def test_wiki_generator_flags_missing_language(tmp_path, fake_store, mock_embed):
    fake_store.recall_items.return_value = [
        {
            "item_id": "id1",
            "title": "Russian report",
            "source": "TASS",
            "url": "https://example.com/1",
            "ccir": "PIR-1",
            "score": 8,
            "similarity": 0.89,
            "lang": "ru",
        },
    ]
    # LLM output omits the Russian citation
    llm_no_ru = lambda messages: "This only cites English sources."
    gen = WikiGenerator(fake_store, tmp_path / "vault", embed=mock_embed, llm=llm_no_ru)
    path = gen.generate_page("Russia")
    text = path.read_text(encoding="utf-8")
    assert "Verification Flag" in text
    assert "ru" in text


def test_wiki_generator_handles_empty_corpus(tmp_path, fake_store, mock_embed):
    fake_store.recall_items.return_value = []
    llm_stub = lambda messages: "No sources available."
    gen = WikiGenerator(fake_store, tmp_path / "vault", embed=mock_embed, llm=llm_stub)
    path = gen.generate_page("Unknown topic")
    text = path.read_text(encoding="utf-8")
    assert "Unknown topic" in text
    assert "No sources available" in text


def test_worker_run_once(tmp_path, fake_store, mock_embed, mock_llm):
    fake_store.get_active_entities.return_value = [
        {"entity_id": "e1", "name": "NATO", "link_count": 10},
        {"entity_id": "e2", "name": "Ukraine", "link_count": 5},
    ]
    from wiki_worker import run_once

    paths = run_once(
        fake_store,
        tmp_path / "vault",
        top_n=2,
        embed=mock_embed,
        llm=mock_llm,
    )
    assert len(paths) == 2
    for path in paths:
        assert path.exists()
    fake_store.get_active_entities.assert_called_once_with(limit=2)


def test_worker_run_once_skips_entities_without_name(tmp_path, mock_embed, mock_llm):
    store = MagicMock()
    store.get_active_entities.return_value = [
        {"entity_id": "e1", "name": "", "link_count": 10},
        {"entity_id": "e2", "link_count": 5},
    ]
    from wiki_worker import run_once

    paths = run_once(
        store, tmp_path / "vault", top_n=10, embed=mock_embed, llm=mock_llm
    )
    assert paths == []
    store.get_active_entities.assert_called_once_with(limit=10)


@pytest.mark.asyncio
async def test_wiki_worker_health_endpoint(tmp_path):
    from wiki_worker import _handle_health

    reader = AsyncMock()
    writer = AsyncMock()
    writer.write = MagicMock()
    writer.drain = AsyncMock()
    writer.close = MagicMock()

    await _handle_health(reader, writer)

    writer.write.assert_called_once()
    response = writer.write.call_args[0][0]
    assert b"HTTP/1.1 200 OK" in response
    assert b"OK" in response


@pytest.mark.asyncio
async def test_wiki_worker_event_driven_generates_page(tmp_path, mock_embed, mock_llm):
    from wiki_worker import _on_verdict_ready

    store = MagicMock()
    store.get_active_entities.return_value = [
        {"entity_id": "e1", "name": "NATO", "link_count": 10},
    ]

    class FakeMessage:
        def __init__(self):
            self.headers = {"item_id": "item-123"}
            self.processed = False

        def process(self):
            class CM:
                async def __aenter__(self2):
                    return self2

                async def __aexit__(self2, *args):
                    return None

            return CM()

    message = FakeMessage()
    await _on_verdict_ready(
        message, store, tmp_path / "vault", top_n=1, embed=mock_embed, llm=mock_llm
    )

    store.get_active_entities.assert_called_once_with(limit=1)
    assert (tmp_path / "vault" / "wiki" / "auto" / "nato.md").exists()


def test_verify_language_coverage_passes_when_all_cited():
    items = [
        {"item_id": "i1", "lang": "en"},
        {"item_id": "i2", "lang": "ru"},
    ]
    text = "Summary [i1] and also [i2]."
    assert generator.verify_language_coverage(items, text) == []


def test_verify_language_coverage_finds_missing_language():
    items = [
        {"item_id": "i1", "lang": "en"},
        {"item_id": "i2", "lang": "ru"},
    ]
    text = "Summary [i1]."
    assert generator.verify_language_coverage(items, text) == ["ru"]


def test_build_prompt_requires_citations():
    gen = WikiGenerator(MagicMock(), "/vault")
    prompt = gen.build_prompt("NATO", [])
    assert CITATION_INSTRUCTION in prompt


def test_build_prompt_requires_cross_language_synthesis():
    gen = WikiGenerator(MagicMock(), "/vault")
    prompt = gen.build_prompt("NATO", [])
    assert CROSS_LANGUAGE_INSTRUCTION in prompt


def test_build_prompt_requires_contradiction_flagging():
    gen = WikiGenerator(MagicMock(), "/vault")
    prompt = gen.build_prompt("NATO", [])
    assert CONTRADICTION_INSTRUCTION in prompt


def test_build_prompt_includes_subject_and_source_items():
    gen = WikiGenerator(MagicMock(), "/vault")
    items = [
        {"item_id": "id1", "title": "Arctic security", "source": "NRK", "lang": "en"},
        {
            "item_id": "id2",
            "title": "NATO summit",
            "source": "Aftenposten",
            "lang": "no",
        },
    ]
    prompt = gen.build_prompt("NATO", items)
    assert "Topic: NATO" in prompt
    assert "[item_id: id1]" in prompt
    assert "Arctic security" in prompt
    assert "Aftenposten" in prompt


def test_write_wiki_page_creates_new_file(tmp_path):
    from generator import write_wiki_page

    path = write_wiki_page(
        "NATO",
        "# NATO\n\nBody content",
        {"title": "NATO", "subject": "NATO"},
        tmp_path / "vault",
    )
    assert path.exists()
    assert path == tmp_path / "vault" / "wiki" / "auto" / "nato.md"
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert "title: NATO" in text
    assert "Body content" in text


def test_write_wiki_page_preserves_operator_frontmatter_keys(tmp_path):
    from generator import write_wiki_page

    vault = tmp_path / "vault"
    path = write_wiki_page(
        "NATO",
        "# NATO\n\nOriginal body",
        {"title": "NATO", "subject": "NATO", "generated_at": "2024-01-01T00:00:00"},
        vault,
    )
    # Simulate operator adding a custom frontmatter key
    existing = path.read_text(encoding="utf-8")
    path.write_text(
        existing.replace("title: NATO", "title: NATO\nreviewed_by: analyst-a"),
        encoding="utf-8",
    )

    updated_path = write_wiki_page(
        "NATO",
        "# NATO\n\nUpdated body",
        {"title": "NATO", "subject": "NATO", "generated_at": "2024-02-01T00:00:00"},
        vault,
    )
    assert updated_path == path
    text = updated_path.read_text(encoding="utf-8")
    assert "reviewed_by: analyst-a" in text
    assert "2024-02-01T00:00:00" in text
    assert "Updated body" in text
    assert "Original body" not in text


def test_write_wiki_page_overwrites_corrupt_frontmatter(tmp_path):
    from generator import write_wiki_page

    vault = tmp_path / "vault"
    wiki_dir = vault / "wiki" / "auto"
    wiki_dir.mkdir(parents=True, exist_ok=True)
    path = wiki_dir / "nato.md"
    path.write_text("---\nnot yaml: [unclosed\n---\n\nOld body", encoding="utf-8")

    updated_path = write_wiki_page(
        "NATO",
        "# NATO\n\nNew body",
        {"title": "NATO", "subject": "NATO"},
        vault,
    )
    assert updated_path == path
    text = updated_path.read_text(encoding="utf-8")
    assert "New body" in text
    assert "Old body" not in text
    assert "title: NATO" in text
