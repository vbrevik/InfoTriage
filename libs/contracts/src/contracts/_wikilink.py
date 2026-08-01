"""_wikilink.py — shared Obsidian [[wikilink]] rendering.

Moved verbatim from apps/brief/vault_writer.py (2026-08-01) so both the brief
vault-writer and the wiki generator link entities without a cross-app import
(same sharing pattern as _verify.verify_language_coverage).
"""
from __future__ import annotations

import re

_URL_SPAN_RE = re.compile(r"https?://\S+")


def render_wikilinked(text: str, entities: list[str]) -> str:
    """Replace entities with [[Entity]] wikilinks.

    Args:
        text: Text to transform
        entities: List of entities to replace with wikilinks

    Returns:
        Wikilinked text with markdown links

    Never wikilinks inside a URL. An extracted "entity" can be a domain
    fragment (e.g. "cw.no", "adnuntius.com" — newsletter/ad-tech noise from
    imperfect NER) that is also a literal substring of a URL elsewhere in the
    same text; word-boundary matching alone does not protect against this,
    since "." and "/" are non-word characters, so the naive substitution
    corrupts the URL (e.g. "https://www.cw.no/x" -> "https://www.[[cw.no]]/x").
    URL spans are protected from substitution entirely (2026-07-24).
    """
    # Split on URL spans, keeping them (capturing group) so we can skip them.
    segments = _URL_SPAN_RE.split(text)
    urls = _URL_SPAN_RE.findall(text)

    # Longest-first so prefix entities ("Ukraine") don't corrupt longer forms
    # ("Ukrainian"); word boundaries + lookarounds skip text already wikilinked.
    sorted_entities = sorted(entities, key=len, reverse=True)

    def _wikilink_segment(segment: str) -> str:
        for entity in sorted_entities:
            pattern = r"(?<!\[)\b" + re.escape(entity) + r"\b(?!\])"
            segment = re.sub(pattern, f"[[{entity}]]", segment)
        return segment

    # re.split with a capturing pattern interleaves non-matches and matches:
    # segments[0], urls[0], segments[1], urls[1], ... segments[-1]. Rebuild in
    # that order, wikilinking only the non-URL segments.
    parts = [_wikilink_segment(segments[0])]
    for url, seg in zip(urls, segments[1:]):
        parts.append(url)
        parts.append(_wikilink_segment(seg))
    return "".join(parts)
