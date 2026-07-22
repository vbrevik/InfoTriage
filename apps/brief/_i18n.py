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


def _maybe_translate(
    text: str, item: dict, *, cache: "TranslationCache | None" = None
) -> str:
    """Return translated text for non-en/no items when translation is enabled.

    Args:
        text: The text to translate.
        item: Dict that may contain a ``lang`` key.
        cache: Optional TranslationCache to avoid repeated LLM calls.
               Defaults to the contracts no-op cache.
    """
    if not _translation_enabled() or not text:
        return text
    lang = (item.get("lang") or "").lower()
    if not lang or lang in ("en", "no"):
        return text
    target = os.environ.get("TRANSLATION_TARGET_LANG", "no")
    if cache is None:
        translated = _contracts.translate_to(text, target, source_lang=lang)
    else:
        translated = _contracts.translate_to(
            text, target, source_lang=lang, cache=cache
        )
    return f"{text} · _Translated ({target}):_ {translated}"
