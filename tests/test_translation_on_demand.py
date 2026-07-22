#!/usr/bin/env python3
"""test_translation_on_demand.py — tests for on-demand translation in reading surfaces."""
import hashlib
import os
from unittest.mock import patch

import pytest

# Patch contracts.translate_to before importing renderer/vault_writer.
# This import captures the *real* translate_to; the autouse fixture below
# patches the module attribute, but this binding stays the original function.
from contracts import TranslationCache, translate_to


def _fake_translate(
    text: str, target_lang: str, source_lang: str | None = None, **kwargs
) -> str:
    return f"[TRANSLATED {target_lang}] {text}"


@pytest.fixture(autouse=True)
def _patch_translate(monkeypatch):
    monkeypatch.setenv("TRANSLATION_ENABLED", "1")
    monkeypatch.setenv("TRANSLATION_TARGET_LANG", "no")
    with patch("contracts.translate_to", side_effect=_fake_translate):
        yield


class _DictTranslationCache:
    """In-memory TranslationCache implementation for tests."""

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], str] = {}

    def get(self, text_hash: str, target_lang: str) -> str | None:
        return self._store.get((text_hash, target_lang))

    def put(self, text_hash: str, target_lang: str, translation: str) -> None:
        self._store[(text_hash, target_lang)] = translation


def test_vault_writer_translates_non_en_no_title():
    """write_item_obsidian translates Russian item titles/summaries."""
    from apps.brief import vault_writer

    item = {
        "item_id": "item-1",
        "title": "Привет",
        "summary": "Новости",
        "source": "Test",
        "url": "https://example.com/1",
        "ts": "2026-07-21T10:00:00+00:00",
        "lang": "ru",
        "score": 8,
    }
    content = vault_writer.render_sab_obsidian([item])
    assert "[TRANSLATED no] Привет" in content
    assert "[TRANSLATED no] Новости" in content


def test_vault_writer_skips_translation_for_norwegian():
    """Norwegian items are not translated."""
    from apps.brief import vault_writer

    item = {
        "item_id": "item-2",
        "title": "Hei",
        "summary": "Nyheter",
        "source": "Test",
        "url": "https://example.com/2",
        "ts": "2026-07-21T10:00:00+00:00",
        "lang": "no",
        "score": 8,
    }
    content = vault_writer.render_sab_obsidian([item])
    assert "[TRANSLATED" not in content
    assert "Hei" in content


def test_renderer_translates_non_en_no_title():
    """render_brief translates Russian item titles."""
    from apps.brief import renderer

    item = {
        "item_id": "item-3",
        "title": "Привет мир",
        "summary": "Краткое содержание",
        "source": "Test",
        "url": "https://example.com/3",
        "ts": "2026-07-21T10:00:00+00:00",
        "lang": "ru",
        "score": 8,
        "ccir": "PIR-1",
        "cnr": "I",
        "bucket": "read",
        "why": "Test why",
    }
    content = renderer.render_brief([item])
    assert "[TRANSLATED no] Привет мир" in content


def test_renderer_skips_translation_when_disabled(monkeypatch):
    """When TRANSLATION_ENABLED=0, no translation happens."""
    from apps.brief import renderer

    monkeypatch.setenv("TRANSLATION_ENABLED", "0")
    item = {
        "item_id": "item-4",
        "title": "Привет",
        "summary": "Новости",
        "source": "Test",
        "url": "https://example.com/4",
        "ts": "2026-07-21T10:00:00+00:00",
        "lang": "ru",
        "score": 8,
    }
    content = renderer.render_list([item])
    assert "[TRANSLATED" not in content
    assert "Привет" in content


def test_renderer_skips_translation_for_und_lang(monkeypatch):
    """Items with lang='und' (e.g. Telegram) are not translated by default."""
    from apps.brief import renderer

    monkeypatch.delenv("TRANSLATION_SKIP_LANGS", raising=False)
    item = {
        "item_id": "item-und",
        "title": "Some Telegram title",
        "summary": "Some Telegram summary",
        "source": "Test",
        "url": "https://example.com/und",
        "ts": "2026-07-21T10:00:00+00:00",
        "lang": "und",
        "score": 8,
    }
    content = renderer.render_list([item])
    assert "[TRANSLATED" not in content
    assert "Some Telegram title" in content


def test_renderer_respects_custom_translation_skip_langs(monkeypatch):
    """TRANSLATION_SKIP_LANGS overrides the default skip list."""
    from apps.brief import renderer

    monkeypatch.setenv("TRANSLATION_SKIP_LANGS", "en")
    item = {
        "item_id": "item-und-translate",
        "title": "Привет",
        "summary": "Новости",
        "source": "Test",
        "url": "https://example.com/und2",
        "ts": "2026-07-21T10:00:00+00:00",
        "lang": "und",
        "score": 8,
    }
    content = renderer.render_list([item])
    assert "[TRANSLATED no] Привет" in content


def test_translate_to_uses_cache():
    """contracts.translate_to only calls the LLM once per (text, target_lang)."""
    cache = _DictTranslationCache()
    call_count = 0

    def _counting_llm(messages: list[dict], max_tokens: int = 400) -> str:
        nonlocal call_count
        call_count += 1
        return f"[TRANSLATED no] {messages[0]['content'][-20:]}"

    # ``translate_to`` is the *real* function captured at import time, even
    # though the autouse fixture patches ``contracts.translate_to``.
    translate_to("Привет мир", "no", source_lang="ru", cache=cache, llm=_counting_llm)
    translate_to("Привет мир", "no", source_lang="ru", cache=cache, llm=_counting_llm)

    assert call_count == 1, f"expected 1 LLM call, got {call_count}"


def test_renderer_threads_cache_to_translate_to():
    """render_brief passes a cache that prevents duplicate LLM calls."""
    from apps.brief import _i18n
    from apps.brief import renderer

    item = {
        "item_id": "item-cache",
        "title": "Привет мир",
        "summary": "Краткое содержание",
        "source": "Test",
        "url": "https://example.com/cache",
        "ts": "2026-07-21T10:00:00+00:00",
        "lang": "ru",
        "score": 8,
        "ccir": "PIR-1",
        "cnr": "I",
        "bucket": "read",
        "why": "Test why",
    }
    cache = _DictTranslationCache()
    call_count = 0

    def _caching_translate(
        text: str,
        target_lang: str,
        source_lang: str | None = None,
        *,
        cache: "TranslationCache | None" = None,
        **kwargs,
    ) -> str:
        nonlocal call_count
        text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if cache is not None:
            cached = cache.get(text_hash, target_lang)
            if cached is not None:
                return cached
        call_count += 1
        result = f"[TRANSLATED {target_lang}] {text}"
        if cache is not None:
            cache.put(text_hash, target_lang, result)
        return result

    with patch.object(_i18n._contracts, "translate_to", side_effect=_caching_translate):
        renderer.render_brief([item], cache=cache)
        renderer.render_brief([item], cache=cache)

    # Title and why are translated once on the first render and then served
    # from the cache on the second render.
    assert call_count == 2, f"expected 2 LLM calls, got {call_count}"


@pytest.mark.db_live
def test_postgres_translation_cache_get_and_put(pg_store):
    """PostgresTranslationCache persists translations across calls."""
    from store import PostgresTranslationCache

    pg_store.init_schema()
    cache = PostgresTranslationCache(pg_store)

    text = "Hello world"
    text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    target_lang = "no"

    assert cache.get(text_hash, target_lang) is None
    cache.put(text_hash, target_lang, "Hei verden")
    assert cache.get(text_hash, target_lang) == "Hei verden"
