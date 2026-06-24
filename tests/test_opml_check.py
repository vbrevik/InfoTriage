#!/usr/bin/env python3
"""tests/test_opml_check.py — opml/_check.py classifier + OPML loader.

Tests:
1. ``classify(probe_result)`` correctly maps 200+RSS / 200+HTML / 4xx / 5xx / network
   errors into the documented ✅ / ⚠️ / ❌ buckets per MINOR-3 + the OPML
   header convention.
2. ``load_opml(opml/feeds.opml)`` returns the expected 11 categories / 64 rss
   feeds — same counts as ``tests/test_opml_roundtrip.py``.
3. ``filter_outlines(rss_list, "rusi.org")`` keeps only feeds whose XML URL
   contains the substring.

No network access required.

Usage: python3 tests/test_opml_check.py
"""
import os
import shutil
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

# opml/ is a sibling of tests/; adding it to sys.path lets us `import _check`.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "opml"))
import _check  # noqa: E402

OPML = os.path.join(os.path.dirname(__file__), "..", "opml", "feeds.opml")


class TestClassify(unittest.TestCase):
    """``classify(probe_result)`` → (emoji, reason). Pure logic, no network."""

    def test_200_rss_xml_is_live(self):
        """200 OK with <?xml + <rss = ✅."""
        self.assertEqual(
            _check.classify((200, "application/rss+xml",
                             b'<?xml version="1.0"?><rss version="2.0">')),
            ("✅", "HTTP 200, RSS/Atom XML"))

    def test_200_atom_xml_is_live(self):
        """200 OK with <?xml + <feed = ✅ (Atom format)."""
        self.assertEqual(
            _check.classify((200, "application/atom+xml",
                             b'<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">')),
            ("✅", "HTTP 200, RSS/Atom XML"))

    def test_200_html_body_keeps_warning(self):
        """200 OK but body is HTML (Pravda / The National Interest) = ⚠️."""
        # Per the OPML header convention: ✅ requires HTTP 200 + XML.
        self.assertEqual(
            _check.classify((200, "text/html",
                             b"<!DOCTYPE html><html><head><title>Pravda</title>")),
            ("⚠️", "HTTP 200, HTML body"))

    def test_403_cloudflare_is_warning(self):
        """403 (Cloudflare bot-block; ISW-style) = ⚠️."""
        self.assertEqual(
            _check.classify((403, "text/html", b"")),
            ("⚠️", "HTTP 403"))

    def test_404_retired_url_is_warning(self):
        """404 (retired URL; RUSI-style) = ⚠️."""
        self.assertEqual(
            _check.classify((404, "text/plain", b"")),
            ("⚠️", "HTTP 404"))

    def test_429_too_many_requests_is_transient(self):
        """429 = 🟡 (back off and retry; do NOT drop — gdeltproject.org class)."""
        self.assertEqual(
            _check.classify((429, "text/html", b"Rate limit exceeded")),
            ("🟡", "HTTP 429 Too Many Requests"))

    def test_429_with_html_body_still_transient(self):
        """429 takes precedence even when the body is HTML — operator should
        slow FreshRSS, regardless of body shape."""
        self.assertEqual(
            _check.classify((429, "text/html",
                             b"<!DOCTYPE html><html><body>rate limited</body></html>")),
            ("🟡", "HTTP 429 Too Many Requests"))

    def test_429_takes_precedence_over_4xx_branch(self):
        """Defensive order check: 429 returns 🟡 not ⚠️ even though 429 ≥ 400.
        Guards against future regressions if someone reorders the if-chain."""
        emoji, _ = _check.classify((429, "text/plain", b""))
        self.assertEqual(emoji, "🟡")

    def test_500_unreachable(self):
        """5xx = ❌ (operator perspective: server failure)."""
        self.assertEqual(
            _check.classify((503, "text/plain", b"")),
            ("❌", "HTTP 503"))

    def test_network_error_is_unreachable(self):
        """status='err' tag (DNS / TLS / timeout) = ❌."""
        emoji, reason = _check.classify(("err", "URLError: timeout", b""))
        self.assertEqual(emoji, "❌")
        self.assertIn("URLError", reason)

    def test_200_unrecognised_body_is_warning(self):
        """200 OK but body not recognised (defense in depth) = ⚠️."""
        self.assertEqual(
            _check.classify((200, "", b"")),
            ("⚠️", "HTTP 200, body not recognised"))

    def test_302_redirect_is_warning(self):
        """302 (no follow) = ⚠️ so operator knows the URL is stale."""
        self.assertEqual(
            _check.classify((302, "text/html", b"")),
            ("⚠️", "HTTP 302 redirect (no follow)"))

    def test_200_rss_with_utf8_bom_is_live(self):
        """200 OK with UTF-8 BOM + raw <rss> = ✅ (servers that omit <?xml)."""
        body = b"\xef\xbb\xbf<rss version=\"2.0\"><channel>"
        self.assertEqual(
            _check.classify((200, "application/rss+xml", body)),
            ("✅", "HTTP 200, RSS/Atom XML"))

    def test_200_atom_bare_no_prolog_is_live(self):
        """200 OK with bare <feed> (no <?xml declaration) = ✅ (lenient path)."""
        body = b'<feed xmlns="http://www.w3.org/2005/Atom">'
        self.assertEqual(
            _check.classify((200, "application/atom+xml", body)),
            ("✅", "HTTP 200, RSS/Atom XML"))

    def test_200_html_with_literal_rss_in_body_is_warning(self):
        """Defense in depth: an HTML page that mentions <rss> in text stays ⚠️.

        The bare-rss lenient path rejects HTML pages whose body contains a
        `<html>...</html>` shell. This guards against false-positive ✅ on
        a Cloudflare error page, debug page, or any HTML page that happens
        to mention `<rss>`. Must be HTML body, not RSS/Atom.
        """
        body = (
            b"<!DOCTYPE html><html><head><title>Cloudflare</title></head>"
            b"<body>RSS feed unavailable; please contact admin. "
            b"<rss>example</rss></body></html>"
        )
        emoji, reason = _check.classify((200, "text/html", body))
        self.assertEqual(emoji, "⚠️", f"HTML page with literal <rss> must stay ⚠️, got {emoji!r}: {reason}")
        self.assertIn("HTML body", reason)


class TestLoadOpml(unittest.TestCase):
    """``load_opml(opml/feeds.opml)`` reads the real file correctly."""

    def test_categories_count_11(self):
        """feeds.opml has 11 top-level outlines (Norske aviser → Sport SIR-2)."""
        groups = _check.load_opml(OPML)
        self.assertEqual(len(groups), 11,
                         f"Expected 11 category groups, got {len(groups)}: "
                         f"{[cat for cat, _ in groups]}")

    def test_total_rss_count_64(self):
        """feeds.opml has 64 RSS feeds total (verified 2026-06-24)."""
        groups = _check.load_opml(OPML)
        total = sum(len(rss) for _, rss in groups)
        self.assertEqual(total, 64,
                         f"Expected 64 RSS feeds, got {total}")

    def test_filter_outlines_substring(self):
        """filter_outlines() reduces a list by URL substring."""
        groups = _check.load_opml(OPML)
        all_rss = [o for _, rss in groups for o in rss]
        # Single-match test on RUSI (which has ⚠️ currently).
        filtered = _check.filter_outlines(all_rss, "rusi.org")
        self.assertEqual(len(filtered), 1,
                         f"Expected 1 rusi.org feed, got {len(filtered)}")
        self.assertIn("rusi.org", filtered[0].get("xmlUrl", ""))


class TestFilterOutlines(unittest.TestCase):
    """``filter_outlines`` directly, with empty + non-matching filter."""

    def test_no_filter_returns_all(self):
        groups = _check.load_opml(OPML)
        all_rss = [o for _, rss in groups for o in rss]
        self.assertEqual(len(_check.filter_outlines(all_rss, "")), len(all_rss))

    def test_no_match_returns_empty(self):
        groups = _check.load_opml(OPML)
        all_rss = [o for _, rss in groups for o in rss]
        self.assertEqual(_check.filter_outlines(all_rss, "definitely-not-a-feed.example"), [])


class TestEmitWorkingOPML(unittest.TestCase):
    """``emit_working_opml`` — re-derive opml/working.opml with ✅/🟡 only.

    Network-free: caller passes a synthetic results list and a tmp out_path.
    Asserts the filter (✅ + 🟡 only) and the date-stamped <title>.
    """

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        # Build synthetic outline elements matching the shape run() produces.
        def outline(title, url):
            return ET.Element("outline", {
                "type": "rss",
                "text": title,
                "title": title,
                "xmlUrl": url,
                "htmlUrl": url.rsplit("/", 1)[0],
            })
        self.results = [
            ("CatA", outline("A1-live", "https://a1.example/rss"),
             "A1-live", "https://a1.example/rss", "✅", "HTTP 200, RSS/Atom XML"),
            ("CatA", outline("A2-transient", "https://a2.example/rss"),
             "A2-transient", "https://a2.example/rss", "🟡", "HTTP 429 Too Many Requests"),
            ("CatA", outline("A3-broken", "https://a3.example/rss"),
             "A3-broken", "https://a3.example/rss", "⚠️", "HTTP 404"),
            ("CatB", outline("B1-unreachable", "https://b1.example/rss"),
             "B1-unreachable", "https://b1.example/rss", "❌", "HTTP 503"),
            ("CatB", outline("B2-live", "https://b2.example/rss"),
             "B2-live", "https://b2.example/rss", "✅", "HTTP 200, RSS/Atom XML"),
        ]

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_emit_working_opml_keeps_only_live_and_transient(self):
        """✅ + 🟡 survive; ⚠️ + ❌ are dropped."""
        out_path = os.path.join(self.tmpdir, "working.opml")
        _check.emit_working_opml(self.results, out_path, "2026-06-24")
        tree = ET.parse(out_path)
        cats = tree.getroot().find("body").findall("outline")
        texts_in_file = []
        for c in cats:
            cat_text = c.get("text")
            for sub in c.findall("outline"):
                texts_in_file.append((cat_text, sub.get("text")))
        self.assertIn(("CatA", "A1-live"), texts_in_file)
        self.assertIn(("CatA", "A2-transient"), texts_in_file)
        self.assertNotIn(("CatA", "A3-broken"), texts_in_file)
        self.assertNotIn(("CatB", "B1-unreachable"), texts_in_file)
        self.assertIn(("CatB", "B2-live"), texts_in_file)
        # And we should NOT have empty categories left around.
        cat_texts = [c.get("text") for c in cats]
        self.assertIn("CatA", cat_texts)
        self.assertIn("CatB", cat_texts)

    def test_emit_working_opml_preserves_xmlurl_htmlurl(self):
        """Each emitted outline keeps xmlUrl + htmlUrl verbatim from the input."""
        out_path = os.path.join(self.tmpdir, "working_urls.opml")
        _check.emit_working_opml(self.results, out_path, "2026-06-24")
        tree = ET.parse(out_path)
        url_set = set()
        for sub in tree.getroot().iter("outline"):
            if sub.get("xmlUrl"):
                url_set.add((sub.get("text"), sub.get("xmlUrl"), sub.get("htmlUrl")))
        self.assertIn(("A1-live", "https://a1.example/rss", "https://a1.example"), url_set)
        self.assertIn(("A2-transient", "https://a2.example/rss", "https://a2.example"), url_set)
        self.assertIn(("B2-live", "https://b2.example/rss", "https://b2.example"), url_set)

    def test_emit_working_opml_has_date_stamp_in_title(self):
        """The <title> embeds today's probe date so staleness is visible."""
        out_path = os.path.join(self.tmpdir, "working_dated.opml")
        _check.emit_working_opml(self.results, out_path, "2026-06-24")
        tree = ET.parse(out_path)
        title = tree.getroot().find("head").find("title").text
        self.assertIn("probe-passed", title,
                      f"title should mark file as probe-passed snapshot, got {title!r}")
        self.assertIn("2026-06-24", title,
                      f"title should embed today's date, got {title!r}")

    def test_emit_working_opml_empty_results_writes_empty_body(self):
        """All-broken results still produce a valid OPML with empty body.

        Empty body is preferable to overwriting with stale content from a
        prior run; the operator reads "no survivors today" at a glance.
        """
        out_path = os.path.join(self.tmpdir, "working_empty.opml")
        _check.emit_working_opml([], out_path, "2026-06-24")
        tree = ET.parse(out_path)
        body = tree.getroot().find("body")
        self.assertEqual(len(body.findall("outline")), 0)
        title = tree.getroot().find("head").find("title").text
        self.assertIn("2026-06-24", title)


if __name__ == "__main__":
    unittest.main(verbosity=2)
