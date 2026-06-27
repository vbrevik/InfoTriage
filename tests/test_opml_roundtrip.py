#!/usr/bin/env python3
"""tests/test_opml_roundtrip.py — OPML structural integrity.

Parses apps/opml/feeds.opml, verifies expected feed count and top-level
outline structure, then writes to a temp file and re-parses to confirm
roundtrip stability.
"""
import os
import tempfile
import xml.etree.ElementTree as ET

OPML = os.path.join(os.path.dirname(__file__), "..", "apps", "opml", "feeds.opml")

EXPECTED_TOP_OUTLINES = 11  # Norske aviser, Offentlig Norge, ... , Sport VM 2026 (SIR-2)
EXPECTED_RSS_FEEDS = 64     # total type="rss" outlines (verified 2026-06-24)


def _parse(path):
    tree = ET.parse(path)
    root = tree.getroot()
    body = root.find("body")
    top = body.findall("outline")
    rss = [o for o in root.iter("outline") if o.get("type") == "rss"]
    return tree, top, rss


def test_parse_counts():
    """OPML has expected number of top-level outlines and RSS feeds."""
    _, top, rss = _parse(OPML)
    assert len(top) == EXPECTED_TOP_OUTLINES, \
        f"Expected {EXPECTED_TOP_OUTLINES} top outlines, got {len(top)}"
    assert len(rss) == EXPECTED_RSS_FEEDS, \
        f"Expected {EXPECTED_RSS_FEEDS} RSS feeds, got {len(rss)}"


def test_all_rss_have_xmlurl():
    """Every type='rss' outline must have an xmlUrl attribute."""
    _, _, rss = _parse(OPML)
    for o in rss:
        assert o.get("xmlUrl") is not None, f"Missing xmlUrl on: {o.get('text')}"


def test_roundtrip_preserves_feed_count():
    """Write to temp, re-parse — feed count must be identical."""
    tree, top_before, rss_before = _parse(OPML)
    with tempfile.NamedTemporaryFile(suffix=".opml", delete=False) as f:
        tmp = f.name
        tree.write(tmp, encoding="unicode", xml_declaration=True)
    try:
        _, top_after, rss_after = _parse(tmp)
        assert len(top_before) == len(top_after)
        assert len(rss_before) == len(rss_after)
    finally:
        os.unlink(tmp)


def test_top_outlines_have_text():
    """Every top-level outline must have a text attribute (category name)."""
    _, top, _ = _parse(OPML)
    for o in top:
        assert o.get("text") is not None, "Top-level outline missing 'text' attribute"
