#!/usr/bin/env python3
"""test_brief_views_links.py — 'links' view filter tests (RED).

The links view is a personal reading-queue lens: it keeps items whose
title / summary / body contain at least one outbound http/https URL.
Unlike COP/CIP/CRP it deliberately bypasses the CCIR scorer — newsletters
with article links are surfaced whether or not they match a CCIR.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from apps.brief.views import filter_rows


def _row(
    item_id: str = "row1",
    title: str = "",
    summary: str = "",
    body: str = "",
    source: str = "Newsletter",
    ccir: str = "none",
    score: int = 0,
    url: str = "",
) -> dict:
    return {
        "item_id": item_id,
        "title": title,
        "summary": summary,
        "body": body,
        "source": source,
        "url": url,
        "ccir": ccir,
        "cnr": "II" if ccir != "none" else "none",
        "score": score,
        "bucket": "keep",
        "why": "test",
        "pmesii": "",
        "tessoc": "",
    }


class TestLinksView(unittest.TestCase):
    def test_links_keeps_items_with_outbound_http_url(self):
        rows = [
            _row(
                title="Newsletter #1",
                summary="See https://example.com/article1 for the full report.",
            )
        ]
        result = filter_rows(rows, "links")
        self.assertEqual(len(result), 1)

    def test_links_keeps_items_with_outbound_https_url(self):
        rows = [_row(summary="Read more at http://nrk.no/another here.")]
        result = filter_rows(rows, "links")
        self.assertEqual(len(result), 1)

    def test_links_drops_items_with_no_url(self):
        rows = [_row(title="Plain update", summary="No links here at all.")]
        result = filter_rows(rows, "links")
        self.assertEqual(result, [])

    def test_links_searches_body_not_just_summary(self):
        # Link lives in body, not in summary (which is truncated to 500 chars).
        rows = [
            _row(
                summary="Newsletter intro text…",
                body="Full article URL: https://thebarentsobserver.com/security/2026/07/01",
            )
        ]
        result = filter_rows(rows, "links")
        self.assertEqual(len(result), 1, "body text must be searched for links")

    def test_links_bypasses_ccir_scoring(self):
        # An email newsletter that has a link but no CCIR match must still surface.
        rows = [
            _row(
                item_id="1",
                title="Linked article",
                summary="https://example.com/1",
                ccir="none",  # not CCIR-relevant
                score=3,
            )
        ]
        result = filter_rows(rows, "links")
        self.assertEqual(
            len(result),
            1,
            "links view must not filter by CCIR (it's a personal reading queue)",
        )

    def test_links_filters_multiple_urls_in_one_row(self):
        rows = [
            _row(
                summary="Two links https://a.example.com/1 and https://b.example.com/2"
            )
        ]
        result = filter_rows(rows, "links")
        self.assertEqual(len(result), 1)

    def test_links_ignores_non_http_schemes(self):
        rows = [
            _row(
                title="Mailto-only",
                summary="Contact me at mailto:foo@example.com or call 555-1234.",
            ),
            _row(
                title="Plain text",
                summary="No urls whatsoever.",
            ),
        ]
        result = filter_rows(rows, "links")
        self.assertEqual(result, [], "mailto: and phone numbers are not article links")

    def test_links_handles_malformed_url_gracefully(self):
        # A near-URL like "://example" should not crash.
        rows = [_row(summary="see ://example for context, also https://ok.com/1")]
        result = filter_rows(rows, "links")
        self.assertEqual(len(result), 1)

    def test_links_view_unknown_raises(self):
        # Unknown view must raise — fail loud rather than silently return
        # everything (mirrors the existing COP/CIP/CRP contract).
        with self.assertRaises(ValueError):
            filter_rows([], "bogus")

    def test_links_accepts_crp_params_passthrough(self):
        # crp_params can still be applied on top of the links view filter.
        rows = [
            _row(item_id="hi", summary="https://a.com/1", score=9),
            _row(item_id="lo", summary="https://b.com/1", score=3),
        ]
        result = filter_rows(rows, "links", {"min_score": "5"})
        self.assertEqual([r["item_id"] for r in result], ["hi"])


if __name__ == "__main__":
    unittest.main()
