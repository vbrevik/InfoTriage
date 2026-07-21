#!/usr/bin/env python3
"""_translation.py — local-LLM translation helpers for InfoTriage.

All translation runs against the local Qwen3.6 stack (ADR-004); cloud translation
APIs are never used.
"""
import hashlib
import json
import os
import urllib.request
from typing import Callable, Optional, Protocol, runtime_checkable


@runtime_checkable
class TranslationCache(Protocol):
    """Cache backend for translated text.

    Persistent implementations (e.g. Postgres) can satisfy this protocol to
    avoid repeated LLM calls for the same source text and target language.
    """

    def get(self, text_hash: str, target_lang: str) -> str | None:
        """Return cached translation or None on miss."""
        ...

    def put(self, text_hash: str, target_lang: str, translation: str) -> None:
        """Store translation in the cache."""
        ...


class _NoOpCache(TranslationCache):
    """Default cache that never stores or returns a hit."""

    def get(self, text_hash: str, target_lang: str) -> str | None:
        return None

    def put(self, text_hash: str, target_lang: str, translation: str) -> None:
        pass


NOOP_CACHE = _NoOpCache()


def _default_llm(messages: list[dict], max_tokens: int = 400) -> str:
    """Call the local LLM configured via environment variables.

    Mirrors the calling convention in apps/triage/triage_score.py so the
    translation helper works out of the box in the existing stack.

    Raises:
        urllib.error.URLError, TimeoutError, or other exceptions from the
        underlying HTTP request are propagated to the caller.
    """
    base = os.environ.get("LLM_BASE_URL", "http://127.0.0.1:8000/v1")
    key = os.environ.get("LLM_API_KEY", "omlx")
    model = os.environ.get("LLM_MODEL", "qwen36-ud-4bit")
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
        return str(json.load(r)["choices"][0]["message"]["content"])


def translate_to(
    text: str,
    target_lang: str,
    source_lang: Optional[str] = None,
    *,
    cache: TranslationCache = NOOP_CACHE,
    llm: Callable[[list[dict], int], str] = _default_llm,
) -> str:
    """Translate ``text`` to ``target_lang`` using the local LLM.

    Args:
        text: Source text to translate.
        target_lang: Target language (e.g. "en", "no").
        source_lang: Optional source language hint (e.g. "ru", "de", "es").
        cache: Optional cache backend. Defaults to a no-op cache.
        llm: Injectable LLM callable for testing.

    Returns:
        Translated text, or the original text if it is empty/whitespace-only.

    Raises:
        Exceptions from the injected ``llm`` callable (including network and
        timeout errors from the default local LLM) are propagated.
    """
    if not text or not text.strip():
        return text

    text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    cached: str | None = cache.get(text_hash, target_lang)
    if cached is not None:
        return cached

    lang_clause = (
        f"from {source_lang} to {target_lang}" if source_lang else f"to {target_lang}"
    )
    prompt = (
        f"Translate the following text {lang_clause}. "
        "Preserve named entities, technical terms, and the original meaning. "
        "Return only the translation, with no extra commentary.\n\n"
        f"{text}"
    )

    translation = llm([{"role": "user", "content": prompt}], 400).strip()
    cache.put(text_hash, target_lang, translation)
    return translation
