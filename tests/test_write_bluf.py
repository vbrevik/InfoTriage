#!/usr/bin/env python3
"""tests/test_write_bluf.py — BLUF credential-leak guard.

Verifies that when the LLM raises an exception whose message contains
credential-like text (e.g. GMAIL_APP_PASSWORD=abcd1234), the markdown
output written by write_bluf never contains that text.

Usage: python3 tests/test_write_bluf.py
"""
import os, re, sys, unittest

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


class TestBlufTokenCap(unittest.TestCase):
    """--bluf-cap-total guards per-LLM-call input size for write_bluf.

    Tail items dropped (lowest-score end) when prompt > cap; section skipped
    cleanly with a markdown marker if cap is below frame + 1 item. Trims
    reported to stderr AND to a markdown footer in bluf.md.
    """

    def _make_verdicts_n(self, ccir, n, score_start=9):
        """N items in CCIR `ccir` with descending scores score_start..score_start-n+1."""
        return [
            {"title": f"item_{i}", "source": f"s_{i}",
             "summary": "x " * 50,                # ~100 chars; ~25 tokens per block
             "ccir": ccir, "cnr": "II", "score": score_start - i,
             "bucket": "read", "why": "test",
             "url": f"http://x/{i}", "id": i, "t": 0}
            for i in range(n)
        ]

    def _stub_llm(self, captured):
        """Replace llm; record the prompts sent, return a stable BLUF string."""
        def stub(msgs, max_tokens=400):
            captured.append(msgs[0]["content"])
            return f"BLUF capture {len(captured)}"
        return stub

    def test_cap_truncates_tail_when_over_budget(self):
        """Cap-induced trim: LLM gets top-K highest-scored items, markdown
        citations mirror exactly what was sent, footer reports the trim.
        Frame-wording agnostic — the test parses the actual prompt sent to
        the LLM (via block-marker indices) instead of re-replicating the
        production frame template. A sentence added to the frame just shifts
        K (cap-dependent), which this test still pins.
        """
        captured = []
        original = triage_score.llm
        triage_score.llm = self._stub_llm(captured)
        try:
            n = 8
            cap = 240
            verdicts = self._make_verdicts_n("FFIR-1", n=n, score_start=9)
            # cap sits between 1-block+frame (~232 tok) and 2-block+frame
            # (~268 tok) so K = 1 today; robust to ~30 chars of frame/block
            # growth before K flips. If K jumps to 2 or 3, the assertions
            # below adapt automatically — only the cap magnitude changes.
            _, text = write_bluf(verdicts, "test period",
                                 top_n=n, cap_total=cap)
        finally:
            triage_score.llm = original

        # Invariant 1: write_bluf runs once per active CCIR. With one section
        # carrying items, expect exactly one LLM call.
        self.assertEqual(len(captured), 1,
                         f"write_bluf is per-CCIR; expected 1 LLM call, got {len(captured)}")

        # Invariant 2: parse which items the LLM received via block markers.
        # The block format `[N] KILDE: …` is a production contract — if the
        # format ever drifts, this test should fail loudly so the regex (or
        # the test) gets updated together.
        sent_indices = sorted(int(m) for m in
                              re.findall(r"\[(\d+)\]\s+KILDE:", captured[0]))
        self.assertGreater(len(sent_indices), 0,
                           "captured prompt has no [N] KILDE markers — "
                           "write_bluf's block format drifted?")

        # Invariant 3: trim drops lowest-scored items *contiguously from the
        # tail*, so sent_indices form `list(range(1, K+1))`. If trim ever
        # drops from the head or skips middle items by mistake, this catches it.
        K = len(sent_indices)
        self.assertEqual(sent_indices, list(range(1, K + 1)),
                         f"trim must drop lowest-scored items contiguously "
                         f"from the tail; got sent_indices={sent_indices}")

        # Invariant 4: trim IS triggered (0 < K < n). If K == 0, either the
        # frame grew past cap or cap is set too low for current prompt size.
        # If K == n, either the frame shrunk below cap or cap is set too
        # loose. Either way the test's premise breaks — re-pick (cap, n).
        self.assertGreater(K, 0,
                           f"cap={cap} expected to keep ≥1 item; got K={K} "
                           f"(prompt frame grew past cap, or cap is too "
                           f"low for current prompt size)")
        self.assertLess(K, n,
                        f"cap={cap} expected to trim at least one item "
                        f"from {n}; got K={K} (prompt frame shrunk below "
                        f"cap, or cap is too loose)")

        # Invariant 5: footer fires whenever items were dropped.
        self.assertIn("Trimmet", text,
                      "footer must be present after a trim occurred")
        self.assertIn("elementer", text)

        # Invariant 6: markdown cites each sent item exactly at slot [N].
        # Citations mirror the prompt — this is the core drift-proof shape.
        for i in sent_indices:
            self.assertIn(f"[{i}] **", text,
                          f"[{i}] citation must appear in markdown "
                          f"(item_{i - 1} was sent in slot [{i}])")
            self.assertIn(f"item_{i - 1}", text,
                          f"item_{i - 1} (slot [{i}]) must be cited")

        # Invariant 7: items BELOW slot [K] must NOT appear in markdown.
        # Drop-tail trim + the citation-mirror invariant above guarantee
        # these were never sent to the LLM, so they must not be cited.
        for dropped_i in range(K + 1, n + 1):
            self.assertNotIn(f"item_{dropped_i - 1}", text,
                             f"item_{dropped_i - 1} (below slot [{K}]) "
                             f"must be trimmed off, not cited")

    def test_no_trim_when_under_cap(self):
        """Default cap easily fits a small prompt; no footer, all items cited."""
        captured = []
        original = triage_score.llm
        triage_score.llm = self._stub_llm(captured)
        try:
            verdicts = self._make_verdicts_n("FFIR-1", n=5, score_start=9)
            _, text = write_bluf(verdicts, "test period")
        finally:
            triage_score.llm = original
        self.assertNotIn("Trimmet", text)
        for i in range(5):
            self.assertIn(f"item_{i}", text)
        self.assertEqual(len(captured), 1)

    def test_cap_below_frame_skips_section_cleanly(self):
        """If cap_total can't fit frame + 1 item, section is skipped; LLM unused."""
        captured = []
        original = triage_score.llm
        triage_score.llm = self._stub_llm(captured)
        try:
            verdicts = self._make_verdicts_n("FFIR-1", n=2, score_start=9)
            # cap=1 is far below the frame (~700 chars / 4 ≈ 175 tokens).
            _, text = write_bluf(verdicts, "test period",
                                 top_n=2, cap_total=1)
        finally:
            triage_score.llm = original
        self.assertIn("seksjon hoppet over", text)
        self.assertIn("Trimmet", text)
        # LLM was not called (cap so low no prompt was sent).
        self.assertEqual(len(captured), 0)


if __name__ == "__main__":
    unittest.main()
