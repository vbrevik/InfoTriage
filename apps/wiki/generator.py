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

import yaml

from contracts import (
    CITATION_INSTRUCTION,
    CONTRADICTION_INSTRUCTION,
    CROSS_LANGUAGE_INSTRUCTION,
    from_frontmatter,
    to_frontmatter,
    verify_language_coverage,
)
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

# Prompt-instruction constants are imported from the contracts package so
# that standing wiki generation and on-demand recall synthesis stay in sync.


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
            f"Source: {r.get('source', 'unknown')} "
            f"CCIR: {r.get('ccir', 'none')} "
            f"Score: {r.get('score', 0)}"
        )
        if r.get("summary"):
            lines.append(f"Summary: {r['summary']}")
    return "\n".join(lines)


# verify_language_coverage is now shared from contracts._verify (Phase 10 Wave 4)
# so it can be reused by apps/triage/recall.py.


# ---------------------------------------------------------------------------
# Public file writer
# ---------------------------------------------------------------------------


def write_wiki_page(
    subject: str, content: str, metadata: dict, vault_path: Path | str
) -> Path:
    """Write or update a standing wiki page in the Obsidian vault.

    The note is written to ``<vault_path>/wiki/auto/<slug>.md``. If the file
    already exists, the existing YAML frontmatter is parsed, merged with the
    new ``metadata`` (new keys override, operator-added custom keys are kept),
    and only the markdown body is replaced.

    Args:
        subject: Human-readable topic/entity title.
        content: Markdown body to write (excluding frontmatter).
        metadata: Frontmatter keys to persist/override.
        vault_path: Root of the Obsidian vault.

    Returns:
        Path to the written note.
    """
    vault_path = Path(vault_path)
    wiki_dir = vault_path / "wiki" / "auto"
    wiki_dir.mkdir(parents=True, exist_ok=True)

    filepath = wiki_dir / f"{_slugify(subject)}.md"

    if filepath.exists():
        existing_text = filepath.read_text(encoding="utf-8")
        try:
            existing_meta = from_frontmatter(existing_text)
        except (ValueError, yaml.YAMLError):
            existing_meta = {}
        merged_meta = {**existing_meta, **metadata}
    else:
        merged_meta = metadata

    frontmatter = to_frontmatter(merged_meta)
    full_text = f"{frontmatter}\n{content}"

    tmp = filepath.with_suffix(".tmp")
    tmp.write_text(full_text, encoding="utf-8")
    os.replace(tmp, filepath)
    return filepath


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
        return cast(list[dict], self.store.recall_items(vec, limit=self.max_items))

    def build_prompt(self, subject: str, items: list[dict]) -> str:
        """Return the synthesis prompt for ``subject`` and its source ``items``.

        The prompt instructs the LLM to produce a concise intelligence wiki
        article, cite every claim with [item_id], synthesize across all
        languages present in the sources, and highlight any contradictions
        explicitly.
        """
        return _synthesis_prompt(subject, items)

    def _write_page(self, subject: str, synthesis: str, items: list[dict]) -> Path:
        metadata = {
            "title": subject,
            "subject": subject,
            "generated_at": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
            "source_count": len(items),
            "sources": [i["item_id"] for i in items],
        }
        cited_list = "\n".join(
            f"- [{i['title']}]({i.get('url', '')})" for i in items if i.get("url")
        )
        body = f"# {subject}\n\n" f"{synthesis}\n\n" f"## Sources\n\n{cited_list}\n"
        return write_wiki_page(subject, body, metadata, self.vault_path)

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
            lang_list = ", ".join(missing_langs)
            synthesis += (
                "\n\n> ⚠️ **Verification Flag**: "
                f"{lang_list} language sources were present but not cited."
            )

        return self._write_page(subject, synthesis, items)
