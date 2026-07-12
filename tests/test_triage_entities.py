#!/usr/bin/env python3
"""tests/test_triage_entities.py — unit tests for apps/triage/entities.py (Phase 8)."""
import pytest

from apps.triage.entities import (
    extract_mentions,
    normalize_name,
    embed_entity_name,
    resolve_entities,
)


def test_extract_mentions_finds_proper_nouns():
    text = "NATO plans a meeting in Oslo. European Union officials will attend."
    mentions = extract_mentions(text)
    assert "NATO" in mentions
    assert "Oslo" in mentions
    assert "European Union" in mentions


def test_extract_mentions_handles_multi_word_phrases():
    text = "The Ministry of Defence met in Washington. Prime Minister Smith attended."
    mentions = extract_mentions(text)
    assert "Ministry of Defence" in mentions
    assert "Washington" in mentions
    assert "Prime Minister Smith" in mentions


def test_extract_mentions_includes_known_topics():
    text = "Norway and NATO discussed the situation."
    mentions = extract_mentions(text)
    assert "NATO" in mentions
    assert "Norway" in mentions


def test_extract_mentions_filters_stop_words():
    text = "This is a Test. There are Words here."
    mentions = extract_mentions(text)
    # "This", "There", "Words" should not be treated as entities.
    assert "This" not in mentions
    assert "There" not in mentions
    assert "Words" not in mentions


def test_normalize_name_lowercases_and_strips():
    assert normalize_name("  NATO ") == "nato"
    assert normalize_name("European Union!") == "european union"
    assert normalize_name("NATO's") == "nato"


def test_embed_entity_name_prefixes_with_query():
    calls = []

    def fake_embed(text):
        calls.append(text)
        return [0.1] * 1024

    result = embed_entity_name("nato", "en", fake_embed)
    assert result == [0.1] * 1024
    assert calls == ["query: nato"]


def test_embed_entity_name_returns_none_on_failure():
    def failing_embed(text):
        raise RuntimeError("model offline")

    result = embed_entity_name("nato", "en", failing_embed)
    assert result is None


def test_resolve_entities_stores_and_links():
    class FakeStore:
        def __init__(self):
            self.entities = {}
            self.links = []
            self._next_id = 1

        def put_entity(self, name, name_norm, lang, type, embedding):
            key = (name_norm, lang)
            if key not in self.entities:
                self.entities[key] = {
                    "id": str(self._next_id),
                    "name": name,
                    "name_norm": name_norm,
                    "lang": lang,
                    "type": type,
                    "embedding": embedding,
                }
                self._next_id += 1
            return self.entities[key]["id"]

        def link_entity(self, entity_id, item_id, mention, lang):
            self.links.append({
                "entity_id": entity_id,
                "item_id": item_id,
                "mention": mention,
                "lang": lang,
            })

    store = FakeStore()

    def fake_embed(text):
        return [0.5] * 1024

    resolve_entities("item-1", "NATO meets in Oslo.", "en", store, fake_embed)

    assert len(store.entities) == 2
    assert len(store.links) == 2
    assert any(l["mention"] == "NATO" for l in store.links)
    assert any(l["mention"] == "Oslo" for l in store.links)
