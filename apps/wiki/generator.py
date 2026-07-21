#!/usr/bin/env python3
"""generator.py — auto-wiki page generator for Phase 10 (Wiki-LLM).

Builds standing Obsidian pages for entities/topics by retrieving relevant corpus
items, synthesizing an LLM summary with citations, and writing markdown to the
vault. Cross-language coverage verification is applied as a post-synthesis check.
"""
from __future__ import annotations

import datetime
import json
import os
import re
import urllib.request
from pathlib import Path
from typing import Callable, Iterable, cast

from contracts import to_frontmatter
from store import Store


DEFAULT_MODEL = "qwen36-ud-4bit"
DEFAULT_EMBED_MODEL = "intfloat/multilingual-e5-large"
DEFAULT_MAX_TOKENS = 800


# ---------------------------------------------------------------------------
# Default LLM / embedding helpers (local only, ADR-004)
# ---------------------------------------------------------------------------


def _get_embedding(text: str) -> list[float]:
    base = os.environ.get("LLM_BASE_URL", "http://127.0.0.1:8000/v1")
    key = os.environ.get("LLM_API_KEY", "omlx")
    body = json.dumps({"model": DEFAULT_EMBED_MODEL, "input": text}).encode()
    req = urllib.request.Request(
        base.rstrip("/") + "/embeddings",
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return cast(list[float], json.load(r)["data"][0]["embedding"])


def _llm(messages: list[dict], max_tokens: int = DEFAULT_MAX_TOKENS) -> str:
    base = os.environ.get("LLM_BASE_URL", "http://127.0.0.1:8000/v1")
    key = os.environ.get("LLM_API_KEY", "omlx")
    model = os.environ.get("LLM_MODEL", DEFAULT_MODEL)
    body = json.dumps(
        {
            "model": model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": max_tokens,
        }
    ).encode()
    req = urllib.request.Request(
        base.rstrip("/") + "/chat/completions",
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return cast(str, json.load(r)["choices"][0]["message"]["content"])


def _slugify(text: str) -> str:
    """Return a filesystem-safe slug from arbitrary text."""
    return re.sub(r"[^\w\-]+", "-", text).strip("-").lower()[:50]


# ---------------------------------------------------------------------------
# Synthesis prompt templates
# ---------------------------------------------------------------------------

CITATION_INSTRUCTION = "Cite every claim with [item_id]."
CROSS_LANGUAGE_INSTRUCTION = "Synthesize insights from ALL provided languages."
CONTRADICTION_INSTRUCTION = (
    "If sources disagree, highlight the contradiction explicitly."
)


def _synthesis_prompt(subject: str, items: list[dict]) -> str:
    lines = [
        "Write a concise intelligence wiki article about the topic below.",
        f"Use ONLY the provided articles as sources. {CITATION_INSTRUCTION}",
        CROSS_LANGUAGE_INSTRUCTION,
        CONTRADICTION_INSTRUCTION,
        "If the articles do not cover the topic, say so.\n",
        f"Topic: {subject}\n",
        "Articles:",
    ]
    for r in items:
        lines.append(
            f"[item_id: {r['item_id']}] Title: \"{r['title']}\" "
            f"Source: {r['source']} CCIR: {r.get('ccir', 'none')} Score: {r.get('score', 0)}"
        )
        if r.get("summary"):
            lines.append(f"Summary: {r['summary']}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Cross-language coverage verification (Phase 999.4)
# ---------------------------------------------------------------------------


def verify_language_coverage(items: Iterable[dict], text: str) -> list[str]:
    """Return languages present in items but missing from citations in text.

    Each item must have a 'lang' key or 'item_id'. Citation format is [item_id].
    """
    from collections import defaultdict

    lang_by_item: dict[str, str] = {}
    for item in items:
        item_id = str(item.get("item_id") or item.get("id"))
        if not item_id:
            continue
        lang_by_item[item_id] = item.get("lang") or "unknown"

    required_langs: set[str] = set()
    for item_id, lang in lang_by_item.items():
        if lang == "unknown":
            continue
        required_langs.add(lang)

    found_langs: set[str] = set()
    for match in re.finditer(r"\[([^\]]+)\]", text):
        cited = match.group(1).strip()
        if cited in lang_by_item:
            found_langs.add(lang_by_item[cited])

    return sorted(required_langs - found_langs)


# ---------------------------------------------------------------------------
# WikiGenerator
# ---------------------------------------------------------------------------


class WikiGenerator:
    """Generate and maintain auto-wiki pages in an Obsidian vault."""

    def __init__(
        self,
        store: Store,
        vault_path: Path | str,
        *,
        embed: Callable[[str], list[float]] | None = None,
        llm: Callable[[list[dict]], str] | None = None,
        max_items: int = 20,
    ) -> None:
        self.store = store
        self.vault_path = Path(vault_path)
        self.embed = embed or _get_embedding
        self.llm = llm or _llm
        self.max_items = max_items

    def _recall_for_subject(self, subject: str) -> list[dict]:
        vec = self.embed(f"query: {subject}")
        return self.store.recall_items(vec, limit=self.max_items)

    def build_prompt(self, subject: str, items: list[dict]) -> str:
        """Return the synthesis prompt for ``subject`` and its source ``items``.

        The prompt instructs the LLM to produce a concise intelligence wiki
        article, cite every claim with [item_id], synthesize across all
        languages present in the sources, and highlight any contradictions
        explicitly.
        """
        return _synthesis_prompt(subject, items)

    def _write_page(self, subject: str, synthesis: str, items: list[dict]) -> Path:
        self.vault_path.mkdir(parents=True, exist_ok=True)
        wiki_dir = self.vault_path / "wiki" / "auto"
        wiki_dir.mkdir(parents=True, exist_ok=True)

        filepath = wiki_dir / f"{_slugify(subject)}.md"

        frontmatter = to_frontmatter(
            {
                "title": subject,
                "subject": subject,
                "generated_at": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
                "source_count": len(items),
                "sources": [i["item_id"] for i in items],
            }
        )
        cited_list = "\n".join(f"- [{i['title']}]({i.get('url', '')})" for i in items if i.get("url"))
        body = (
            f"{frontmatter}\n\n"
            f"# {subject}\n\n"
            f"{synthesis}\n\n"
            f"## Sources\n\n{cited_list}\n"
        )

        tmp = filepath.with_suffix(".tmp")
        tmp.write_text(body, encoding="utf-8")
        os.replace(tmp, filepath)
        return filepath

    def generate_page(self, subject: str) -> Path:
        """Generate or refresh a standing wiki page for ``subject``.

        Returns the path to the written Obsidian note.
        """
        items = self._recall_for_subject(subject)
        if not items:
            prompt_text = (
                f"There are no corpus items for '{subject}'. Write a one-sentence "
                "wiki stub stating that no sources are currently available."
            )
        else:
            prompt_text = self.build_prompt(subject, items)

        synthesis = self.llm([{"role": "user", "content": prompt_text}])

        missing_langs = verify_language_coverage(items, synthesis)
        if missing_langs:
            synthesis += (
                "\n\n> ⚠️ **Verification Flag**: sources in "
                f"{', '.join(missing_langs)} were present but not cited."
            )

        return self._write_page(subject, synthesis, items)
