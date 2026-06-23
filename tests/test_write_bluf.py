#!/usr/bin/env python3
"""tests/test_write_bluf.py — BLUF credential-leak guard.

Verifies that when the LLM raises an exception whose message contains
credential-like text (e.g. GMAIL_APP_PASSWORD=abcd1234), the markdown
output written by write_bluf never contains that text.

Usage: python3 tests/test_write_bluf.py
"""
import os, sys, unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "score"))
import triage_score  # noqa: E402
from digest import write_bluf  # noqa: E402


class TestBlufCredentialLeak(unittest.TestCase):
    """Simulate LLM failures with credential-shaped text; assert markdown is clean."""

    def _make_verdicts(self, ccir="PIR-1"):
        """Minimal verdict list hitting one CCIR."""
        return [{"title": "t", "source": "s", "summary": "sum",
                 "ccir": ccir, "cnr": "II", "score": 8, "bucket": "read",
                 "why": "test", "url": "http://x", "id": 1, "t": 0}]

    def test_credential_not_in_markdown(self):
        """Exception carrying GMAIL_APP_PASSWORD=… must NOT appear in bluf.md."""
        secret = "GMAIL_APP_PASSWORD=abcd1234efgh5678"
        original = triage_score.llm

        def failing_llm(msgs, max_tokens=400):
            raise RuntimeError(f"auth failed: {secret}")

        triage_score.llm = failing_llm
        try:
            _, text = write_bluf(self._make_verdicts("PIR-1"), "test period")
        finally:
            triage_score.llm = original

        self.assertNotIn("abcd1234", text)
        self.assertNotIn("GMAIL_APP_PASSWORD", text)
        self.assertIn("Kunne ikke generere BLUF", text)

    def test_credential_not_in_stderr_output(self):
        """The markdown placeholder is used, not the raw exception text."""
        secret = "imap_password=hunter2xyz"
        original = triage_score.llm

        def failing_llm(msgs, max_tokens=400):
            raise ConnectionError(f"IMAP auth: {secret}")

        triage_score.llm = failing_llm
        try:
            _, text = write_bluf(self._make_verdicts("SIR-1"), "test period")
        finally:
            triage_score.llm = original

        self.assertNotIn("hunter2xyz", text)
        self.assertNotIn("imap_password", text)
        self.assertIn("_(Kunne ikke generere BLUF", text)

    def test_normal_flow_still_works(self):
        """When LLM succeeds, BLUF text is returned as-is (no placeholder)."""
        original = triage_score.llm
        triage_score.llm = lambda msgs, max_tokens=400: "Dette er en normal BLUF."
        try:
            _, text = write_bluf(self._make_verdicts("FFIR-1"), "test period")
        finally:
            triage_score.llm = original

        self.assertIn("Dette er en normal BLUF.", text)
        self.assertNotIn("Kunne ikke generere BLUF", text)


if __name__ == "__main__":
    unittest.main()
