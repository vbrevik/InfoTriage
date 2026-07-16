#!/usr/bin/env python3
"""entities.py — lightweight entity extraction, embedding, and linking (Phase 8).

Uses a fast regex/heuristic NER (no new dependencies) and the existing
mE5-large embedding endpoint to canonicalise and link entities to items.

Public API:
    extract_mentions(text: str) -> list[str]
    normalize_name(name: str) -> str
    embed_entity_name(name: str, lang: str, embed_fn) -> list[float] | None
    resolve_entities(item_id, text, lang, store, embed_fn) -> None
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import cast


log = logging.getLogger(__name__)

# Default entity-link cosine threshold. Re-validated for mE5-large by
# scripts/validate_entity_threshold.py and documented in
# .planning/phases/999.3-entity-resolution-cross-language-coverage-and-mE5-large-re-validation/999.3-VERDICT.md
# (T*=0.92 adopted: zero false-merges; the earlier 0.85 was validated on bge-m3).
LINK_THRESHOLD = 0.92

# Known topics / system entities that the heuristic should always surface even if
# the regex misses them.  Kept small and domain-agnostic; most entities come from
# the text itself.  Use canonical casing (acronyms stay uppercase).
_KNOWN_TOPICS = {
    "NATO",
    "Norge",
    "Norway",
    "Oslo",
    "Bergen",
    "Tromsø",
    "Stavanger",
    "Trondheim",
    "NATO HQ",
    "Norwegian Defense",
    "Norwegian Armed Forces",
    "Forsvaret",
    "Ukraine",
    "Russia",
    "Putin",
    "Zelensky",
    "Warsaw",
    "Poland",
    "Belarus",
    "China",
    "Beijing",
    "Taiwan",
    "Hong Kong",
    "Diplomatic",
    "America",
    "USA",
    "United States",
    "Washington",
    "Climate",
    "Environment",
    "Green",
    "Sustainable",
    "Renewable",
    "Technology",
    "AI",
    "Artificial Intelligence",
    "Cybersecurity",
    "Security",
    "Ukrainian",
    "Russian",
    "Chinese",
    "American",
    "European",
    "EU",
}

# Words that look like proper nouns but are not entities.
_STOP_WORDS = {
    "the",
    "this",
    "that",
    "these",
    "those",
    "there",
    "where",
    "when",
    "why",
    "how",
    "what",
    "which",
    "who",
    "whose",
    "it",
    "its",
    "they",
    "them",
    "their",
    "i",
    "you",
    "he",
    "she",
    "we",
    "us",
    "our",
    "my",
    "your",
    "his",
    "her",
    "a",
    "an",
    "and",
    "or",
    "but",
    "if",
    "then",
    "than",
    "as",
    "at",
    "by",
    "from",
    "in",
    "on",
    "to",
    "of",
    "with",
    "without",
    "over",
    "under",
    "between",
    "about",
    "after",
    "before",
    "during",
    "within",
    "through",
    "above",
    "below",
    "new",
    "old",
    "good",
    "bad",
    "big",
    "small",
    "long",
    "short",
    "high",
    "low",
    "many",
    "much",
    "more",
    "most",
    "some",
    "any",
    "all",
    "each",
    "every",
    "both",
    "said",
    "says",
    "say",
    "told",
    "made",
    "make",
    "used",
    "use",
    "using",
    "according",
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
    # Norwegian common words (capitalised forms may be mistaken for entities)
    "det",
    "en",
    "et",
    "og",
    "eller",
    "men",
    "som",
    "at",
    "til",
    "fra",
    "på",
    "av",
    "med",
    "for",
    "i",
    "om",
    "den",
    "de",
    "dette",
    "disse",
    "hans",
    "hennes",
    "deres",
    "vår",
    "min",
    "din",
    "nå",
    "her",
    "da",
    "så",
    "hvis",
    "når",
    "hvor",
    "hva",
    "hvem",
    "hvorfor",
    "hvordan",
    # Russian common words (capitalised forms may be mistaken for entities)
    "в",
    "и",
    "на",
    "по",
    "с",
    "к",
    "о",
    "у",
    "от",
    "для",
    "из",
    "за",
    "под",
    "над",
    "при",
    "через",
    "а",
    "но",
    "или",
    "если",
    "когда",
    "где",
    "кто",
    "что",
    "как",
    "почему",
    "зачем",
    "этот",
    "эта",
    "это",
    "эти",
    "тот",
    "та",
    "то",
    "те",
    "саммит",
    "встреча",
    "конференция",
}

# Character class for entity word bodies: Latin, Norwegian, and Cyrillic.
_WORD_CHARS = r"a-zæøåA-ZÆØÅа-яёА-ЯЁ"

# Capitalised phrase: one or more capitalised words optionally joined by
# lowercase connecting words (e.g. "European Union", "Ministry of Defence").
_ENTITY_RE = re.compile(
    rf"\b[A-ZÆØÅА-ЯЁ][{_WORD_CHARS}]*"
    rf"(?:\s+[A-ZÆØÅА-ЯЁ][{_WORD_CHARS}]+){{0,3}}"
    rf"(?:\s+(?:of|the|&|for|in|on|de|del|di|von|van|da|dos|e)\s+[A-ZÆØÅА-ЯЁ][{_WORD_CHARS}]+)*"
    r"\b",
    re.UNICODE,
)


def extract_mentions(text: str) -> list[str]:
    """Return unique entity-like mentions from text using regex + known topics.

    The heuristic is intentionally lightweight: it finds capitalised phrases and
    supplements them with a small domain topic list.  It avoids adding heavy
    NLP dependencies to the triage container.
    """
    text = text or ""
    text_lower = text.lower()
    mentions: set[str] = set()

    # Known topics first (preserve canonical casing).
    for topic in _KNOWN_TOPICS:
        if topic.lower() in text_lower:
            mentions.add(topic)

    # Regex proper nouns.
    for match in _ENTITY_RE.finditer(text):
        mention = match.group(0).strip()
        # Drop leading articles and trailing punctuation / possessives.
        mention = re.sub(r"^(?:the|a|an)\s+", "", mention, flags=re.IGNORECASE)
        mention = mention.rstrip("'s")
        if not mention:
            continue
        # Filter out stop words and single letters.
        key = mention.lower()
        if key in _STOP_WORDS or len(key) <= 1:
            continue
        mentions.add(mention)

    # Stable order for deterministic tests.
    return sorted(mentions, key=lambda s: s.lower())


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
) -> str | None:
    """Return an entity id for mention, creating a new entity if necessary.

    Resolution order:
      1. Exact (name_norm, lang) match.
      2. Similar existing entity by mE5-large cosine similarity >= LINK_THRESHOLD.
      3. Create a new entity.

    Returns None for mentions that normalise to a stop word or empty string.
    """
    name_norm = normalize_name(mention)
    if not name_norm or name_norm in _STOP_WORDS:
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
            type=None,
            embedding=embedding,
        ),
    )


def resolve_entities(
    item_id: str,
    text: str,
    lang: str,
    store,
    embed_fn,
) -> None:
    """Extract entities from text, persist them, and link them to item_id.

    This is the synchronous core; worker.py calls it via asyncio.to_thread.
    """
    mentions = extract_mentions(text)
    for mention in mentions:
        entity_id = _find_or_create_entity(mention, lang, store, embed_fn)
        if entity_id is not None:
            store.link_entity(entity_id, item_id, mention, lang)


async def resolve_entities_async(
    item_id: str,
    text: str,
    lang: str,
    store,
    embed_fn,
) -> None:
    """Async wrapper around resolve_entities for the async worker loop."""
    await asyncio.to_thread(resolve_entities, item_id, text, lang, store, embed_fn)
