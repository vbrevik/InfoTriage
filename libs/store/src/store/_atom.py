#!/usr/bin/env python3
"""_atom.py — pull-on-demand Atom projection for InfoTriage.

Exposes one public function:

    render_atom(store, limit=50) -> bytes

This is a pull-on-demand projection (D-04): it reads stored articles at call
time, filters to RSS/YouTube source types only (D-04a — email excluded), and
renders a valid RFC 4287 Atom feed via feedgen (D-04b — no hand-rolled XML).

The function depends only on the Store Protocol interface and feedgen, so it
works identically against InMemoryStore (tests) and PostgresStore (production).

Result: bytes (UTF-8 encoded XML). Callers that need a string must decode:
    render_atom(store).decode("utf-8")
(Pitfall 6: feedgen's atom_str() returns bytes, not str.)

Limit (default 50): caps the number of entries to mitigate unbounded
result materialization from a large store (T-02-05 DoS mitigation).
"""
import datetime
from typing import cast

from feedgen.feed import FeedGenerator

from ._protocol import Store

# D-04a: only RSS and YouTube source types are projected into the Atom feed;
# email (imap) items are deliberately excluded.
_ATOM_SOURCE_TYPES = ["rss", "yt"]


def render_atom(store: Store, limit: int = 50) -> bytes:
    """Pull-on-demand Atom projection of RSS+YouTube articles.

    Args:
        store: any Store implementation (InMemoryStore or PostgresStore).
        limit: maximum entries in the feed (T-02-05 DoS guard).

    Returns:
        bytes: well-formed RFC 4287 Atom XML. Deterministic for a given store
               state (list_items ordering is stable for the same data).

    Exclusion rule (D-04a): items with source_type "imap" (email) are excluded.
    """
    fg = FeedGenerator()
    fg.id("http://localhost/infotriage/atom")
    fg.title("InfoTriage")
    fg.link(href="http://localhost/", rel="alternate")
    fg.link(href="http://localhost/atom.xml", rel="self")
    fg.language("no")
    # Use a fixed epoch so the feed header timestamp is deterministic across
    # calls on the same store state (R7 idempotency). Production callers that
    # want a live "updated" can override by setting fg.updated() before calling
    # atom_str, but we keep render_atom deterministic by default.
    fg.updated(datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc))

    # Pull items from the store — D-04a filter applied in list_items call.
    items = store.list_items(source_type_in=_ATOM_SOURCE_TYPES, limit=limit)

    for item in items:
        fe = fg.add_entry(order="append")
        fe.id(item.url or f"infotriage:{item.id}")
        fe.title(item.title)
        if item.url:
            fe.link(href=item.url)
        # feedgen expects tz-aware datetime; Item.ts is AwareDatetime (always tz-aware)
        fe.published(item.ts)
        fe.updated(item.ts)
        if item.summary:
            fe.summary(item.summary)

    # Returns bytes (UTF-8 encoded XML) — callers must decode if they need str.
    # Do NOT use atom_str(pretty=True) with a text mode open(); open in binary.
    return cast(bytes, fg.atom_str(pretty=True))
