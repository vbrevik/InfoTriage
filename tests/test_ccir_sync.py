#!/usr/bin/env python3
"""tests/test_ccir_sync.py — DRIFT-1 closure invariant.

`apps/triage/digest.py:CCIR_ORDER` and `ccir.md`'s top-level `- **CODE**`
bullets must agree on the same set of CCIR ids. Drift silently drops new
(or stale) ids from BLUF/SAB renders. `digest.py` already raises
AssertionError at import on drift; this test mirrors the invariant as
pytest assertions so CI / pre-commit surfaces drift before `digest.py` is
imported in anger.
"""
import os
import re
from collections import Counter

# Top-level import also forces digest.py's own runtime assert to fire —
# that's the same check, expressed twice on purpose (one belt, one braces).
import digest  # resolved via apps/triage on pythonpath

CCIR_MD = os.path.join(os.path.dirname(__file__), "..", "ccir.md")
# Same regex as the runtime guard in apps/triage/digest.py.
CCIR_BULLET_RE = re.compile(r"^\s*-\s+\*\*([A-Z]{3,4}-\d+)\b", re.MULTILINE)
CCIR_ID_RE = re.compile(r"^[A-Z]{3,4}-\d+$")


def ccir_md_ids():
    """Parse ccir.md for top-level CCIR bullets (`- **CODE** ...`)."""
    return set(CCIR_BULLET_RE.findall(open(CCIR_MD, encoding="utf-8").read()))


def ccir_order_ids():
    """Extract CCIR ids from apps/triage/digest.py:CCIR_ORDER."""
    return {cid for cid, _ in digest.CCIR_ORDER}


def test_ids_match():
    """The id-set in CCIR_ORDER equals the id-set in ccir.md top-level bullets."""
    order_ids = ccir_order_ids()
    md_ids = ccir_md_ids()
    missing_in_md = sorted(order_ids - md_ids)
    missing_in_order = sorted(md_ids - order_ids)
    problems = []
    if missing_in_md:
        problems.append(f"in CCIR_ORDER but not in ccir.md: {missing_in_md}")
    if missing_in_order:
        problems.append(f"in ccir.md but not in CCIR_ORDER: {missing_in_order}")
    assert not problems, (
        "CCIR drift detected — " + "; ".join(problems) + ". Update both files to match."
    )


def test_ccir_order_has_no_duplicates():
    """CCIR_ORDER entries must be unique ids (no `(PIR-1, ...), (PIR-1, ...)`)."""
    all_ids = [c for c, _ in digest.CCIR_ORDER]
    dupes = [k for k, n in Counter(all_ids).items() if n > 1]
    assert not dupes, f"CCIR_ORDER has duplicate ids: {dupes}"


def test_ccir_md_has_no_duplicates():
    """ccir.md top-level bullets must be unique ids (no two `- **PIR-1** ...`)."""
    all_bullets = CCIR_BULLET_RE.findall(open(CCIR_MD, encoding="utf-8").read())
    dupes = [k for k, n in Counter(all_bullets).items() if n > 1]
    assert not dupes, f"ccir.md has duplicate CCIR bullets: {dupes}"


def test_ccir_ids_are_canonical():
    """Every CCIR id (in CCIR_ORDER or ccir.md) matches ^[A-Z]{3,4}-\\d+$."""
    bad_order = [c for c, _ in digest.CCIR_ORDER if not CCIR_ID_RE.match(c)]
    assert not bad_order, f"CCIR_ORDER has malformed ids: {bad_order}"
    bad_md = [c for c in ccir_md_ids() if not CCIR_ID_RE.match(c)]
    assert not bad_md, f"ccir.md has malformed CCIR bullet ids: {bad_md}"


def test_ccir_order_titles_are_nonempty():
    """Every CCIR_ORDER tuple carries a non-empty title for markdown rendering."""
    bad = [
        (cid, title)
        for cid, title in digest.CCIR_ORDER
        if not title or not title.strip()
    ]
    assert not bad, f"CCIR_ORDER entries with empty/whitespace titles: {bad}"


# ── Registry sync guards (single source of truth = contracts.ccir) ───────────

_FEEDS_OPML = os.path.join(
    os.path.dirname(__file__), "..", "apps", "opml", "feeds.opml"
)
_PMESII_RE = re.compile(r"`PMESII:\s*([^`]+)`")
_TESSOC_RE = re.compile(r"`TESSOC:\s*([^`]+)`")


def _ccir_md_trailers():
    """Parse ccir.md per-requirement `PMESII: …` · `TESSOC: …` trailers.

    Returns {id: (pmesii_tuple, tessoc_tuple)}.
    """
    text = open(CCIR_MD, encoding="utf-8").read()
    blocks = re.split(r"(?m)(?=^- \*\*[A-Z]{3,4}-\d+)", text)
    out = {}
    for b in blocks:
        m = re.match(r"- \*\*([A-Z]{3,4}-\d+)", b)
        if not m:
            continue
        pm, te = _PMESII_RE.search(b), _TESSOC_RE.search(b)
        if pm and te:
            out[m.group(1)] = (
                tuple(x.strip() for x in pm.group(1).split(",")),
                tuple(x.strip() for x in te.group(1).split(",")),
            )
    return out


def test_registry_pmesii_tessoc_match_ccir_md():
    """Each active spec's pmesii/tessoc tuples equal ccir.md's trailers."""
    from contracts.ccir import active_specs

    trailers = _ccir_md_trailers()
    mismatches = []
    for c in active_specs():
        expected = trailers.get(c.id)
        if expected != (c.pmesii, c.tessoc):
            mismatches.append((c.id, (c.pmesii, c.tessoc), expected))
    assert not mismatches, "registry ↔ ccir.md PMESII/TESSOC drift: " + "; ".join(
        f"{cid}: registry={r} ccir.md={m}" for cid, r, m in mismatches
    )


def test_feeds_opml_ccir_groups_in_sync():
    """The generated CCIR feed groups match apps/opml/feeds.opml. Run
    `make ccir-sync` if this fails."""
    from contracts.ccir import render_feeds_opml_groups

    on_disk = open(_FEEDS_OPML, encoding="utf-8").read()
    assert (
        render_feeds_opml_groups() in on_disk
    ), "feeds.opml CCIR groups drifted from the registry — run `make ccir-sync`"
