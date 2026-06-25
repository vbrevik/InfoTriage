#!/usr/bin/env python3
"""Spike R2: Fresh corpus fetcher for NRK / BBC / TASS.

READ-ONLY — writes ONLY to .spike/items.json.
Never touches data/verdicts.jsonl or any real feed file.

Uses defusedxml.ElementTree exclusively (XXE/billion-laughs prevention).
The unsafe stdlib parser is intentionally excluded (see RESEARCH Pitfall 7).

Output: .spike/items.json — list of dicts with keys:
    id        str   "{source}_{NNN:03d}"  e.g. nrk_001
    source    str   "nrk" | "bbc" | "tass"
    title     str
    summary   str   (empty string when absent)
    link      str
    lang      str   "no" | "en" | "ru"
    published str   ISO-8601 or raw pubDate string
"""

import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

import defusedxml.ElementTree as ET

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

FEEDS = [
    {
        "source": "nrk",
        "lang": "no",
        "url": "https://www.nrk.no/nyheter/siste.rss",
    },
    {
        "source": "bbc",
        "lang": "en",
        "url": "https://feeds.bbci.co.uk/news/world/rss.xml",
    },
    {
        "source": "tass",
        "lang": "ru",
        "url": "https://tass.com/rss/v2.xml",
    },
]

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT_PATH = os.path.join(ROOT, ".spike", "items.json")

# RSS 2.0 namespaces encountered in the wild
NS = {
    "media": "http://search.yahoo.com/mrss/",
    "dc":    "http://purl.org/dc/elements/1.1/",
    "atom":  "http://www.w3.org/2005/Atom",
    "content": "http://purl.org/rss/1.0/modules/content/",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _text(el, tag: str, default: str = "") -> str:
    """Return stripped text of first child matching tag, or default."""
    child = el.find(tag)
    if child is not None and child.text:
        return child.text.strip()
    return default


def _parse_date(raw: str) -> str:
    """Best-effort normalise to ISO-8601 UTC; return raw string on failure."""
    if not raw:
        return ""
    for fmt in (
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
    ):
        try:
            dt = datetime.strptime(raw.strip(), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).isoformat()
        except ValueError:
            continue
    return raw.strip()


def fetch_rss(feed_cfg: dict) -> list[dict]:
    """Fetch one RSS feed and return normalised item list."""
    source = feed_cfg["source"]
    lang   = feed_cfg["lang"]
    url    = feed_cfg["url"]

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "InfoTriage-Spike/0.1 (concept spike; read-only research tool)",
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw_bytes = resp.read()
    except Exception as exc:
        print(f"[{source}] FETCH ERROR: {exc}", file=sys.stderr)
        return []

    # defusedxml.ElementTree.fromstring — safe drop-in with XXE protection
    try:
        root = ET.fromstring(raw_bytes)
    except Exception as exc:
        print(f"[{source}] PARSE ERROR: {exc}", file=sys.stderr)
        return []

    # Handle both <rss><channel> and Atom <feed> roots
    channel = root.find("channel") if root.tag == "rss" else root

    items: list[dict] = []
    counter = 1

    for item_el in channel.findall("item"):
        title   = _text(item_el, "title")
        link    = _text(item_el, "link")
        summary = _text(item_el, "description")
        pub_raw = _text(item_el, "pubDate") or _text(item_el, "dc:date")
        published = _parse_date(pub_raw)

        items.append(
            {
                "id":        f"{source}_{counter:03d}",
                "source":    source,
                "title":     title,
                "summary":   summary,
                "link":      link,
                "lang":      lang,
                "published": published,
            }
        )
        counter += 1

    print(f"[{source}] fetched {len(items)} items", file=sys.stderr)
    return items


def main() -> None:
    all_items: list[dict] = []

    for feed_cfg in FEEDS:
        items = fetch_rss(feed_cfg)
        all_items.extend(items)

    total = len(all_items)
    sources = {i["source"] for i in all_items}

    print(
        f"Total items: {total} | sources: {sorted(sources)}",
        file=sys.stderr,
    )

    if total < 30:
        print(
            f"WARNING: only {total} items fetched (need >=30). "
            "Re-run on a busier news day (see CONTEXT D-02 / Assumption A3).",
            file=sys.stderr,
        )

    with open(OUT_PATH, "w", encoding="utf-8") as fh:
        json.dump(all_items, fh, ensure_ascii=False, indent=2)

    print(f"Written: {OUT_PATH}", file=sys.stderr)


if __name__ == "__main__":
    main()
