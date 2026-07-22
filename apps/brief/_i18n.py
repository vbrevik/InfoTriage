#!/usr/bin/env python3
"""_i18n.py — shared on-demand translation helpers for reading surfaces.

Used by apps.brief.renderer and apps.brief.vault_writer so translation logic
is not duplicated. All translation goes through the local LLM
(contracts.translate_to); cloud translation APIs are never used (ADR-004).
"""
import os

from contracts import TranslationCache

import contracts as _contracts


def _translation_enabled() -> bool:
    """Read TRANSLATION_ENABLED lazily so tests can toggle it."""
    return os.environ.get("TRANSLATION_ENABLED", "0").strip().lower() in (
        "1",
        "true",
        "yes",
    )


_skip_langs_cache: dict[str, set[str]] = {}


def _skip_langs() -> set[str]:
    """Return the set of language codes that should never be translated.

    Defaults to ``en,no,und`` so English, Norwegian, and unknown-language
    items (e.g. Telegram posts) are not translated by default.
    """
    raw = os.environ.get("TRANSLATION_SKIP_LANGS", "en,no,und")
    if raw not in _skip_langs_cache:
        _skip_langs_cache[raw] = {
            lang.strip().lower() for lang in raw.split(",") if lang.strip()
        }
    return _skip_langs_cache[raw]


def _maybe_translate(
    text: str, item: dict, *, cache: "TranslationCache | None" = None
) -> str:
    """Return translated text for items whose language is not in the skip list.

    Args:
        text: The text to translate.
        item: Dict that may contain a ``lang`` key.
        cache: Optional TranslationCache to avoid repeated LLM calls.
               Defaults to the contracts no-op cache.
    """
    if not _translation_enabled() or not text:
        return text
    lang = (item.get("lang") or "").lower()
    if not lang or lang in _skip_langs():
        return text
    target = os.environ.get("TRANSLATION_TARGET_LANG", "no")
    if cache is None:
        translated = _contracts.translate_to(text, target, source_lang=lang)
    else:
        translated = _contracts.translate_to(
            text, target, source_lang=lang, cache=cache
        )
    return f"{text} · _Translated ({target}):_ {translated}"
