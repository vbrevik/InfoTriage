#!/usr/bin/env python3
"""test_brief_renderer_links.py — render_links() unit tests (RED)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from apps.brief.renderer import render_links, _strip_url_trailing_punct


def _row(
    item_id: str = "row1",
    title: str = "Sample title",
    summary: str = "",
    body: str = "",
    source: str = "Newsletter",
    score: int = 7,
    url: str = "imap://pop.example.com/uid-A",
) -> dict:
    return {
        "item_id": item_id,
        "title": title,
        "summary": summary,
        "body": body,
        "source": source,
        "url": url,
        "ccir": "none",
        "cnr": "II",
        "score": score,
        "bucket": "keep",
        "why": "test",
    }


def test_render_links_returns_markdown_string():
    rows = [_row(summary="https://example.com/article1")]
    md = render_links(rows)
    assert isinstance(md, str)
    assert md.startswith("# InfoTriage")


def test_render_links_emits_one_line_per_url():
    rows = [
        _row(
            summary="(1) https://a.example.com/1 (2) https://b.example.com/2",
        )
    ]
    md = render_links(rows)
    assert "https://a.example.com/1" in md
    assert "https://b.example.com/2" in md
    # Both URLs should be linked.
    assert "[https://a.example.com/1](https://a.example.com/1)" in md
    assert "[https://b.example.com/2](https://b.example.com/2)" in md


def test_render_links_includes_title_and_source():
    rows = [_row(title="Top story", summary="https://example.com/1", source="NRK")]
    md = render_links(rows)
    assert "Top story" in md
    assert "NRK" in md


def test_render_links_strips_trailing_punctuation():
    # Real newsletters end links with ")" or "."
    rows = [_row(summary="See https://example.com/x.) for context.")]
    md = render_links(rows)
    # Positive round-trip invariant: the *clean* URL must round-trip whole
    # (helper strips both '.' and orphan ')'). The negative check below
    # catches any un-stripped URL form surviving in the render.
    assert "[https://example.com/x](https://example.com/x)" in md
    assert "https://example.com/x.)" not in md


def test_render_links_empty_rows():
    md = render_links([])
    assert md.startswith("# InfoTriage")
    # Zero-items sentinel must be present so we never produce a misleading empty list.
    assert "0" in md


def test_render_links_uses_body_when_summary_empty():
    rows = [_row(summary="intro only", body="https://bbc.com/p/abc")]
    md = render_links(rows)
    assert "https://bbc.com/p/abc" in md


def test_render_links_one_row_with_no_urls_renders_labeled_entry():
    # Edge: a row whose haystack has no http/https URL gets a labeled fallback so
    # the user knows it was inspected.
    rows = [_row(title="Unmarked item", summary="no url present")]
    md = render_links(rows)
    assert "Unmarked item" in md
    assert "(no outbound URL" in md


def test_render_links_sorts_by_score_descending():
    rows = [
        _row(item_id="low", score=2, summary="see https://a.com/1"),
        _row(item_id="high", score=9, summary="see https://b.com/1"),
    ]
    md = render_links(rows)
    # Sorted by score desc: row with score 9 ('high' / b.com) appears first.
    assert md.index("https://b.com/1") < md.index("https://a.com/1")


def test_render_links_preserves_wikipedia_balanced_parens():
    """Regression: the prior regex stripped at ")", truncating Wikipedia URLs.

    After the balanced-paren upgrade in apps.brief.views._OUTBOUND_URL_RE
    plus the parens-aware trailing-punctuation stripper in render_links(),
    the exact URL `https://en.wikipedia.org/wiki/Foo_(bar)` must round-trip
    whole into the rendered markdown body — including the closing ")".
    """
    url = "https://en.wikipedia.org/wiki/Foo_(bar)"
    rows = [_row(summary=f"read the relevant entry at {url} for context")]
    md = render_links(rows)
    assert (
        f"[{url}]({url})" in md
    ), f"expected balanced-paren URL to round-trip into markdown; got: {md!r}"


def test_render_links_preserves_disambiguation_parens():
    # Second Wikipedia-style pattern: longer disambiguation name with
    # underscore-anchored paren suffix (e.g. Page_(1996_film)).
    url = "https://en.wikipedia.org/wiki/Some_Page_(1996_film)"
    rows = [_row(summary=f"see {url}")]
    md = render_links(rows)
    assert f"[{url}]({url})" in md


def test_render_links_strips_orphan_trailing_close_paren():
    """Regression: the helper must strip a stray unbalanced ')' attached to
    the URL by an email client.

    The round-trip '[clean](clean)' assertion below is the strongest
    invariant: if the URL still ended in ')', the rendered link would be
    '[foo)](foo))' which cannot match '[foo](foo)'.
    """
    rows = [_row(summary="see https://example.com/foo) for context")]
    md = render_links(rows)
    assert "[https://example.com/foo](https://example.com/foo)" in md


def test_render_links_strips_orphan_paren_then_period():
    """Regression: a period AFTER an unbalanced ')' must also be stripped.

    Example: "see https://example.com/foo). for context" → the trailing
    ').' is entirely email-mid-sentence punctuation, so the link target
    must be 'foo' (no '.', no ')') by the time the helper returns. The
    round-trip '[foo](foo)' assertion catches both regressions at once:
    the helper's while-loop walks each trailing char individually so
    multi-char tails like ').' collapse cleanly.
    """
    rows = [_row(summary="see https://example.com/foo). for context")]
    md = render_links(rows)
    assert "[https://example.com/foo](https://example.com/foo)" in md


def test_render_links_strips_multiple_orphan_close_parens():
    """Regression: multiple unbalanced ')' chars must all be stripped.

    Example: "see https://example.com/foo)) for context" → two orphan
    closing parens; both must be removed so the link target equals the
    canonical URL. The while-loop iterates until the tail is clean.
    """
    rows = [_row(summary="see https://example.com/foo)) for context")]
    md = render_links(rows)
    assert "[https://example.com/foo](https://example.com/foo)" in md


@pytest.mark.parametrize(
    ("input_url", "expected"),
    [
        # Balanced parens (Wikipedia disambiguation pages): preserved whole
        (
            "https://en.wikipedia.org/wiki/Foo_(bar)",
            "https://en.wikipedia.org/wiki/Foo_(bar)",
        ),
        (
            "https://en.wikipedia.org/wiki/Foo_(bar).",
            "https://en.wikipedia.org/wiki/Foo_(bar)",
        ),
        (
            "https://en.wikipedia.org/wiki/Foo_(bar)_(baz)",
            "https://en.wikipedia.org/wiki/Foo_(bar)_(baz)",
        ),
        # Plain and period-only tails: stripped
        ("https://example.com/foo", "https://example.com/foo"),
        ("https://example.com/foo.", "https://example.com/foo"),
        ("https://example.com/foo,", "https://example.com/foo"),
        # Orphan ')' with no matching '(' anywhere: stripped
        ("https://example.com/foo)", "https://example.com/foo"),
        # Orphan ')' followed by '.': both stripped (multi-char tail)
        ("https://example.com/foo).", "https://example.com/foo"),
        # Multiple orphan ')': all stripped
        ("https://example.com/foo))", "https://example.com/foo"),
        # Punctuation storm without parens: all stripped
        ("https://example.com/foo.!?", "https://example.com/foo"),
        # Percent-encoded ')' (no literal ')'): must NOT be stripped.
        ("https://x.com/search?q=hello%29", "https://x.com/search?q=hello%29"),
        # Empty input: helper short-circuits and returns ''.
        ("", ""),
        # Mixed encoded-then-literal ')': literal ')' stripped, %29 kept
        # (helper's '(' scan ignores %29 because there is no literal '(').
        ("https://x.com/foo%29)", "https://x.com/foo%29"),
    ],
)
def test_strip_url_trailing_punct_units(input_url: str, expected: str) -> None:
    """Unit-level invariant on _strip_url_trailing_punct: input URL maps to
    expected cleaned URL. Locks the helper's order-of-ops and balanced-paren
    rule independent of markdown rendering.
    """
    assert _strip_url_trailing_punct(input_url) == expected


def test_render_links_surfaces_url_from_long_body_when_summary_short() -> None:
    """Regression: render_links must read row.body, not only row.summary.

    Summary is capped at ~500 chars by the ingest pipeline, so URLs that
    live deep in the email body dropped out of the link view before
    consumer._SELECT started fetching a.body. The fixture here puts the
    URLs only in body; surface assertions lock the haystack contract.
    """
    body_text = (
        "...newsletter open. The full article is at "
        "https://example.com/full-article. Related coverage: "
        "https://example.com/related."
    )
    rows = [_row(summary="Top headline, teaser only", body=body_text)]
    md = render_links(rows)
    assert "[https://example.com/full-article](https://example.com/full-article)" in md
    assert "[https://example.com/related](https://example.com/related)" in md


def test_render_links_surfaces_urls_from_both_summary_and_body() -> None:
    """If different URLs appear in summary vs body, both surface.

    Locks the haystack union behavior: title + summary + body are joined
    with whitespace, so distinct URLs from each field are both captured;
    duplicates across fields yield one entry via _OUTBOUND_URL_RE.findall.
    """
    rows = [
        _row(
            summary="Lead link https://example.com/lead",
            body="Follow-up at https://example.com/followup.",
        )
    ]
    md = render_links(rows)
    assert "[https://example.com/lead](https://example.com/lead)" in md
    assert "[https://example.com/followup](https://example.com/followup)" in md


def test_render_links_surfaces_multiple_body_urls_with_balanced_paren() -> None:
    """Multi-URL body AND one balanced-paren Wikipedia URL — locks both
    the body passthrough AND the recently-merged _strip_url_trailing_punct
    helper on the same round-trip.

    Complements (does not replace) test_render_links_preserves_wikipedia_
    balanced_parens, which puts the URL in summary; this one puts it in
    body, exercising the URL-in-body stripper path.
    """
    body_text = (
        "Primary read https://example.com/primary. "
        "Disambiguation entry at "
        "https://en.wikipedia.org/wiki/Foo_(bar). "
        "Third source https://example.com/third."
    )
    rows = [_row(summary="Roundup", body=body_text)]
    md = render_links(rows)
    assert "[https://example.com/primary](https://example.com/primary)" in md
    assert (
        "[https://en.wikipedia.org/wiki/Foo_(bar)](https://en.wikipedia.org/wiki/Foo_(bar))"
        in md
    )
    assert "[https://example.com/third](https://example.com/third)" in md
