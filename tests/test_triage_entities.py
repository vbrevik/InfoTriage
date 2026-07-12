#!/usr/bin/env python3
"""tests/test_triage_entities.py — unit tests for apps/triage/entities.py (Phase 8)."""
import math

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

    def get_entity_by_name_norm(self, name_norm, lang):
        for entity in self.entities.values():
            if entity["name_norm"] == name_norm and entity["lang"] == lang:
                return dict(entity)
        return None

    def find_similar_entity(self, vector, threshold=0.85):
        best_id = None
        best_name = None
        best_sim = -1.0
        for entity in self.entities.values():
            if entity["embedding"] is None:
                continue
            dot = sum(a * b for a, b in zip(vector, entity["embedding"]))
            norm_a = math.sqrt(sum(a * a for a in vector))
            norm_b = math.sqrt(sum(b * b for b in entity["embedding"]))
            if norm_a == 0.0 or norm_b == 0.0:
                continue
            sim = dot / (norm_a * norm_b)
            if sim > best_sim:
                best_sim = sim
                best_id = entity["id"]
                best_name = entity["name"]
        if best_sim >= threshold:
            return {"entity_id": best_id, "name": best_name}
        return None

    def link_entity(self, entity_id, item_id, mention, lang):
        self.links.append(
            {
                "entity_id": entity_id,
                "item_id": item_id,
                "mention": mention,
                "lang": lang,
            }
        )


def test_resolve_entities_stores_and_links():
    store = FakeStore()

    def fake_embed(text):
        # Give distinct vectors so "NATO" and "Oslo" do not collapse via similarity.
        if "nato" in text.lower():
            return [1.0] + [0.0] * 1023
        if "oslo" in text.lower():
            return [0.0, 1.0] + [0.0] * 1022
        return [0.5] * 1024

    resolve_entities("item-1", "NATO meets in Oslo.", "en", store, fake_embed)

    assert len(store.entities) == 2
    assert len(store.links) == 2
    assert any(l["mention"] == "NATO" for l in store.links)
    assert any(l["mention"] == "Oslo" for l in store.links)


def test_resolve_entities_links_similar_cross_language_entity():
    """A Russian mention similar to an existing English entity links to it."""
    store = FakeStore()

    def fake_embed(text):
        # Use a deterministic vector based on the text so "NATO" and "НАТО"
        # produce very similar vectors, while "Oslo" is different.
        lowered = text.lower()
        if "nato" in lowered or "нато" in lowered:
            return [1.0] + [0.0] * 1023
        if "осло" in lowered or "oslo" in lowered:
            return [0.0, 1.0] + [0.0] * 1022
        return [0.5] * 1024

    # First, create the English entity.
    resolve_entities("item-en", "NATO summit in Oslo.", "en", store, fake_embed)
    assert len(store.entities) == 2

    # Then, a Russian article mentions НАТО. It should link to the existing NATO entity.
    resolve_entities("item-ru", "НАТО в Осло.", "ru", store, fake_embed)

    # Only one entity for NATO should exist (English); Russian variant links to it.
    nato_entities = [e for e in store.entities.values() if "nato" in e["name_norm"]]
    assert len(nato_entities) == 1
    assert nato_entities[0]["lang"] == "en"

    # The Russian item should have a link to the English NATO entity.
    ru_links = [l for l in store.links if l["item_id"] == "item-ru"]
    nato_link = next((l for l in ru_links if l["mention"] == "НАТО"), None)
    assert nato_link is not None
    assert nato_link["entity_id"] == nato_entities[0]["id"]


def test_resolve_entities_exact_match_takes_precedence_over_similarity():
    """If (name_norm, lang) exists, use it even if a similar entity exists."""
    store = FakeStore()

    def fake_embed(text):
        return [1.0] + [0.0] * 1023

    resolve_entities("item-1", "NATO statement.", "en", store, fake_embed)
    entity_id_1 = store.entities[("nato", "en")]["id"]

    # A second English NATO mention should hit the exact (name_norm, lang) match.
    resolve_entities("item-2", "NATO summit.", "en", store, fake_embed)
    entity_id_2 = next(l["entity_id"] for l in store.links if l["item_id"] == "item-2")
    assert entity_id_1 == entity_id_2
    assert len(store.entities) == 1
