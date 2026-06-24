#!/usr/bin/env python3
"""tests/test_bridge_escape.py — bridge/_util.py::escape() contract.

Pins the helper that bridge/{gmail,imap,yt}_to_atom.py route title / author /
summary text through before emitting Atom XML. The bridges trust this helper
not to leak raw ``<``, ``>``, ``&``, ``"``, ``'`` into the feed; this test
file is the regression net.

Usage: python3 tests/test_bridge_escape.py
"""
import os, sys, unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bridge"))
from _util import escape  # noqa: E402


class TestEscape(unittest.TestCase):
    """Atom-XML escape contract (None-safe; stdlib html.escape-equivalent)."""

    def test_ascii_alphanumeric_passthrough(self):
        """Plain printable ASCII is unchanged."""
        self.assertEqual(escape("Hello world 123"), "Hello world 123")

    def test_norwegian_unicode_passthrough(self):
        """Norwegian letters (æøå ÆØÅ) round-trip untouched — bridges send
        real Norwegian titles through this helper daily."""
        self.assertEqual(escape("Blåbær æøå ÆØÅ"), "Blåbær æøå ÆØÅ")

    def test_ampersand_escaped(self):
        """``AT&T`` → ``AT&amp;T`` — raw ``&`` would orphan the entity."""
        self.assertEqual(escape("AT&T"), "AT&amp;T")

    def test_angle_brackets_escaped(self):
        """``<script>`` → ``&lt;script&gt;`` — never embed raw markup."""
        self.assertEqual(escape("<script>"), "&lt;script&gt;")

    def test_double_quote_escaped_by_default(self):
        """Helper must also be safe inside attribute values (quote=True)."""
        self.assertEqual(escape('said "hi"'), "said &quot;hi&quot;")

    def test_single_quote_escaped_by_default(self):
        """Single quote also escaped by default — defense-in-depth."""
        self.assertEqual(escape("it's"), "it&#x27;s")

    def test_none_returns_empty_string(self):
        """Bridges pass raw dict values; missing fields are None.
        html.escape(None) raises TypeError; this helper must not."""
        self.assertEqual(escape(None), "")

    def test_empty_string_passthrough(self):
        """Empty input is empty output — bridges write ' ' for blank fields."""
        self.assertEqual(escape(""), "")

    def test_non_str_input_fails_loud(self):
        """Defense-in-depth: silent ``str()`` coercion was over-broad.
        If a future bridge mistakenly passes an int / dict / bytes,
        ``html.escape`` must raise — not silently emit its repr.
        """
        for bad in (123, 4.5, ["a"], {"k": "v"}, b"bytes"):
            with self.assertRaises(TypeError,
                                   msg=f"expected TypeError for input {bad!r}"):
                escape(bad)

    def test_realistic_norwegian_title_with_metachars(self):
        """Realistic paste: Norwegian + ampersand + angle brackets survives."""
        s = "Forsvar & sikkerhet: <rapport> fra FFI 2025"
        out = escape(s)
        # Norwegian content unchanged
        self.assertIn("Forsvar", out)
        self.assertIn("sikkerhet", out)
        self.assertIn("FFI 2025", out)
        # All metachars escaped — no raw special chars in output
        self.assertNotIn("<", out)
        self.assertNotIn(">", out)
        self.assertNotIn("& ", out)   # raw & followed by space (not &amp; / &lt; / ...)
        self.assertIn("&amp;", out)
        self.assertIn("&lt;", out)
        self.assertIn("&gt;", out)

    def test_double_escape_stays_well_formed(self):
        """Defense-in-depth: html.escape is not idempotent by design
        (``escape("&lt;")`` correctly becomes ``"&amp;lt;"`` — verbose but
        valid XML). The invariant we DO want is: even if a bridge
        accidentally double-escapes, the output still contains no raw
        XML metachars — FreshRSS keeps parsing; malformed output never
        reaches the feed. This protects against single-call regressions
        where ``escape`` accidentally started emitting raw ``<`` / ``>``.
        """
        for raw in ["<a>", "a&b", '"x"', "mix & < > '\"", "AT&T"]:
            once = escape(raw)
            twice = escape(once)
            for c in ("<", ">"):
                self.assertNotIn(c, twice,
                                 f"raw {c!r} leaked through double-escape of {raw!r}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
