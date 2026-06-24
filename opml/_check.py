#!/usr/bin/env python3
"""opml/_check.py — bulk health-check of every feed in opml/feeds.opml.

Iterates every ``<outline type="rss" xmlUrl="...">`` in feeds.opml, GET-probes
the URL with a FreshRSS-equivalent Mozilla User-Agent, and classifies each
as:

  ✅ live      HTTP 200 + body is RSS/Atom XML
  🟡 transient HTTP 429 Too Many Requests — operator should slow FreshRSS
                  refresh rate; do NOT drop, do NOT recreate, the upstream
                  is alive but throttling us. Distinct from ⚠️ so consecutive
                  429s cannot trigger FreshRSS auto-remove (gdeltproject.org).
  ⚠️ broken    403 / 404 / 302 (no follow) / 200 with non-XML body
                  — fix the URL, recreate via rss-bridge, or drop.
  ❌ unreachable  5xx / DNS / TLS / timeout / connection refused

Output: a markdown report grouped by top-level outline (Norske aviser,
Verdensnyheter, etc.) with a status legend, per-feed rows (status, feed,
URL, notes), a summary, and two tail blocks: "🟡 Transient feeds (action:
back off)" listing every HTTP 429 feed (slow FreshRSS refresh rate; do NOT
drop or recreate — upstream is alive, just throttling us) and "Suggested
⚠️ actions" listing every permanently-broken feed so the operator can
recreate via rss-bridge or drop.

Closes ``CONCERNS.md`` MINOR-3 ("⚠️ flagging is empirical, no auto-detection").

Usage::

  python3 opml/_check.py                                  # report to stdout
  python3 opml/_check.py --out data/feed-health.md        # also write to file
  python3 opml/_check.py --url-filter understandingwar.org  # only probe matching
  python3 opml/_check.py --ua 'curl/8.4.0'               # override UA
  python3 opml/_check.py --timeout 8                     # per-feed timeout (sec)
  python3 opml/_check.py --workers 8                      # parallel probe workers (default 8)

Stdlib only — urllib.request, xml.etree.ElementTree, concurrent.futures, argparse.
"""
import argparse
import concurrent.futures
import datetime
import io
import os
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

# FreshRSS-default UA-ish: a Chrome UA that FreshRSS can be configured to
# mimic. Adjusts past any common Cloudflare/JS-challenge layers that 403 pure
# bot UAs (curl, wget, Go-http-client). Override per-site via --ua as needed.
#
# Must be pure ASCII: urllib sends the User-Agent header as a latin-1-encoded
# byte string; any non-latin-1 codepoint (e.g. em-dash U+2014) raises
# UnicodeEncodeError on EVERY probe. Keep this string ASCII only.
DEFAULT_UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 "
              "(FreshRSS-style; lawfaremedia/ISW sites still 403 -- known)")
DEFAULT_TIMEOUT = 10
DEFAULT_WORKERS = 8
PROBE_BODY_BYTES = 2048  # enough to detect <rss>/<feed> in first 1-2 KB of any feed

OPML_HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "feeds.opml")


def probe(url, ua=DEFAULT_UA, timeout=DEFAULT_TIMEOUT):
    """GET the URL; return ``(status|err-str, content_type, body_bytes)``.

    Uses GET instead of HEAD because many feeds (CNN legacy, some BBC mirror
    hosts) silently 405 on HEAD — we want to validate the *real* payload
    FreshRSS will receive. HTTP errors are NOT exception failures: 4xx/5xx
    are exactly what we want to detect (bot-block, retired URL, server down).
    """
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": ua,
            "Accept": ("application/rss+xml,application/atom+xml,"
                       "application/xml;q=0.9,text/xml;q=0.8,*/*;q=0.5"),
        })
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.headers.get("Content-Type", ""), r.read(PROBE_BODY_BYTES)
    except urllib.error.HTTPError as e:
        try:
            body = e.read(PROBE_BODY_BYTES) if hasattr(e, "read") else b""
        except Exception:
            body = b""
        return e.code, (e.headers.get("Content-Type", "") if e.headers else ""), body
    except Exception as e:
        return "err", f"{type(e).__name__}: {e}", b""


def classify(probe_result):
    """Classify ``probe()`` output into ``(emoji, reason)``.

    Four-tier status (for the OPML header convention):
      - HTTP 429 → 🟡 transient (back off and retry; do NOT drop)
      - HTTP 5xx → ❌ unreachable
      - HTTP 4xx (other than 429) → ⚠️ broken / bot-blocked
      - HTTP 3xx → ⚠️ redirect (no follow)
      - HTTP 2xx + RSS/Atom XML → ✅ live
      - HTTP 2xx + HTML body → ⚠️ body not recognised
    """
    status, ctype, body = probe_result
    if status == "err":
        return ("❌", "network: " + str(ctype))
    try:
        n = int(status)
    except (TypeError, ValueError):
        return ("❌", f"non-int status: {status!r}")
    if n >= 500:
        return ("❌", f"HTTP {n}")
    if n == 429:
        # "Back off and retry" — GDELT-style rate limits. Operator's job is
        # to slow FreshRSS's refresh cadence, not to drop/recreate; this
        # distinguishes ⚠️ (fix or drop) from 🟡 (transient).
        return ("🟡", f"HTTP {n} Too Many Requests")
    if n >= 400:
        return ("⚠️", f"HTTP {n}")
    if n >= 300:
        return ("⚠️", f"HTTP {n} redirect (no follow)")
    # 2xx path — body shape decides live vs. broken. Strip leading UTF-8
    # BOM + whitespace before checking the root tag, so feeds that omit
    # the `<?xml` declaration (or prefix a BOM) still classify correctly.
    body_clean = body.lstrip(b"\xef\xbb\xbf \t\r\n")
    head = body_clean[:400].lower()
    root_tag = b"<rss" in head[:400] or b"<feed" in head[:400]
    is_xml_decl = head.startswith(b"<?xml") and root_tag
    # Bare-rss/atom body must look like XML: starts with the root tag NEARLY
    # IMMEDIATELY (within first 200 bytes), AND must not contain `<html`,
    # `<body`, or `<!doctype` anywhere in the first 400 bytes (otherwise the
    # page is an HTML page that happens to mention <rss> in text).
    is_xml_bare = (
        (b"<rss" in head[:200] or b"<feed" in head[:200])
        and b"<html" not in head
        and b"<body" not in head
        and b"<!doctype" not in head
    )
    if is_xml_decl or is_xml_bare:
        return ("✅", f"HTTP {n}, RSS/Atom XML")
    if head.startswith((b"<!doctype", b"<html", b"<body")):
        return ("⚠️", f"HTTP {n}, HTML body")
    return ("⚠️", f"HTTP {n}, body not recognised")


def load_opml(path):
    """Parse the OPML and return ``[(category_text, [rss_outline_dicts]), ...]``.

    Top-level ``<outline>`` elements without ``type="rss"`` are treated as
    folder categories; their rss children are collected (recursively, in case
    the OPML ever introduces sub-folders). Currently feeds.opml has flat
    folder-only structure — 11 top-level folders → 11 groups.
    """
    tree = ET.parse(path)
    root = tree.getroot()
    body = root.find("body")
    groups = []
    for folder in body.findall("outline"):
        if folder.get("type") == "rss":
            continue  # orphan top-level rss — no category assigns, skip
        cat_text = folder.get("text") or folder.get("title") or "?"
        rss = _collect_rss(folder)
        if rss:
            groups.append((cat_text, rss))
    return groups


def _collect_rss(parent):
    """Recursively collect all `type="rss"` outlines under `parent`.

    Defensive against sub-folder structures that don't currently exist in
    feeds.opml but might be added later (e.g. nested category hierarchies).
    """
    out = []
    for o in parent.findall("outline"):
        if o.get("type") == "rss":
            out.append(o)
        else:
            out.extend(_collect_rss(o))
    return out


def filter_outlines(outlines, url_filter):
    """Keep only outlines whose xmlUrl contains the substring (case-sensitive)."""
    if not url_filter:
        return list(outlines)
    return [o for o in outlines if url_filter in (o.get("xmlUrl") or "")]


def probe_and_classify(outline, ua, timeout):
    """One feed → ``(text, xmlUrl, emoji, reason)``. Used as a worker fn."""
    text = outline.get("text") or ""
    url = outline.get("xmlUrl") or ""
    if not url:
        return text, url, "❌", "no xmlUrl"
    emoji, reason = classify(probe(url, ua=ua, timeout=timeout))
    return text, url, emoji, reason


def run(opml_path, url_filter, ua, timeout, workers):
    """Probe every feed, render a markdown report. Pure: no side effects."""
    groups = load_opml(opml_path)
    flat = [(cat, o) for cat, outlines in groups for o in filter_outlines(outlines, url_filter)]
    if not flat:
        return f"# InfoTriage · feed health\n\nNo feeds match `--url-filter {url_filter!r}`.\n", []

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(probe_and_classify, o, ua, timeout): (cat, o)
                   for cat, o in flat}
        for fut in concurrent.futures.as_completed(futures):
            cat, _o = futures[fut]
            try:
                text, url, emoji, reason = fut.result()
            except Exception as e:
                text, url, emoji, reason = "", "", "❌", f"probe exception: {e}"
            results.append((cat, _o, text, url, emoji, reason))

    # Group by category, preserving OPML discovery order.
    by_cat, cat_order = {}, []
    for cat, _o, text, url, emoji, reason in results:
        if cat not in by_cat:
            by_cat[cat] = []
            cat_order.append(cat)
        by_cat[cat].append((text, url, emoji, reason))

    today = datetime.date.today().isoformat()
    n_total = len(results)
    n_ok = sum(1 for r in results if r[4] == "✅")
    n_transient = sum(1 for r in results if r[4] == "🟡")
    n_warn = sum(1 for r in results if r[4] == "⚠️")
    n_bad = sum(1 for r in results if r[4] == "❌")

    L = [
        f"# InfoTriage · feed health — {today}",
        "",
        (f"_Probed {n_total} feeds · ✅ {n_ok} live · "
         f"🟡 {n_transient} transient · "
         f"⚠️ {n_warn} broken · ❌ {n_bad} unreachable_"),
        "",
        ("**Status legend:** ✅ HTTP 200 + body is RSS/Atom XML · "
         "🟡 HTTP 429 Too Many Requests (back off) · "
         "⚠️ 403 / 404 / 200 with HTML body · "
         "❌ 5xx / network error"),
        "",
    ]
    for cat in cat_order:
        rows = by_cat[cat]
        # Sort order: ⚠️ first (operator action: fix or drop), then ❌
        # (network trouble; might recover), then ✅ (good baseline), then
        # 🟡 (visible-but-not-action: just slow FreshRSS and wait). Within
        # each status, alpha by feed name.
        order = {"⚠️": 0, "❌": 1, "✅": 2, "🟡": 3}
        rows.sort(key=lambda r: (order[r[2]], r[0]))
        L.append(f"## {cat}")
        L.append("")
        L.append("| Status | Feed | URL | Notes |")
        L.append("|---|---|---|---|")
        for text, url, emoji, reason in rows:
            L.append(f"| {emoji} | {text} | {url} | {reason} |")
        L.append("")

    # Tail sections: 🟡 (transient, action: back off) and ⚠️/❌ (broken,
    # action: fix or drop). Each block only emitted if its bucket is
    # non-empty.
    transients = [r for r in results if r[4] == "🟡"]
    broken = [r for r in results if r[4] in ("⚠️", "❌")]
    if transients:
        L.append("---")
        L.append("")
        L.append("### 🟡 Transient feeds (action: back off)")
        L.append("")
        for cat, _o, text, url, emoji, reason in transients:
            L.append(f"- **{text}** ({cat}) — {reason} · {url}")
        L.append("")
        L.append("_Recovery: rate-limit / slow FreshRSS so it doesn't hit the "
                 "1 req / 5 s upstream cap. FreshRSS auto-removes feeds after "
                 "N consecutive failures, so the goal is zero 429s — not just "
                 "a longer interval. Do NOT drop or recreate — GDELT is alive, "
                 "just throttled._")
        L.append("")
    if broken:
        L.append("---")
        L.append("")
        L.append("### Suggested ⚠️ actions")
        L.append("")
        for cat, _o, text, url, emoji, reason in broken:
            L.append(f"- **{text}** ({cat}) — {reason} · {url}")
        L.append("")
        L.append("_Recovery: recreate via rss-bridge (http://localhost:3000) or drop._")
        L.append("")
    return "\n".join(L), results


def emit_working_opml(results, out_path, today_str):
    """Write a working OPML containing only the live + transient feeds.

    Filtered from the probe-pass results: keeps only ✅ (live) and 🟡
    (transient — the upstream is alive, just throttling us). Drops ⚠️
    (broken / bot-blocked) and ❌ (5xx / network) per design contract.

    Always overwrites. Designed to be called after every full-feed probe so
    the output stays co-current with the markdown report. Skipped entirely
    by ``main()`` if ``--url-filter`` narrows the probe (a partial probe
    would silently truncate the working file).
    """
    # Single pass: group by category, keep only ✅ / 🟡 outlines.
    # `_o` is always a real <outline> element (constructed in the main thread
    # at flat list assembly), so no None-guard needed.
    by_cat, cat_order = {}, []
    for cat, o, _text, _url, emoji, _reason in results:
        if emoji not in ("✅", "🟡"):
            continue
        if cat not in by_cat:
            by_cat[cat] = []
            cat_order.append(cat)
        by_cat[cat].append(o)

    if not by_cat:
        # No live / transient feeds — write an empty body so the file still
        # exists and signals "nothing survives" to the operator. Stale
        # content is worse than an empty file.
        out = ET.Element("opml", attrib={"version": "2.0"})
        head = ET.SubElement(out, "head")
        ET.SubElement(head, "title").text = (
            f"InfoTriage — working feeds (probe-passed, {today_str})")
        ET.SubElement(out, "body")
        tree = ET.ElementTree(out)
        with io.open(out_path, "wb") as f:
            tree.write(f, encoding="utf-8", xml_declaration=True)
        return

    out = ET.Element("opml", attrib={"version": "2.0"})
    head = ET.SubElement(out, "head")
    ET.SubElement(head, "title").text = (
        f"InfoTriage — working feeds (probe-passed, {today_str})")
    body = ET.SubElement(out, "body")
    for cat in cat_order:
        cat_outline = ET.SubElement(body, "outline",
                                    attrib={"text": cat, "title": cat})
        for o in by_cat[cat]:
            # Preserve original xmlUrl, htmlUrl, type, etc.
            attrs = {k: v for k, v in o.attrib.items() if v is not None}
            ET.SubElement(cat_outline, "outline", attrib=attrs)

    tree = ET.ElementTree(out)
    if hasattr(ET, "indent"):
        ET.indent(tree, space="  ")
    with io.open(out_path, "wb") as f:
        tree.write(f, encoding="utf-8", xml_declaration=True)


def main():
    # Ensure stdout AND stderr can emit markdown with em-dash + accented
    # characters, even when the parent shell's locale is latin-1. Required
    # because the markdown contains "—" (U+2014) and "·" (U+00B7).
    # Python 3.7+ supports .reconfigure(); older interpreters are unsupported
    # (Python 3.6 reached EOL 2021-12).
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser(
        description="Bulk health-check of every feed in opml/feeds.opml.")
    ap.add_argument("--opml", default=OPML_HERE,
                    help=f"path to feeds.opml (default: {OPML_HERE})")
    ap.add_argument("--out", help="write markdown report to file (in addition to stdout)")
    ap.add_argument("--url-filter",
                    help="only probe feeds whose xmlUrl contains this substring")
    ap.add_argument("--ua", default=DEFAULT_UA, help="User-Agent string")
    ap.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT,
                    help=f"per-feed timeout (sec, default {DEFAULT_TIMEOUT})")
    ap.add_argument("--workers", type=int, default=DEFAULT_WORKERS,
                    help=f"parallel probe workers (default {DEFAULT_WORKERS})")
    ap.add_argument("--allow-broken", action="store_true",
                    help="exit 0 even if ⚠️ feeds exist (informational run; dashboards etc.).")
    ap.add_argument("--exit-on-error-only", action="store_true",
                    help="exit 1 only on ❌ (5xx / network); 🟡 and ⚠️ exit 0. "
                         "Use when transient 429s are not actionable in this CI "
                         "run AND broken feeds are tolerated. Combine with "
                         "--allow-broken for an always-exit-0 informational run.")
    args = ap.parse_args()

    md, results = run(args.opml, args.url_filter, args.ua, args.timeout, args.workers)
    print(md)

    # Compute the auto-emit target up front so we can refuse path collisions
    # with --out. Both paths are absolute to handle relative --out paths.
    working_path_default = os.path.join(os.path.dirname(OPML_HERE), "working.opml")

    if args.out:
        out_abs = os.path.abspath(args.out)
        working_abs = os.path.abspath(working_path_default)
        if out_abs == working_abs:
            # Markdown report + OPML XML have different formats; if the user
            # redirects --out and the auto-emit to the same path, one is
            # silently lost. Refuse with a clear message.
            print(f"\nERROR: --out {args.out} resolves to the same path as the "
                  f"auto-emitted opml/working.opml. These are different formats "
                  f"(markdown vs. OPML 2.0) and cannot share a single file. "
                  f"Either pass --out to a different path, or run with --url-filter "
                  f"to suppress working.opml emission.", file=sys.stderr)
            sys.exit(2)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(md)
        print(f"\n_wrote {args.out}_", file=sys.stderr)

    # Side output: also re-derive opml/working.opml (live + transient feeds
    # only) so it stays co-current with this report. Skipped when --url-filter
    # narrows the probe (we'd silently truncate the working file otherwise).
    if not args.url_filter:
        emit_working_opml(results, working_path_default,
                          datetime.date.today().isoformat())
        print(f"\n_wrote {working_path_default}_", file=sys.stderr)

    # Exit policy (quad-state):
    #   --allow-broken            → always exit 0 (informational dashboards).
    #   --exit-on-error-only      → exit 1 only on ❌ (5xx / network). Soft
    #                                gate for parsers that can't tell ❌ from
    #                                warning-class transient errors cleanly.
    #   default                   → exit 1 on 🟡 | ⚠️ | ❌. We keep 🟡 in
    #                                default-strict because consecutive 429s
    #                                WILL auto-remove the feed from
    #                                FreshRSS, so a CI gate is the safest
    #                                way to make sure the operator notices.
    if args.allow_broken:
        sys.exit(0)
    bad = "❌" in md
    warn = "⚠️" in md
    transient = "🟡" in md
    if bad:
        sys.exit(1)
    if (warn or transient) and not args.exit_on_error_only:
        n_attention = (md.count("| ⚠️ ") + md.count("| 🟡 ")
                       + md.count("| ❌ "))
        print(f"\n({n_attention} feeds need attention — run with --out for full report)",
              file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
