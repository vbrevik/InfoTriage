#!/usr/bin/env python3
"""tests/test_score_parse.py — scorer JSON extraction robustness.

Covers the three payload shapes the LLM can return:
  A: well-formed JSON dict
  B: JSON inside a triple-backtick code fence (```json ... ```)
  C: garbage with no braces → fallback dict
"""
import json

import triage_score  # resolved via apps/triage on pythonpath


def _score_with(llm_raw, item=None):
    """Run score_item with a stubbed llm() that returns `llm_raw`."""
    item = item or {"title": "test", "source": "src", "summary": "sum"}
    original = triage_score.llm
    triage_score.llm = lambda msgs, max_tokens=400: llm_raw
    try:
        return triage_score.score_item(item)
    finally:
        triage_score.llm = original


# -- A: well-formed JSON -----------------------------------------------

def test_wellformed_json():
    """Clean JSON → parsed fields, bucket=read (score >= 7)."""
    payload = json.dumps({"ccir": "FFIR-3", "cnr": "II", "pmesii": "Information",
                          "tessoc": "Espionage", "score": 7, "why": "test"})
    v = _score_with(payload)
    assert v["ccir"] == "FFIR-3"
    assert v["cnr"] == "II"
    assert v["pmesii"] == "Information"
    assert v["tessoc"] == "Espionage"
    assert v["score"] == 7
    assert v["bucket"] == "read"


# -- B: code-fenced JSON -----------------------------------------------

def test_codefence_json():
    """JSON wrapped in ```json ... ``` → same as well-formed."""
    inner = json.dumps({"ccir": "FFIR-3", "cnr": "II", "pmesii": "Information",
                        "tessoc": "Espionage", "score": 7, "why": "test"})
    payload = f"```json\n{inner}\n```"
    v = _score_with(payload)
    assert v["ccir"] == "FFIR-3"
    assert v["pmesii"] == "Information"
    assert v["tessoc"] == "Espionage"
    assert v["score"] == 7
    assert v["bucket"] == "read"


# -- C: garbage (no JSON at all) ----------------------------------------

def test_garbage_returns_fallback():
    """Unparseable → fallback dict: ccir=none, score=0, bucket=skip."""
    v = _score_with("not even json — just some text")
    assert v["ccir"] == "none"
    assert v["cnr"] == "none"
    assert v["pmesii"] == "none"
    assert v["tessoc"] == "none"
    assert v["score"] == 0
    assert v["why"] == "uleselig modell-svar"
    assert v["bucket"] == "skip"


# -- bonus: low score → bucket=maybe -----------------------------------

def test_low_score_maybe():
    """CCIR hit with score < 7 and cnr != I → bucket=maybe."""
    payload = json.dumps({"ccir": "PIR-1", "cnr": "II", "pmesii": "Military",
                          "tessoc": "Sabotage", "score": 4, "why": "test"})
    v = _score_with(payload)
    assert v["bucket"] == "maybe"
    assert v["pmesii"] == "Military"
    assert v["tessoc"] == "Sabotage"


# -- bonus: cnr I → bucket=read regardless of score ---------------------

def test_cnr_one_forces_read():
    """CAT I → bucket=read even at low score."""
    payload = json.dumps({"ccir": "PIR-1", "cnr": "I", "pmesii": "Military",
                          "tessoc": "Sabotage", "score": 3, "why": "test"})
    v = _score_with(payload)
    assert v["bucket"] == "read"
    assert v["pmesii"] == "Military"
    assert v["tessoc"] == "Sabotage"


def test_missing_enrichment_fallback():
    """LLM omits pmesii + tessoc → falls back to 'none' gracefully."""
    payload = json.dumps({"ccir": "FFIR-3", "cnr": "II", "score": 7,
                          "why": "test"})
    v = _score_with(payload)
    assert v["pmesii"] == "none"
    assert v["tessoc"] == "none"
    assert v["bucket"] == "read"


# -- prompt-contract regression: ccir='none' forces pmesii/tessoc to 'none' ---


def test_ccir_none_forces_pmesii_and_tessoc_none():
    """Prompt contract: ccir='none' forces pmesii='none' AND tessoc='none'.

    Per apps/triage/triage_score.py scoring prompt's disambiguation:
      PMESII: '"none" if ccir is "none" (irrelevant items have no operational domain).'
      TESSOC: '"none" if ccir is "none".'

    Regression guard: if a future prompt rewrite drops or weakens either of
    those two lines, OR if the LLM drifts and emits a non-'none' pmesii/
    tessoc alongside a 'none' ccir, score_item must coerce. Without this
    guard a stray Military/Espionage tag leaks into the rest of the
    pipeline (filter_rows, sab_html.py TESSOC distribution, view filters)
    for items that the scorer itself said are not CCIR-relevant.
    """
    payload = json.dumps({"ccir": "none", "cnr": "none",
                          "pmesii": "Military", "tessoc": "Espionage",
                          "score": 4, "why": "not ccir"})
    v = _score_with(payload)
    assert v["ccir"] == "none"
    # Contract: ccir='none' → no PMESII domain, no TESSOC actor
    assert v["pmesii"] == "none"
    assert v["tessoc"] == "none"
    # And bucket must reflect the ccir=none skip path
    assert v["bucket"] == "skip"


def test_ccir_none_both_pmesii_and_tessoc_emitted_both_coerced():
    """Same contract: LLM emits BOTH pmesii and tessoc for a 'none' ccir.

    Mirrors the synthetic case where either enrichment field leaks
    alongside a 'none' ccir — the contract coercion should still take
    precedence over the setdefault fallback for BOTH fields.
    """
    payload = json.dumps({"ccir": "none", "cnr": "none",
                          "pmesii": "Information", "tessoc": "Sabotage",
                          "score": 0, "why": "irrelevant"})
    v = _score_with(payload)
    assert v["ccir"] == "none"
    assert v["pmesii"] == "none"
    assert v["tessoc"] == "none"
    assert v["bucket"] == "skip"
