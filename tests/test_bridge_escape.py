#!/usr/bin/env python3
"""tests/test_bridge_escape.py — bridge/_util.py::escape() contract.

Pins the helper that apps/ingest/{gmail,imap,yt}_to_atom.py route title /
author / summary text through before emitting Atom XML. The bridges trust
this helper not to leak raw ``<``, ``>``, ``&``, ``"``, ``'`` into the
feed; this test file is the regression net.
"""
import pytest
from _util import escape


def test_ascii_alphanumeric_passthrough():
    """Plain printable ASCII is unchanged."""
    assert escape("Hello world 123") == "Hello world 123"


def test_norwegian_unicode_passthrough():
    """Norwegian letters (æøå ÆØÅ) round-trip untouched — bridges send
    real Norwegian titles through this helper daily."""
    assert escape("Blåbær æøå ÆØÅ") == "Blåbær æøå ÆØÅ"


def test_ampersand_escaped():
    """``AT&T`` → ``AT&amp;T`` — raw ``&`` would orphan the entity."""
    assert escape("AT&T") == "AT&amp;T"


def test_angle_brackets_escaped():
    """``<script>`` → ``&lt;script&gt;`` — never embed raw markup."""
    assert escape("<script>") == "&lt;script&gt;"


def test_double_quote_escaped_by_default():
    """Helper must also be safe inside attribute values (quote=True)."""
    assert escape('said "hi"') == "said &quot;hi&quot;"


def test_single_quote_escaped_by_default():
    """Single quote also escaped by default — defense-in-depth."""
    assert escape("it's") == "it&#x27;s"


def test_none_returns_empty_string():
    """Bridges pass raw dict values; missing fields are None.
    html.escape(None) raises TypeError; this helper must not."""
    assert escape(None) == ""


def test_empty_string_passthrough():
    """Empty input is empty output — bridges write ' ' for blank fields."""
    assert escape("") == ""


def test_non_str_input_fails_loud():
    """Defense-in-depth: silent ``str()`` coercion was over-broad.
    If a future bridge mistakenly passes an int / dict / bytes,
    ``html.escape`` must raise — not silently emit its repr.
    """
    for bad in (123, 4.5, ["a"], {"k": "v"}, b"bytes"):
        with pytest.raises(TypeError):
            escape(bad)


def test_realistic_norwegian_title_with_metachars():
    """Realistic paste: Norwegian + ampersand + angle brackets survives."""
    s = "Forsvar & sikkerhet: <rapport> fra FFI 2025"
    out = escape(s)
    # Norwegian content unchanged
    assert "Forsvar" in out
    assert "sikkerhet" in out
    assert "FFI 2025" in out
    # All metachars escaped — no raw special chars in output
    assert "<" not in out
    assert ">" not in out
    assert "& " not in out   # raw & followed by space (not &amp; / &lt; / ...)
    assert "&amp;" in out
    assert "&lt;" in out
    assert "&gt;" in out


def test_double_escape_stays_well_formed():
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
            assert c not in twice, f"raw {c!r} leaked through double-escape of {raw!r}"
