#!/usr/bin/env python3
"""tests/test_entities.py — unit tests for LLM-based entity extraction, embedding, and linking (Phase 8, Wave 2).

All I/O (LLM chat, embedding HTTP) is mocked; the tests exercise the parsing,
normalisation, linking logic, and the orchestrator.
"""
from __future__ import annotations

import asyncio
import json
import logging
from unittest.mock import Mock

import pytest

from store import InMemoryStore
from apps.triage.entities import (
    LINK_THRESHOLD,
    _parse_entities,
    embed_entity_name,
    extract_entities,
    normalize_name,
    resolve_entities,
    resolve_entities_async,
)


# ---------------------------------------------------------------------------
# _parse_entities — JSON parsing, fences, type coercion
# ---------------------------------------------------------------------------


class TestParseEntities:
    def test_parses_clean_array(self):
        raw = '[{"name": "NATO", "type": "ORG"}, {"name": "Putin", "type": "PER"}]'
        out = _parse_entities(raw)
        assert len(out) == 2
        assert {"name": "NATO", "type": "ORG"} in out
        assert {"name": "Putin", "type": "PER"} in out

    def test_parses_markdown_fence(self):
        raw = '```json\n[{"name": "Kyiv", "type": "GPE"}]\n```'
        out = _parse_entities(raw)
        assert len(out) == 1
        assert out[0]["name"] == "Kyiv"

    def test_parses_empty_array(self):
        assert _parse_entities("[]") == []

    def test_returns_empty_on_no_json(self):
        assert _parse_entities("no json here") == []

    def test_returns_empty_on_malformed_json(self):
        assert _parse_entities('[{"name": "NATO", "type": ORG}]') == []

    def test_returns_empty_on_non_list(self):
        assert _parse_entities('{"name": "NATO"}') == []

    def test_deduuplicates_by_lowercase_name(self):
        raw = (
            '[{"name": "NATO", "type": "ORG"}, '
            '{"name": "nato", "type": "ORG"}, '
            '{"name": "НАТО", "type": "ORG"}]'
        )
        out = _parse_entities(raw)
        # NATO and nato share a lowercased key → deduped; НАТО is distinct.
        names = {e["name"] for e in out}
        assert len(out) == 2
        assert "НАТО" in names

    def test_coerces_unknown_type_to_misc(self):
        raw = '[{"name": "MysteryThing", "type": "FAKE"}]'
        out = _parse_entities(raw)
        assert out[0]["type"] == "MISC"

    def test_allows_all_valid_types(self):
        raw = (
            '[{"name": "A", "type": "PER"}, '
            '{"name": "B", "type": "ORG"}, '
            '{"name": "C", "type": "LOC"}, '
            '{"name": "D", "type": "GPE"}, '
            '{"name": "E", "type": "MISC"}]'
        )
        out = _parse_entities(raw)
        assert len(out) == 5

    def test_skips_empty_name(self):
        raw = '[{"name": "", "type": "ORG"}, {"name": "Valid", "type": "PER"}]'
        out = _parse_entities(raw)
        assert len(out) == 1
        assert out[0]["name"] == "Valid"

    def test_skips_non_dict_entries(self):
        raw = '["NATO", {"name": "Putin", "type": "PER"}]'
        out = _parse_entities(raw)
        assert len(out) == 1

    def test_returns_empty_on_none(self):
        assert _parse_entities("") == []
        assert _parse_entities(None) == []


# ---------------------------------------------------------------------------
# extract_entities — LLM integration, graceful failure
# ---------------------------------------------------------------------------


class TestExtractEntities:
    def test_calls_chat_fn_with_prompt(self):
        chat = Mock(return_value='[{"name": "NATO", "type": "ORG"}]')
        out = extract_entities("NATO announced defence spending", "en", chat)
        assert len(out) == 1
        assert out[0]["name"] == "NATO"
        # Prompt must contain the language hint.
        prompt = chat.call_args[0][0][0]["content"]
        assert "en" in prompt

    def test_truncates_text_to_max_chars(self):
        """extract_entities caps the prompt at _MAX_NER_CHARS."""
        chat = Mock(return_value="[]")
        extract_entities("A " * 10000, "en", chat)
        prompt = chat.call_args[0][0][0]["content"]
        # Instruction text ~500 chars + "Text:\n" + truncated 6000 chars.
        assert len(prompt) <= 6800

    def test_returns_empty_on_empty_text(self):
        assert extract_entities("", "en", lambda *_: "") == []
        assert extract_entities(None, "en", lambda *_: "") == []

    def test_returns_empty_on_llm_failure(self):
        chat = Mock(side_effect=RuntimeError("model unavailable"))
        assert extract_entities("some text", "en", chat) == []

    def test_returns_empty_on_malformed_llm_response(self):
        chat = Mock(return_value="garbage not json")
        assert extract_entities("some text", "en", chat) == []

    def test_handles_russian_text(self):
        chat = Mock(
            return_value='[{"name": "НАТО", "type": "ORG"}, {"name": "Путин", "type": "PER"}]'
        )
        out = extract_entities("НАТО провёл встречу с Путиным", "ru", chat)
        assert len(out) == 2

    def test_lang_hint_passed_through(self):
        chat = Mock(return_value="[]")
        extract_entities("test", "no", chat)
        prompt = chat.call_args[0][0][0]["content"]
        assert "no" in prompt


# ---------------------------------------------------------------------------
# normalize_name
# ---------------------------------------------------------------------------


class TestNormalizeName:
    def test_lowercase(self):
        assert normalize_name("NATO") == "nato"

    def test_strips_punctuation(self):
        assert normalize_name("NATO!") == "nato"

    def test_collapse_whitespace(self):
        assert normalize_name("New  York") == "new york"

    def test_removes_possessive(self):
        assert normalize_name("America's") == "america"

    def test_handles_unicode(self):
        assert normalize_name("Москва") == "москва"


# ---------------------------------------------------------------------------
# embed_entity_name — mocked embedding call
# ---------------------------------------------------------------------------


class TestEmbedEntityName:
    def test_calls_embed_fn_with_query_prefix(self):
        embed = Mock(return_value=[0.1] * 1024)
        embed_entity_name("NATO", "en", embed)
        embed.assert_called_once_with("query: NATO")

    def test_returns_none_on_failure(self, caplog):
        embed = Mock(side_effect=ConnectionError("offline"))
        with caplog.at_level(logging.WARNING, logger="triage.entities"):
            result = embed_entity_name("NATO", "en", embed)
        assert result is None
        assert "embedding failed" in caplog.text

    def test_returns_vector_on_success(self):
        vec = [0.01] * 1024
        embed = Mock(return_value=vec)
        result = embed_entity_name("Test", "en", embed)
        assert result == vec


# ---------------------------------------------------------------------------
# resolve_entities — InMemory integration (no real LLM/embedding needed)
# ---------------------------------------------------------------------------


class TestResolveEntities:
    @pytest.fixture
    def store(self, tmp_path):
        return InMemoryStore(blob_root=tmp_path / "blobs")

    def _chat(self, _messages, max_tokens=800):
        """Mock LLM that returns a fixed entity set."""
        return json.dumps(
            [
                {"name": "NATO", "type": "ORG"},
                {"name": "Putin", "type": "PER"},
            ]
        )

    def _embed(self, text):
        """Mock embedder: deterministic vector derived from text hash."""
        h = hash(text) & 0xFFFFFFFF
        vec = [(h >> (i * 8)) & 0xFF for i in range(32)] + [0.0] * 992
        # Normalise to unit-ish vector.
        mag = sum(v * v for v in vec) ** 0.5 or 1.0
        return [v / mag for v in vec]

    def test_creates_and_links_entities(self, store):
        store.put_entity(
            name="NATO", name_norm="nato", lang="en", type="ORG", embedding=None
        )
        resolve_entities(
            "item-001",
            "NATO and Putin met in Oslo",
            "en",
            store,
            self._embed,
            self._chat,
        )
        links = store.get_entity_links("item-001")
        assert len(links) == 2
        names = {e["name"] for e in links}
        assert "NATO" in names
        assert "Putin" in names

    def test_uses_exact_name_norm_match_first(self, store):
        """If (name_norm, lang) exists, no new entity is created."""
        existing_id = store.put_entity(
            name="NATO HQ",
            name_norm="nato",
            lang="en",
            type="ORG",
            embedding=None,
        )
        resolve_entities(
            "item-001",
            "NATO announced something",
            "en",
            store,
            self._embed,
            self._chat,
        )
        links = store.get_entity_links("item-001")
        # NATO should link to the existing entity_id.
        assert any(l["entity_id"] == existing_id for l in links)

    def test_creates_new_entity_when_no_match(self, store):
        resolve_entities(
            "item-001",
            "Bellingcat published an investigation",
            "en",
            store,
            self._embed,
            self._chat,
        )
        links = store.get_entity_links("item-001")
        assert len(links) > 0
        # Each entity should have been created.
        for link in links:
            entity = store.get_entity(link["entity_id"])
            assert entity is not None
            assert entity["name"]

    def test_ignores_empty_entity_names(self, store):
        chat = Mock(return_value=json.dumps([{"name": "", "type": "ORG"}]))
        resolve_entities("item-001", "text", "en", store, self._embed, chat)
        links = store.get_entity_links("item-001")
        assert len(links) == 0

    def test_exception_swallows_cleanly(self, store):
        """resolve_entities should log but not raise on LLM/embed failures."""
        chat = Mock(side_effect=RuntimeError("boom"))
        # Should NOT raise.
        resolve_entities("item-001", "text", "en", store, self._embed, chat)
        # No crash — that's the test.

    def test_resolve_entities_async_propagates(self):
        """resolve_entities_async is a thin wrapper around asyncio.to_thread."""
        store = InMemoryStore(blob_root="/tmp/test_async")
        chat = Mock(return_value=json.dumps([{"name": "AsyncTest", "type": "MISC"}]))

        def _embed(text):
            h = hash(text) & 0xFFFFFFFF
            vec = [(h >> (i * 8)) & 0xFF for i in range(32)] + [0.0] * 992
            mag = sum(v * v for v in vec) ** 0.5 or 1.0
            return [v / mag for v in vec]

        asyncio.run(
            resolve_entities_async("item-001", "async text", "en", store, _embed, chat)
        )
        links = store.get_entity_links("item-001")
        assert len(links) == 1
        assert links[0]["name"] == "AsyncTest"
