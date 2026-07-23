#!/usr/bin/env python3
"""Regression: both brief SELECTs must fetch a.body so the link view reads
from the full email body, not just the 500-char summary.

Read-only assertion on the SQL source — no Postgres connection required.
A failure here means a future edit accidentally narrowed one of the
consumer.fetch / main._ENRICHMENT_SQL row sets, which would silently drop
body-derived URLs from the user-facing links surface.
"""
import re

from apps.brief import consumer as brief_consumer
from apps.brief import main as brief_main


# Tolerate whitespace reformats: "a . body" or "a. body" must still match.
_A_BODY = re.compile(r"\ba\s*\.\s*body\b")
_JOIN_ARTICLES = re.compile(r"JOIN\s+infotriage\.articles\s+a\b", re.IGNORECASE)


def _as_one_line(sql: str) -> str:
    return re.sub(r"\s+", " ", sql)


def test_consumer_select_fetches_a_body() -> None:
    raw = getattr(brief_consumer, "_SELECT", None)
    assert raw, "apps.brief.consumer._SELECT must be defined"
    collapsed = _as_one_line(raw)
    match = _A_BODY.search(collapsed)
    assert match is not None, (
        f"consumer._SELECT must include a.body so verdict.ready payloads "
        f"carry the full article body to render_links(). Got: {collapsed!r}"
    )
    join_match = _JOIN_ARTICLES.search(collapsed)
    assert (
        join_match is not None
    ), "consumer._SELECT must JOIN infotriage.articles to access a.body"


def test_main_enrichment_sql_fetches_a_body() -> None:
    raw = getattr(brief_main, "_ENRICHMENT_SQL", None)
    assert raw, "apps.brief.main._ENRICHMENT_SQL must be defined"
    collapsed = _as_one_line(raw)
    match = _A_BODY.search(collapsed)
    assert match is not None, (
        f"main._ENRICHMENT_SQL must include a.body so /sab?view=links "
        f"renders URLs from the full body. Got: {collapsed!r}"
    )
    join_match = _JOIN_ARTICLES.search(collapsed)
    assert (
        join_match is not None
    ), "main._ENRICHMENT_SQL must JOIN infotriage.articles to access a.body"
