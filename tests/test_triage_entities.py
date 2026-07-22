#!/usr/bin/env python3
"""tests/test_triage_entities.py — unit tests for apps/triage/entities.py (Phase 8).

Wave 2: NER is now LLM-based. Tests inject a fake ``chat_fn`` (mirroring
triage_score.llm's ``(messages, max_tokens) -> str`` contract) so no live model
is needed.
"""
import json
import math

import pytest

from apps.triage.entities import (
    _parse_entities,
    embed_entity_name,
    extract_entities,
    normalize_name,
    resolve_entities,
)


# --- fake chat_fn -------------------------------------------------------------

# Surface forms the fake NER "recognises" in a prompt, with their types.
_KNOWN = [
    ("European Union", "ORG"),
    ("NATO", "ORG"),
    ("Oslo", "GPE"),
    ("НАТО", "ORG"),
    ("Осло", "GPE"),
    ("Washington", "GPE"),
]


def fake_chat(messages, max_tokens=800):
    """Return a JSON array of the known entities present in the prompt text."""
    content = messages[0]["content"]
    found = [{"name": s, "type": t} for s, t in _KNOWN if s in content]
    return json.dumps(found)


# --- extract_entities / _parse_entities ---------------------------------------


def test_extract_entities_parses_typed_json():
    text = "NATO plans a meeting in Oslo. European Union officials will attend."
    ents = extract_entities(text, "en", fake_chat)
    names = {e["name"] for e in ents}
    assert {"NATO", "Oslo", "European Union"} <= names
    by_name = {e["name"]: e["type"] for e in ents}
    assert by_name["NATO"] == "ORG"
    assert by_name["Oslo"] == "GPE"


def test_extract_entities_cross_language_preserves_script():
    ents = extract_entities("НАТО встреча в Осло.", "ru", fake_chat)
    names = {e["name"] for e in ents}
    assert "НАТО" in names and "Осло" in names


def test_extract_entities_empty_input_skips_llm():
    called = []

    def spy(messages, max_tokens=800):
        called.append(1)
        return "[]"

    assert extract_entities("", "en", spy) == []
    assert extract_entities("   ", "en", spy) == []
    assert called == []  # no LLM call for empty text


def test_extract_entities_llm_error_returns_empty():
    def boom(messages, max_tokens=800):
        raise RuntimeError("model offline")

    assert extract_entities("NATO in Oslo.", "en", boom) == []


def test_extract_entities_malformed_json_returns_empty():
    assert (
        extract_entities("x", "en", lambda m, max_tokens=800: "not json at all") == []
    )
    assert (
        extract_entities("x", "en", lambda m, max_tokens=800: '{"name": "NATO"}') == []
    )


def test_parse_entities_strips_code_fences():
    raw = '```json\n[{"name": "NATO", "type": "ORG"}]\n```'
    out = _parse_entities(raw)
    assert out == [{"name": "NATO", "type": "ORG"}]


def test_parse_entities_ignores_prose_around_array():
    raw = 'Here are the entities:\n[{"name": "Oslo", "type": "GPE"}]\nDone.'
    assert _parse_entities(raw) == [{"name": "Oslo", "type": "GPE"}]


def test_parse_entities_coerces_unknown_type_and_dedups():
    raw = json.dumps(
        [
            {"name": "NATO", "type": "WEAPON"},  # unknown -> MISC
            {"name": "nato", "type": "ORG"},  # dup (case-insensitive) -> dropped
            {"name": "", "type": "ORG"},  # empty name -> dropped
            {"type": "ORG"},  # no name -> dropped
            "garbage",  # non-dict -> dropped
        ]
    )
    out = _parse_entities(raw)
    assert out == [{"name": "NATO", "type": "MISC"}]


def test_parse_entities_empty_and_nonlist():
    assert _parse_entities("") == []
    assert _parse_entities("[]") == []
    assert _parse_entities('{"name": "NATO"}') == []


# --- normalize_name / embed_entity_name ---------------------------------------


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


# --- resolve_entities (FakeStore) ---------------------------------------------


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
        if "nato" in text.lower():
            return [1.0] + [0.0] * 1023
        if "oslo" in text.lower():
            return [0.0, 1.0] + [0.0] * 1022
        return [0.5] * 1024

    resolve_entities(
        "item-1", "NATO meets in Oslo.", "en", store, fake_embed, fake_chat
    )

    assert len(store.entities) == 2
    assert len(store.links) == 2
    assert any(l["mention"] == "NATO" for l in store.links)
    assert any(l["mention"] == "Oslo" for l in store.links)
    # NER type is persisted on the created entity.
    assert store.entities[("nato", "en")]["type"] == "ORG"


def test_resolve_entities_links_similar_cross_language_entity():
    """A Russian mention similar to an existing English entity links to it."""
    store = FakeStore()

    def fake_embed(text):
        lowered = text.lower()
        if "nato" in lowered or "нато" in lowered:
            return [1.0] + [0.0] * 1023
        if "осло" in lowered or "oslo" in lowered:
            return [0.0, 1.0] + [0.0] * 1022
        return [0.5] * 1024

    resolve_entities(
        "item-en", "NATO summit in Oslo.", "en", store, fake_embed, fake_chat
    )
    assert len(store.entities) == 2

    resolve_entities("item-ru", "НАТО в Осло.", "ru", store, fake_embed, fake_chat)

    nato_entities = [e for e in store.entities.values() if "nato" in e["name_norm"]]
    assert len(nato_entities) == 1
    assert nato_entities[0]["lang"] == "en"

    ru_links = [l for l in store.links if l["item_id"] == "item-ru"]
    nato_link = next((l for l in ru_links if l["mention"] == "НАТО"), None)
    assert nato_link is not None
    assert nato_link["entity_id"] == nato_entities[0]["id"]


def test_resolve_entities_exact_match_takes_precedence_over_similarity():
    """If (name_norm, lang) exists, use it even if a similar entity exists."""
    store = FakeStore()

    def fake_embed(text):
        return [1.0] + [0.0] * 1023

    resolve_entities("item-1", "NATO statement.", "en", store, fake_embed, fake_chat)
    entity_id_1 = store.entities[("nato", "en")]["id"]

    resolve_entities("item-2", "NATO summit.", "en", store, fake_embed, fake_chat)
    entity_id_2 = next(l["entity_id"] for l in store.links if l["item_id"] == "item-2")
    assert entity_id_1 == entity_id_2
    assert len(store.entities) == 1
