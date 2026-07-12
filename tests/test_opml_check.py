#!/usr/bin/env python3
"""tests/test_opml_check.py — apps/opml/_check.py classifier + OPML loader.

Tests:
1. ``classify(probe_result)`` correctly maps 200+RSS / 200+HTML / 4xx / 5xx /
   network errors into the documented ✅ / ⚠️ / ❌ buckets per MINOR-3 + the
   OPML header convention.
2. ``load_opml(apps/opml/feeds.opml)`` returns the expected 11 categories / 64
   rss feeds — same counts as ``tests/test_opml_roundtrip.py``.
3. ``filter_outlines(rss_list, "rusi.org")`` keeps only feeds whose XML URL
   contains the substring.

No network access required.
"""
import os
import xml.etree.ElementTree as ET

import pytest
import _check  # resolved via apps/opml on pythonpath

OPML = os.path.join(os.path.dirname(__file__), "..", "apps", "opml", "feeds.opml")


# ---------------------------------------------------------------------------
# classify()
# ---------------------------------------------------------------------------


def test_200_rss_xml_is_live():
    """200 OK with <?xml + <rss = ✅."""
    assert _check.classify(
        (200, "application/rss+xml", b'<?xml version="1.0"?><rss version="2.0">')
    ) == ("✅", "HTTP 200, RSS/Atom XML")


def test_200_atom_xml_is_live():
    """200 OK with <?xml + <feed = ✅ (Atom format)."""
    assert _check.classify(
        (
            200,
            "application/atom+xml",
            b'<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">',
        )
    ) == ("✅", "HTTP 200, RSS/Atom XML")


def test_200_html_body_keeps_warning():
    """200 OK but body is HTML (Pravda / The National Interest) = ⚠️."""
    assert _check.classify(
        (200, "text/html", b"<!DOCTYPE html><html><head><title>Pravda</title>")
    ) == ("⚠️", "HTTP 200, HTML body")


def test_403_cloudflare_is_warning():
    """403 (Cloudflare bot-block; ISW-style) = ⚠️."""
    assert _check.classify((403, "text/html", b"")) == ("⚠️", "HTTP 403")


def test_404_retired_url_is_warning():
    """404 (retired URL; RUSI-style) = ⚠️."""
    assert _check.classify((404, "text/plain", b"")) == ("⚠️", "HTTP 404")


def test_429_too_many_requests_is_transient():
    """429 = 🟡 (back off and retry; do NOT drop — gdeltproject.org class)."""
    assert _check.classify((429, "text/html", b"Rate limit exceeded")) == (
        "🟡",
        "HTTP 429 Too Many Requests",
    )


def test_429_with_html_body_still_transient():
    """429 takes precedence even when the body is HTML — operator should
    slow FreshRSS, regardless of body shape."""
    assert _check.classify(
        (429, "text/html", b"<!DOCTYPE html><html><body>rate limited</body></html>")
    ) == ("🟡", "HTTP 429 Too Many Requests")


def test_429_takes_precedence_over_4xx_branch():
    """Defensive order check: 429 returns 🟡 not ⚠️ even though 429 ≥ 400.
    Guards against future regressions if someone reorders the if-chain."""
    emoji, _ = _check.classify((429, "text/plain", b""))
    assert emoji == "🟡"


def test_500_unreachable():
    """5xx = ❌ (operator perspective: server failure)."""
    assert _check.classify((503, "text/plain", b"")) == ("❌", "HTTP 503")


def test_network_error_is_unreachable():
    """status='err' tag (DNS / TLS / timeout) = ❌."""
    emoji, reason = _check.classify(("err", "URLError: timeout", b""))
    assert emoji == "❌"
    assert "URLError" in reason


def test_200_unrecognised_body_is_warning():
    """200 OK but body not recognised (defense in depth) = ⚠️."""
    assert _check.classify((200, "", b"")) == ("⚠️", "HTTP 200, body not recognised")


def test_302_redirect_is_warning():
    """302 (no follow) = ⚠️ so operator knows the URL is stale."""
    assert _check.classify((302, "text/html", b"")) == (
        "⚠️",
        "HTTP 302 redirect (no follow)",
    )


def test_200_rss_with_utf8_bom_is_live():
    """200 OK with UTF-8 BOM + raw <rss> = ✅ (servers that omit <?xml)."""
    body = b'\xef\xbb\xbf<rss version="2.0"><channel>'
    assert _check.classify((200, "application/rss+xml", body)) == (
        "✅",
        "HTTP 200, RSS/Atom XML",
    )


def test_200_atom_bare_no_prolog_is_live():
    """200 OK with bare <feed> (no <?xml declaration) = ✅ (lenient path)."""
    body = b'<feed xmlns="http://www.w3.org/2005/Atom">'
    assert _check.classify((200, "application/atom+xml", body)) == (
        "✅",
        "HTTP 200, RSS/Atom XML",
    )


def test_200_html_with_literal_rss_in_body_is_warning():
    """Defense in depth: an HTML page that mentions <rss> in text stays ⚠️."""
    body = (
        b"<!DOCTYPE html><html><head><title>Cloudflare</title></head>"
        b"<body>RSS feed unavailable; please contact admin. "
        b"<rss>example</rss></body></html>"
    )
    emoji, reason = _check.classify((200, "text/html", body))
    assert (
        emoji == "⚠️"
    ), f"HTML page with literal <rss> must stay ⚠️, got {emoji!r}: {reason}"
    assert "HTML body" in reason


# ---------------------------------------------------------------------------
# load_opml()
# ---------------------------------------------------------------------------


def test_categories_count_12():
    """feeds.opml has 12 top-level outlines (Norske aviser → NewsAPI.org → Sport SIR-2)."""
    groups = _check.load_opml(OPML)
    assert (
        len(groups) == 12
    ), f"Expected 12 category groups, got {len(groups)}: {[cat for cat, _ in groups]}"


def test_total_rss_count_70():
    """feeds.opml has 70 RSS feeds total (verified 2026-06-24)."""
    groups = _check.load_opml(OPML)
    total = sum(len(rss) for _, rss in groups)
    assert total == 70, f"Expected 70 RSS feeds, got {total}"


def test_filter_outlines_substring():
    """filter_outlines() reduces a list by URL substring."""
    groups = _check.load_opml(OPML)
    all_rss = [o for _, rss in groups for o in rss]
    filtered = _check.filter_outlines(all_rss, "rusi.org")
    assert len(filtered) == 1, f"Expected 1 rusi.org feed, got {len(filtered)}"
    assert "rusi.org" in filtered[0].get("xmlUrl", "")


# ---------------------------------------------------------------------------
# filter_outlines() direct
# ---------------------------------------------------------------------------


def test_no_filter_returns_all():
    groups = _check.load_opml(OPML)
    all_rss = [o for _, rss in groups for o in rss]
    assert len(_check.filter_outlines(all_rss, "")) == len(all_rss)


def test_no_match_returns_empty():
    groups = _check.load_opml(OPML)
    all_rss = [o for _, rss in groups for o in rss]
    assert _check.filter_outlines(all_rss, "definitely-not-a-feed.example") == []


# ---------------------------------------------------------------------------
# emit_working_opml() — using tmp_path fixture
# ---------------------------------------------------------------------------


def _make_outline(title, url):
    return ET.Element(
        "outline",
        {
            "type": "rss",
            "text": title,
            "title": title,
            "xmlUrl": url,
            "htmlUrl": url.rsplit("/", 1)[0],
        },
    )


def _synthetic_results():
    return [
        (
            "CatA",
            _make_outline("A1-live", "https://a1.example/rss"),
            "A1-live",
            "https://a1.example/rss",
            "✅",
            "HTTP 200, RSS/Atom XML",
        ),
        (
            "CatA",
            _make_outline("A2-transient", "https://a2.example/rss"),
            "A2-transient",
            "https://a2.example/rss",
            "🟡",
            "HTTP 429 Too Many Requests",
        ),
        (
            "CatA",
            _make_outline("A3-broken", "https://a3.example/rss"),
            "A3-broken",
            "https://a3.example/rss",
            "⚠️",
            "HTTP 404",
        ),
        (
            "CatB",
            _make_outline("B1-unreachable", "https://b1.example/rss"),
            "B1-unreachable",
            "https://b1.example/rss",
            "❌",
            "HTTP 503",
        ),
        (
            "CatB",
            _make_outline("B2-live", "https://b2.example/rss"),
            "B2-live",
            "https://b2.example/rss",
            "✅",
            "HTTP 200, RSS/Atom XML",
        ),
    ]


def test_emit_working_opml_keeps_only_live_and_transient(tmp_path):
    """✅ + 🟡 survive; ⚠️ + ❌ are dropped."""
    out_path = str(tmp_path / "working.opml")
    _check.emit_working_opml(_synthetic_results(), out_path, "2026-06-24")
    tree = ET.parse(out_path)
    cats = tree.getroot().find("body").findall("outline")
    texts_in_file = []
    for c in cats:
        cat_text = c.get("text")
        for sub in c.findall("outline"):
            texts_in_file.append((cat_text, sub.get("text")))
    assert ("CatA", "A1-live") in texts_in_file
    assert ("CatA", "A2-transient") in texts_in_file
    assert ("CatA", "A3-broken") not in texts_in_file
    assert ("CatB", "B1-unreachable") not in texts_in_file
    assert ("CatB", "B2-live") in texts_in_file
    cat_texts = [c.get("text") for c in cats]
    assert "CatA" in cat_texts
    assert "CatB" in cat_texts


def test_emit_working_opml_preserves_xmlurl_htmlurl(tmp_path):
    """Each emitted outline keeps xmlUrl + htmlUrl verbatim from the input."""
    out_path = str(tmp_path / "working_urls.opml")
    _check.emit_working_opml(_synthetic_results(), out_path, "2026-06-24")
    tree = ET.parse(out_path)
    url_set = set()
    for sub in tree.getroot().iter("outline"):
        if sub.get("xmlUrl"):
            url_set.add((sub.get("text"), sub.get("xmlUrl"), sub.get("htmlUrl")))
    assert ("A1-live", "https://a1.example/rss", "https://a1.example") in url_set
    assert ("A2-transient", "https://a2.example/rss", "https://a2.example") in url_set
    assert ("B2-live", "https://b2.example/rss", "https://b2.example") in url_set


def test_emit_working_opml_has_date_stamp_in_title(tmp_path):
    """The <title> embeds today's probe date so staleness is visible."""
    out_path = str(tmp_path / "working_dated.opml")
    _check.emit_working_opml(_synthetic_results(), out_path, "2026-06-24")
    tree = ET.parse(out_path)
    title = tree.getroot().find("head").find("title").text
    assert (
        "probe-passed" in title
    ), f"title should mark file as probe-passed snapshot, got {title!r}"
    assert "2026-06-24" in title, f"title should embed today's date, got {title!r}"


def test_emit_working_opml_empty_results_writes_empty_body(tmp_path):
    """All-broken results still produce a valid OPML with empty body."""
    out_path = str(tmp_path / "working_empty.opml")
    _check.emit_working_opml([], out_path, "2026-06-24")
    tree = ET.parse(out_path)
    body = tree.getroot().find("body")
    assert len(body.findall("outline")) == 0
    title = tree.getroot().find("head").find("title").text
    assert "2026-06-24" in title
