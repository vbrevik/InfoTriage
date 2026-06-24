#!/usr/bin/env python3
"""tests/test_score_parse.py — scorer JSON extraction robustness.

Covers the three payload shapes the LLM can return:
  A: well-formed JSON dict
  B: JSON inside a triple-backtick code fence (```json ... ```)
  C: garbage with no braces → fallback dict

Usage: python3 tests/test_score_parse.py
"""
import json, os, sys, unittest

# Ensure the score/ package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "score"))
import triage_score  # noqa: E402


class TestScoreParse(unittest.TestCase):
    """Stub triage_score.llm and drive score_item() with controlled payloads."""

    # -- helpers ----------------------------------------------------------

    def _score_with(self, llm_raw, item=None):
        """Run score_item with a stubbed llm() that returns `llm_raw`."""
        item = item or {"title": "test", "source": "src", "summary": "sum"}
        original = triage_score.llm
        triage_score.llm = lambda msgs, max_tokens=400: llm_raw
        try:
            return triage_score.score_item(item)
        finally:
            triage_score.llm = original

    # -- A: well-formed JSON -----------------------------------------------

    def test_wellformed_json(self):
        """Clean JSON → parsed fields, bucket=read (score >= 7)."""
        payload = json.dumps({"ccir": "FFIR-3", "cnr": "II", "pmesii": "Information",
                              "tessoc": "Skills", "score": 7, "why": "test"})
        v = self._score_with(payload)
        self.assertEqual(v["ccir"], "FFIR-3")
        self.assertEqual(v["cnr"], "II")
        self.assertEqual(v["pmesii"], "Information")
        self.assertEqual(v["tessoc"], "Skills")
        self.assertEqual(v["score"], 7)
        self.assertEqual(v["bucket"], "read")

    # -- B: code-fenced JSON -----------------------------------------------

    def test_codefence_json(self):
        """JSON wrapped in ```json ... ``` → same as well-formed."""
        inner = json.dumps({"ccir": "FFIR-3", "cnr": "II", "pmesii": "Information",
                            "tessoc": "Skills", "score": 7, "why": "test"})
        payload = f"```json\n{inner}\n```"
        v = self._score_with(payload)
        self.assertEqual(v["ccir"], "FFIR-3")
        self.assertEqual(v["pmesii"], "Information")
        self.assertEqual(v["tessoc"], "Skills")
        self.assertEqual(v["score"], 7)
        self.assertEqual(v["bucket"], "read")

    # -- C: garbage (no JSON at all) ----------------------------------------

    def test_garbage_returns_fallback(self):
        """Unparseable → fallback dict: ccir=none, score=0, bucket=skip."""
        v = self._score_with("not even json — just some text")
        self.assertEqual(v["ccir"], "none")
        self.assertEqual(v["cnr"], "none")
        self.assertEqual(v["pmesii"], "none")
        self.assertEqual(v["tessoc"], "none")
        self.assertEqual(v["score"], 0)
        self.assertEqual(v["why"], "uleselig modell-svar")
        self.assertEqual(v["bucket"], "skip")

    # -- bonus: low score → bucket=maybe -----------------------------------

    def test_low_score_maybe(self):
        """CCIR hit with score < 7 and cnr != I → bucket=maybe."""
        payload = json.dumps({"ccir": "PIR-1", "cnr": "II", "pmesii": "Military",
                              "tessoc": "Equipment", "score": 4, "why": "test"})
        v = self._score_with(payload)
        self.assertEqual(v["bucket"], "maybe")
        self.assertEqual(v["pmesii"], "Military")
        self.assertEqual(v["tessoc"], "Equipment")

    # -- bonus: cnr I → bucket=read regardless of score ---------------------

    def test_cnr_one_forces_read(self):
        """CAT I → bucket=read even at low score."""
        payload = json.dumps({"ccir": "PIR-1", "cnr": "I", "pmesii": "Military",
                              "tessoc": "Equipment", "score": 3, "why": "test"})
        v = self._score_with(payload)
        self.assertEqual(v["bucket"], "read")
        self.assertEqual(v["pmesii"], "Military")
        self.assertEqual(v["tessoc"], "Equipment")

    def test_missing_enrichment_fallback(self):
        """LLM omits pmesii + tessoc → falls back to 'none' gracefully."""
        payload = json.dumps({"ccir": "FFIR-3", "cnr": "II", "score": 7,
                              "why": "test"})
        v = self._score_with(payload)
        self.assertEqual(v["pmesii"], "none")
        self.assertEqual(v["tessoc"], "none")
        self.assertEqual(v["bucket"], "read")


if __name__ == "__main__":
    unittest.main()
