#!/usr/bin/env python3
"""tests/test_triage_score_hotread.py — ccir.md hot-read regression test (D-5, D-02).

Proves score_item() re-reads CCIR_PATH on every call instead of caching it at
import time. Editing ccir.md between two score_item() calls must change the
prompt sent to the LLM, with no process restart.
"""
import json

import triage_score  # resolved via apps/triage on pythonpath


def test_ccir_hot_read(tmp_path, monkeypatch):
    """score_item() reads CCIR_PATH fresh each call — edits take effect immediately."""
    ccir_file = tmp_path / "ccir.md"
    ccir_file.write_text("MARKER_A", encoding="utf-8")
    monkeypatch.setattr(triage_score, "CCIR_PATH", str(ccir_file))

    captured_prompts = []

    def _capture_llm(messages, max_tokens=400):
        captured_prompts.append(messages[0]["content"])
        return json.dumps({"ccir": "none", "cnr": "none", "pmesii": "none",
                            "tessoc": "none", "score": 0, "why": "test"})

    monkeypatch.setattr(triage_score, "llm", _capture_llm)

    item = {"title": "test", "source": "src", "summary": "sum"}

    triage_score.score_item(item)
    assert "MARKER_A" in captured_prompts[0]

    ccir_file.write_text("MARKER_B", encoding="utf-8")

    triage_score.score_item(item)
    assert "MARKER_B" in captured_prompts[1]
    assert "MARKER_A" not in captured_prompts[1]
