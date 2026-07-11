#!/usr/bin/env python3
"""tests/test_score_parse.py — scorer JSON extraction robustness.

Covers the three payload shapes the LLM can return:
  A: well-formed JSON dict
  B: JSON inside a triple-backtick code fence (```json ... ```)
  C: garbage with no braces → fallback dict
"""
import json
import logging

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


# -- TESSOC vocabulary coverage (formerly untested labels) ---------------


def test_tessoc_terror_low_score_maybe():
    """PIR-1 + TESSOC='Terror' passes through score_item unchanged → bucket=maybe.

    Regression guard for the TESSOC taxonomy (commit 9b62b95 reorganised
    TESSOC to the UK/NATO JDP 2-00 threat-actor frame: Terror / Espionage /
    Subversion / Sabotage / Organized Crime). If a future prompt rewrite
    drops 'Terror' from the enumeration list, the LLM might silently start
    emitting 'none' or another label instead, and this test fails loudly.
    """
    payload = json.dumps({"ccir": "PIR-1", "cnr": "II", "pmesii": "Military",
                          "tessoc": "Terror", "score": 4, "why": "test"})
    v = _score_with(payload)
    assert v["bucket"] == "maybe"
    assert v["pmesii"] == "Military"
    assert v["tessoc"] == "Terror"


def test_tessoc_subversion_low_score_maybe():
    """PIR-1 + TESSOC='Subversion' passes through score_item unchanged → bucket=maybe.

    Regression guard. Per ccir.md (post-9b62b95), PIR-1's canonical TESSOC
    annotation lists 'Espionage, Sabotage, Subversion' — so this label is
    BOTH canonically valid AND now directly tested (previously only
    Espionage and Sabotage were exercised in the test suite).
    """
    payload = json.dumps({"ccir": "PIR-1", "cnr": "II", "pmesii": "Political",
                          "tessoc": "Subversion", "score": 4, "why": "test"})
    v = _score_with(payload)
    assert v["bucket"] == "maybe"
    assert v["pmesii"] == "Political"
    assert v["tessoc"] == "Subversion"


def test_tessoc_organized_crime_low_score_maybe():
    """PIR-1 + TESSOC='Organized Crime' passes through score_item unchanged → bucket=maybe.

    Regression guard. Note the SPACE in the value — matches the LLM-emitted
    title-case form per the prompt's enumeration list ('Organized Crime',
    not 'organized_crime' or 'Organized_Crime'). This value flows through
    sab_html.py, which lowercases it before lookup (TESSOC_ICONS['organized crime']),
    so both the scorer and the renderer need to preserve the space.
    """
    payload = json.dumps({"ccir": "PIR-1", "cnr": "II", "pmesii": "Economic",
                          "tessoc": "Organized Crime", "score": 4, "why": "test"})
    v = _score_with(payload)
    assert v["bucket"] == "maybe"
    assert v["pmesii"] == "Economic"
    assert v["tessoc"] == "Organized Crime"


# -- caplog regression: ccir='none' coercion emits log.warning on drift ----


def test_ccir_none_dirty_emits_log_warning(caplog):
    """ccir=none + non-'none' pmesii/tessoc → triage_score emits log.warning.

    Regression guard for the observability fix that closes the 243008d
    post-push reviewer's flagged gap (silent coercion masking qwen36
    prompt drift). Asserts the WARNING-level record carries the PRE-
    coercion pmesii/tessoc values so the operator can spot drift on
    the wire before downstream consumers see the cleaned data.
    """
    payload = json.dumps({"ccir": "none", "cnr": "none",
                          "pmesii": "Military", "tessoc": "Espionage",
                          "score": 4, "why": "not ccir"})
    with caplog.at_level(logging.WARNING, logger=triage_score.log.name):
        _score_with(payload)
    drift_warnings = [
        r for r in caplog.records
        if r.levelno == logging.WARNING
        and "ccir=none" in r.message
        and "Military" in r.message
        and "Espionage" in r.message
    ]
    assert drift_warnings, (
        f"expected triage_score WARNING with pre-coercion values, "
        f"got {[(r.levelname, r.message) for r in caplog.records]}"
    )


def test_ccir_none_clean_stays_silent(caplog):
    """ccir=none + already-clean enrichment must NOT emit log.warning.

    Regression guard for the same observability fix: when the LLM
    emits ccir=none alongside already-clean pmesii='none'/tessoc='none',
    no coercion actually moves the values, so no warning should fire.
    (The test_garbage_returns_fallback path hits the same ccir=none
    branch with already-clean values but via the bootstrap dict,
    not through a real LLM payload.)
    """
    payload = json.dumps({"ccir": "none", "cnr": "none",
                          "pmesii": "none", "tessoc": "none",
                          "score": 0, "why": "irrelevant"})
    with caplog.at_level(logging.WARNING, logger=triage_score.log.name):
        _score_with(payload)
    drift_warnings = [
        r for r in caplog.records
        if r.levelno == logging.WARNING
        and "triage_score enriched" in r.message
    ]
    assert not drift_warnings, (
        f"expected SILENT on clean ccir=none, "
        f"got {[(r.levelname, r.message) for r in drift_warnings]}"
    )
