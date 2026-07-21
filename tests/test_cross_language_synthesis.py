"""tests/test_cross_language_synthesis.py — Phase 10 Wave 4 cross-language verification."""

from __future__ import annotations

from unittest.mock import MagicMock

from contracts import verify_language_coverage
from generator import WikiGenerator


def test_verify_language_coverage_passes_when_all_languages_cited():
    items = [
        {"item_id": "i1", "lang": "en"},
        {"item_id": "i2", "lang": "ru"},
        {"item_id": "i3", "lang": "no"},
    ]
    text = "Summary [i1], [i2], and [i3]."
    assert verify_language_coverage(items, text) == []


def test_verify_language_coverage_finds_missing_language():
    items = [
        {"item_id": "i1", "lang": "en"},
        {"item_id": "i2", "lang": "ru"},
        {"item_id": "i3", "lang": "no"},
    ]
    text = "Summary [i1] and [i3]."
    assert verify_language_coverage(items, text) == ["ru"]


def test_verify_language_coverage_ignores_unknown_languages():
    items = [
        {"item_id": "i1", "lang": "en"},
        {"item_id": "i2", "lang": "unknown"},
    ]
    text = "Summary [i1]."
    assert verify_language_coverage(items, text) == []


def test_verify_language_coverage_supports_id_key():
    items = [
        {"id": "i1", "lang": "en"},
        {"id": "i2", "lang": "ru"},
    ]
    text = "Summary [i1]."
    assert verify_language_coverage(items, text) == ["ru"]


def test_wiki_generator_appends_verification_flag_for_missing_language(tmp_path):
    store = MagicMock()
    store.recall_items.return_value = [
        {"item_id": "i1", "title": "T1", "url": "http://a/1", "lang": "en"},
        {"item_id": "i2", "title": "T2", "url": "http://a/2", "lang": "ru"},
    ]

    def llm(messages):
        return "Summary [i1]."

    gen = WikiGenerator(
        store, tmp_path / "vault", embed=lambda text: [0.1] * 1024, llm=llm
    )
    path = gen.generate_page("NATO")

    text = path.read_text(encoding="utf-8")
    assert "Verification Flag" in text
    assert "ru language sources were present but not cited" in text
    assert "Summary [i1]" in text


def test_wiki_generator_no_flag_when_all_languages_cited(tmp_path):
    store = MagicMock()
    store.recall_items.return_value = [
        {"item_id": "i1", "title": "T1", "url": "http://a/1", "lang": "en"},
        {"item_id": "i2", "title": "T2", "url": "http://a/2", "lang": "ru"},
    ]

    def llm(messages):
        return "Summary [i1] and [i2]."

    gen = WikiGenerator(
        store, tmp_path / "vault", embed=lambda text: [0.1] * 1024, llm=llm
    )
    path = gen.generate_page("NATO")

    text = path.read_text(encoding="utf-8")
    assert "Verification Flag" not in text
    assert "Summary [i1] and [i2]" in text


def test_verify_language_coverage_skips_items_with_missing_id():
    items = [
        {"item_id": "i1", "lang": "en"},
        {"lang": "ru"},  # no item_id or id
        {"id": None, "lang": "no"},
    ]
    assert verify_language_coverage(items, "Summary [i1].") == []


def test_wiki_generator_prompt_includes_cross_language_and_contradiction_instructions():
    gen = WikiGenerator(MagicMock(), "/vault")
    items = [
        {"item_id": "i1", "title": "T1", "source": "S1", "lang": "en"},
    ]
    prompt = gen.build_prompt("NATO", items)
    assert "Synthesize insights from ALL provided languages" in prompt
    assert "If sources disagree, highlight the contradiction" in prompt


def test_recall_synthesis_prompt_uses_shared_instructions():
    from recall import _synthesis_prompt

    prompt = _synthesis_prompt("Arctic security", [], include_body=False)
    assert "Cite every claim with [item_id]" in prompt
    assert "Synthesize insights from ALL provided languages" in prompt
    assert "If sources disagree, highlight the contradiction" in prompt


def test_recall_synthesis_prompt_hardens_optional_fields():
    from recall import _synthesis_prompt

    items = [{"item_id": "i1", "title": "T1"}]
    prompt = _synthesis_prompt("topic", items, include_body=False)
    assert "Source: unknown" in prompt
    assert "CCIR: none" in prompt
    assert "Score: 0" in prompt
