#!/usr/bin/env python3
"""tests/test_translation.py — unit tests for contracts._translation."""
import hashlib

import pytest

from contracts import translate_to, TranslationCache


class _FakeCache(TranslationCache):
    """In-memory cache for tests."""

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], str] = {}

    def get(self, text_hash: str, target_lang: str) -> str | None:
        return self._store.get((text_hash, target_lang))

    def put(self, text_hash: str, target_lang: str, translation: str) -> None:
        self._store[(text_hash, target_lang)] = translation


def test_translate_to_returns_cached_result_without_calling_llm():
    cache = _FakeCache()

    def fake_llm(messages, max_tokens=400):
        raise RuntimeError("should not be called")

    # Pre-seed the cache with the real text hash so the LLM is skipped.
    text = "original"
    text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    cache.put(text_hash, "en", "cached translation")

    result = translate_to(text, "en", llm=fake_llm, cache=cache)
    assert result == "cached translation"


def test_translate_to_calls_llm_and_caches_result():
    cache = _FakeCache()
    calls = []

    def fake_llm(messages, max_tokens=400):
        calls.append(messages)
        return "translated text"

    result = translate_to("hello world", "no", llm=fake_llm, cache=cache)
    assert result == "translated text"
    assert len(calls) == 1
    assert "Translate the following text" in calls[0][0]["content"]
    assert "hello world" in calls[0][0]["content"]


def test_translate_to_returns_empty_input_unchanged():
    def fake_llm(messages, max_tokens=400):
        raise RuntimeError("should not be called")

    assert translate_to("", "en", llm=fake_llm) == ""
    assert translate_to("   ", "en", llm=fake_llm) == "   "


def test_translate_to_passes_source_lang():
    calls = []

    def fake_llm(messages, max_tokens=400):
        calls.append(messages)
        return "ok"

    translate_to("привет", "en", source_lang="ru", llm=fake_llm)
    prompt = calls[0][0]["content"]
    assert "from ru to en" in prompt


def test_translate_to_prompts_only_translation():
    calls = []

    def fake_llm(messages, max_tokens=400):
        calls.append(messages)
        return "ok"

    translate_to("hello", "en", llm=fake_llm)
    prompt = calls[0][0]["content"]
    assert "Return only the translation" in prompt
    assert "no extra commentary" in prompt
