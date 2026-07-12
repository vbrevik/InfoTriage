#!/usr/bin/env python3
"""tests/test_write_bluf.py — BLUF credential-leak guard.

Verifies that when the LLM raises an exception whose message contains
credential-like text (e.g. GMAIL_APP_PASSWORD=abcd1234), the markdown
output written by write_bluf never contains that text.
"""
import re

import pytest
import triage_score  # resolved via apps/triage on pythonpath
from digest import write_bluf  # resolved via apps/triage on pythonpath


def _make_verdicts(ccir="PIR-1"):
    """Minimal verdict list hitting one CCIR."""
    return [
        {
            "title": "t",
            "source": "s",
            "summary": "sum",
            "ccir": ccir,
            "cnr": "II",
            "score": 8,
            "bucket": "read",
            "why": "test",
            "url": "http://x",
            "id": 1,
            "t": 0,
        }
    ]


def test_credential_not_in_markdown(monkeypatch):
    """Exception carrying GMAIL_APP_PASSWORD=… must NOT appear in bluf.md."""
    secret = "GMAIL_APP_PASSWORD=abcd1234efgh5678"

    def failing_llm(msgs, max_tokens=400):
        raise RuntimeError(f"auth failed: {secret}")

    monkeypatch.setattr(triage_score, "llm", failing_llm)
    _, text = write_bluf(_make_verdicts("PIR-1"), "test period")

    assert "abcd1234" not in text
    assert "GMAIL_APP_PASSWORD" not in text
    assert "Kunne ikke generere BLUF" in text


def test_credential_not_in_stderr_output(monkeypatch):
    """The markdown placeholder is used, not the raw exception text."""
    secret = "imap_password=hunter2xyz"

    def failing_llm(msgs, max_tokens=400):
        raise ConnectionError(f"IMAP auth: {secret}")

    monkeypatch.setattr(triage_score, "llm", failing_llm)
    _, text = write_bluf(_make_verdicts("SIR-1"), "test period")

    assert "hunter2xyz" not in text
    assert "imap_password" not in text
    assert "_(Kunne ikke generere BLUF" in text


def test_normal_flow_still_works(monkeypatch):
    """When LLM succeeds, BLUF text is returned as-is (no placeholder)."""
    monkeypatch.setattr(
        triage_score, "llm", lambda msgs, max_tokens=400: "Dette er en normal BLUF."
    )
    _, text = write_bluf(_make_verdicts("FFIR-1"), "test period")

    assert "Dette er en normal BLUF." in text
    assert "Kunne ikke generere BLUF" not in text


# ---------------------------------------------------------------------------
# Token-cap tests
# ---------------------------------------------------------------------------


def _make_verdicts_n(ccir, n, score_start=9):
    """N items in CCIR `ccir` with descending scores score_start..score_start-n+1."""
    return [
        {
            "title": f"item_{i}",
            "source": f"s_{i}",
            "summary": "x " * 50,  # ~100 chars; ~25 tokens per block
            "ccir": ccir,
            "cnr": "II",
            "score": score_start - i,
            "bucket": "read",
            "why": "test",
            "url": f"http://x/{i}",
            "id": i,
            "t": 0,
        }
        for i in range(n)
    ]


def _stub_llm_factory(captured):
    """Return a stub that records prompts and emits a stable BLUF string."""

    def stub(msgs, max_tokens=400):
        captured.append(msgs[0]["content"])
        return f"BLUF capture {len(captured)}"

    return stub


def test_cap_truncates_tail_when_over_budget(monkeypatch):
    """Cap-induced trim: LLM gets top-K highest-scored items, markdown
    citations mirror exactly what was sent, footer reports the trim."""
    captured = []
    monkeypatch.setattr(triage_score, "llm", _stub_llm_factory(captured))

    n = 8
    cap = 240
    verdicts = _make_verdicts_n("FFIR-1", n=n, score_start=9)
    _, text = write_bluf(verdicts, "test period", top_n=n, cap_total=cap)

    # Invariant 1: one LLM call per active CCIR
    assert (
        len(captured) == 1
    ), f"write_bluf is per-CCIR; expected 1 LLM call, got {len(captured)}"

    # Invariant 2: parse which items the LLM received via block markers
    sent_indices = sorted(
        int(m) for m in re.findall(r"\[(\d+)\]\s+KILDE:", captured[0])
    )
    assert (
        len(sent_indices) > 0
    ), "captured prompt has no [N] KILDE markers — write_bluf's block format drifted?"

    # Invariant 3: sent_indices form list(range(1, K+1)) — contiguous trim from tail
    K = len(sent_indices)
    assert sent_indices == list(
        range(1, K + 1)
    ), f"trim must drop lowest-scored items contiguously from the tail; got sent_indices={sent_indices}"

    # Invariant 4: trim IS triggered (0 < K < n)
    assert K > 0, f"cap={cap} expected to keep ≥1 item; got K={K}"
    assert K < n, f"cap={cap} expected to trim at least one item from {n}; got K={K}"

    # Invariant 5: footer fires whenever items were dropped
    assert "Trimmet" in text, "footer must be present after a trim occurred"
    assert "elementer" in text

    # Invariant 6: markdown cites each sent item exactly at slot [N]
    for i in sent_indices:
        assert (
            f"[{i}] **" in text
        ), f"[{i}] citation must appear in markdown (item_{i - 1} was sent in slot [{i}])"
        assert f"item_{i - 1}" in text, f"item_{i - 1} (slot [{i}]) must be cited"

    # Invariant 7: items BELOW slot [K] must NOT appear in markdown
    for dropped_i in range(K + 1, n + 1):
        assert (
            f"item_{dropped_i - 1}" not in text
        ), f"item_{dropped_i - 1} (below slot [{K}]) must be trimmed off, not cited"


def test_no_trim_when_under_cap(monkeypatch):
    """Default cap easily fits a small prompt; no footer, all items cited."""
    captured = []
    monkeypatch.setattr(triage_score, "llm", _stub_llm_factory(captured))
    verdicts = _make_verdicts_n("FFIR-1", n=5, score_start=9)
    _, text = write_bluf(verdicts, "test period")

    assert "Trimmet" not in text
    for i in range(5):
        assert f"item_{i}" in text
    assert len(captured) == 1


def test_cap_below_frame_skips_section_cleanly(monkeypatch):
    """If cap_total can't fit frame + 1 item, section is skipped; LLM unused."""
    captured = []
    monkeypatch.setattr(triage_score, "llm", _stub_llm_factory(captured))
    verdicts = _make_verdicts_n("FFIR-1", n=2, score_start=9)
    # cap=1 is far below the frame (~700 chars / 4 ≈ 175 tokens)
    _, text = write_bluf(verdicts, "test period", top_n=2, cap_total=1)

    assert "seksjon hoppet over" in text
    assert "Trimmet" in text
    # LLM was not called (cap so low no prompt was sent)
    assert len(captured) == 0
