#!/usr/bin/env python3
"""entities.py — LLM-based entity extraction, embedding, and linking (Phase 8).

Wave 2: named entities are extracted by the local qwen36 chat model (typed
PER/ORG/LOC/GPE/MISC), replacing the earlier regex/known-topics heuristic. The
extracted names are canonicalised and linked to items via the mE5-large
embedding endpoint (same threshold logic as before).

Public API:
    extract_entities(text: str, lang: str, chat_fn) -> list[dict]
    normalize_name(name: str) -> str
    embed_entity_name(name: str, lang: str, embed_fn) -> list[float] | None
    resolve_entities(item_id, text, lang, store, embed_fn, chat_fn) -> None
    resolve_entities_async(item_id, text, lang, store, embed_fn, chat_fn) -> None
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import cast


log = logging.getLogger(__name__)

# Default entity-link cosine threshold. Re-validated by
# scripts/validate_entity_threshold.py and documented in
# .planning/phases/999.3-entity-resolution-cross-language-coverage-and-mE5-large-re-validation/999.3-VERDICT.md
LINK_THRESHOLD = 0.85

# Entity types the model may assign; anything else is coerced to MISC.
_ALLOWED_TYPES = {"PER", "ORG", "LOC", "GPE", "MISC"}

# Upper bound on prompt text. Titles + summaries are short; this is a safety cap
# so a pathological body can't blow up the NER call.
_MAX_NER_CHARS = 6000

# NER instruction. Kept model-agnostic and deterministic (temperature 0 upstream);
# the model must reply with ONLY a JSON array so parsing stays robust.
_NER_INSTRUCTION = (
    "You are a named-entity recognition engine for an intelligence-triage "
    "pipeline. Extract the distinct named entities from the text below. For each, "
    "give its canonical surface form and one type from: PER (person), ORG "
    "(organization), LOC (physical location), GPE (country/city/geopolitical "
    "entity), MISC (any other named entity). Ignore common nouns, dates, numbers, "
    "and pronouns. Preserve each entity's original language and script. "
    'Respond with ONLY a JSON array of objects {{"name": "...", "type": '
    '"PER|ORG|LOC|GPE|MISC"}} and no other text. The text language is {lang}."'
)


def extract_entities(text: str, lang: str, chat_fn) -> list[dict]:
    """Extract typed named entities from text using the local chat LLM (qwen36).

    Args:
        text: the source text (title + summary in production).
        lang: ISO language hint passed to the model ("en", "no", "ru", ...).
        chat_fn: callable ``(messages, max_tokens=...) -> str`` returning the raw
            assistant content (see triage_score.llm). Injected for testability.

    Returns:
        A list of ``{"name": str, "type": str}`` dicts (types in _ALLOWED_TYPES),
        de-duplicated by lowercased name. ANY failure — LLM error or unparseable
        output — returns ``[]`` and logs a WARNING. Entity resolution is
        best-effort and must never raise into the worker.
    """
    text = (text or "").strip()
    if not text:
        return []
    prompt = (
        _NER_INSTRUCTION.format(lang=lang or "unknown")
        + "\n\nText:\n"
        + text[:_MAX_NER_CHARS]
    )
    try:
        raw = chat_fn([{"role": "user", "content": prompt}], max_tokens=800)
    except Exception as exc:  # pragma: no cover - network/model failure path
        log.warning("entity NER LLM call failed: %s", exc)
        return []
    return _parse_entities(raw)


def _parse_entities(raw: str) -> list[dict]:
    """Parse an LLM NER response into validated ``{name, type}`` dicts.

    Tolerant of markdown code fences and surrounding prose: it isolates the
    outermost JSON array. Returns ``[]`` (with a WARNING) on anything it cannot
    parse into a list of name-bearing objects.
    """
    if not raw:
        return []
    s = raw.strip()
    # Strip ```json ... ``` fences if the model wrapped its answer.
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\n?", "", s)
        s = re.sub(r"\n?```$", "", s).strip()
    # Isolate the outermost JSON array.
    start, end = s.find("["), s.rfind("]")
    if start == -1 or end == -1 or end < start:
        log.warning("entity NER returned no JSON array: %r", raw[:120])
        return []
    try:
        data = json.loads(s[start : end + 1])
    except Exception as exc:
        log.warning("entity NER JSON parse failed: %s", exc)
        return []
    if not isinstance(data, list):
        return []
    out: list[dict] = []
    seen: set[str] = set()
    for entry in data:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        name = name.strip()
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        etype = entry.get("type")
        etype = etype if etype in _ALLOWED_TYPES else "MISC"
        out.append({"name": name, "type": etype})
    return out


def normalize_name(name: str) -> str:
    """Normalise an entity surface form to a canonical key.

    Rules:
      - lower-case
      - strip leading/trailing punctuation
      - collapse whitespace
      - remove possessive 's
    """
    name = name.strip().lower()
    name = re.sub(r"[^\w\s'-]+", "", name)
    name = name.rstrip("'s")
    name = re.sub(r"\s+", " ", name).strip()
    return name


def embed_entity_name(
    name: str,
    lang: str,
    embed_fn,
) -> list[float] | None:
    """Embed a canonical entity name using the mE5-large endpoint.

    mE5-large expects a ``query:`` prefix for asymmetric retrieval tasks.  If the
    embedding call fails, log a warning and return None so the entity can still be
    stored without a vector.
    """
    try:
        # mE5-large asymmetric retrieval convention.
        prefixed = f"query: {name}"
        return cast(list[float] | None, embed_fn(prefixed))
    except Exception as exc:  # pragma: no cover - network/model failure path
        log.warning("entity embedding failed for %r: %s", name, exc)
        return None


def _find_or_create_entity(
    mention: str,
    lang: str,
    store,
    embed_fn,
    entity_type: str | None = None,
) -> str | None:
    """Return an entity id for mention, creating a new entity if necessary.

    Resolution order:
      1. Exact (name_norm, lang) match.
      2. Similar existing entity by mE5-large cosine similarity >= LINK_THRESHOLD.
      3. Create a new entity (with its NER type, when known).

    Returns None for mentions that normalise to an empty string.
    """
    name_norm = normalize_name(mention)
    if not name_norm:
        return None

    existing = store.get_entity_by_name_norm(name_norm, lang)
    if existing is not None:
        return cast(str, existing["id"])

    embedding = embed_entity_name(name_norm, lang, embed_fn)

    if embedding is not None:
        similar = store.find_similar_entity(embedding, LINK_THRESHOLD)
        if similar is not None:
            return cast(str, similar["entity_id"])

    return cast(
        str,
        store.put_entity(
            name=mention,
            name_norm=name_norm,
            lang=lang,
            type=entity_type,
            embedding=embedding,
        ),
    )


def resolve_entities(
    item_id: str,
    text: str,
    lang: str,
    store,
    embed_fn,
    chat_fn,
) -> None:
    """Extract entities from text (LLM NER), persist them, and link to item_id.

    This is the synchronous core; worker.py calls it via asyncio.to_thread.
    """
    for entity in extract_entities(text, lang, chat_fn):
        name = entity.get("name")
        if not name:
            continue
        entity_id = _find_or_create_entity(
            name, lang, store, embed_fn, entity.get("type")
        )
        if entity_id is not None:
            store.link_entity(entity_id, item_id, name, lang)


async def resolve_entities_async(
    item_id: str,
    text: str,
    lang: str,
    store,
    embed_fn,
    chat_fn,
) -> None:
    """Async wrapper around resolve_entities for the async worker loop."""
    await asyncio.to_thread(
        resolve_entities, item_id, text, lang, store, embed_fn, chat_fn
    )
