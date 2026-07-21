"""_verify.py — shared synthesis verification utilities.

Used by both standing wiki generation (``apps/wiki/generator.py``) and
on-demand recall synthesis (``apps/triage/recall.py``) to enforce that all
languages present in the source corpus are actually cited in the synthesized
output.
"""

from __future__ import annotations

import re
from typing import Iterable


CITATION_INSTRUCTION = "Cite every claim with [item_id]."
CROSS_LANGUAGE_INSTRUCTION = "Synthesize insights from ALL provided languages."
CONTRADICTION_INSTRUCTION = (
    "If sources disagree, highlight the contradiction explicitly."
)


def verify_language_coverage(items: Iterable[dict], text: str) -> list[str]:
    """Return languages present in ``items`` but missing from citations in ``text``.

    Each item must have an ``item_id`` or ``id`` and a ``lang`` key. Citation
    format is ``[item_id]``. Languages with ``lang == "unknown"`` are ignored.

    Args:
        items: Source items referenced by the synthesis.
        text: Synthesized text to check for citations.

    Returns:
        Sorted list of language codes that are present in ``items`` but not
        cited in ``text``.
    """
    lang_by_item: dict[str, str] = {}
    for item in items:
        raw_id = item.get("item_id") or item.get("id")
        if raw_id is None:
            continue
        item_id = str(raw_id)
        lang = item.get("lang")
        if not lang or lang == "unknown":
            continue
        lang_by_item[item_id] = lang

    required_langs: set[str] = set(lang_by_item.values())
    if not required_langs:
        return []

    found_langs: set[str] = set()
    for match in re.finditer(r"\[([^\]]+)\]", text):
        cited = match.group(1).strip()
        if cited in lang_by_item:
            found_langs.add(lang_by_item[cited])

    return sorted(required_langs - found_langs)
