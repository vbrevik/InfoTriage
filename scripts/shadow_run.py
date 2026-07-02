#!/usr/bin/env python3
"""scripts/shadow_run.py — shadow-run parity check (D-08, D-09, R6).

Reads every scored row in `infotriage.enrichment` (joined to `infotriage.articles`
for title/source/summary), re-runs the proven standalone `score_item()` from
`apps/triage/triage_score.py` on each article, and prints a side-by-side table
comparing the bucket the event-driven triage worker stored vs. the bucket a
fresh standalone re-score produces.

Parity is defined as a MATCHING BUCKET per item, not an identical score — the
LLM is stochastic (D-09). Both buckets are read|maybe|skip raw vocabulary
(the worker stores raw score_item() output in infotriage.enrichment, so no
vocabulary mapping is needed for this comparison).

This script is read-only: it performs a single SELECT and writes nothing.
It never touches/deletes apps/triage/fever_triage.py.

Usage:
    python3 scripts/shadow_run.py

Env: INFOTRIAGE_PG_DSN (falls back to the dev DSN used by tests/test_store_integration.py).
"""
import os
import sys

import psycopg
from psycopg.rows import dict_row

# triage_score.py lives in apps/triage/ as a sibling module, not an installed
# package — same sys.path pattern used by apps/triage/fever_triage.py and
# apps/triage/digest.py to import it from outside that directory.
_TRIAGE_DIR = os.path.join(os.path.dirname(__file__), "..", "apps", "triage")
sys.path.insert(0, _TRIAGE_DIR)
from triage_score import score_item  # noqa: E402

DEV_DSN = "postgresql://infotriage:infotriage_dev@localhost:22000/infotriage"
PARITY_BAR = 10  # D-09: >= 10 matching buckets required before Fever cutover

QUERY = """
    SELECT e.item_id, a.title, a.summary, a.source, e.bucket, e.why
    FROM infotriage.enrichment e
    JOIN infotriage.articles a ON a.id = e.item_id
    WHERE e.bucket IS NOT NULL
    LIMIT %s
"""


def _get_dsn() -> str:
    return os.environ.get("INFOTRIAGE_PG_DSN", DEV_DSN)


def main() -> None:
    dsn = _get_dsn()
    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        rows = conn.execute(QUERY, (100,)).fetchall()

    if not rows:
        print("No enrichment rows with a stored bucket found — nothing to compare.")
        print(f"Parity verdict: NOT MET (0 < {PARITY_BAR} matching buckets required).")
        return

    header = f"{'item_id':<10} {'title':<42} {'enrichment':<10} {'rescore':<10} {'match'}"
    print(header)
    print("-" * len(header))

    matches = 0
    dedup_skipped = 0
    compared = 0
    for row in rows:
        item_id = str(row["item_id"])
        title = row["title"] or ""
        stored_bucket = row["bucket"]

        # Dedup short-circuits (D-01) never call the LLM — the worker stores
        # bucket=skip with why="duplicate of <id>" and no score. A fresh
        # standalone rescore has no notion of "duplicate of X" and will
        # naturally disagree; comparing them measures dedup logic, not
        # scoring parity, so these rows are excluded from the parity count.
        if (row["why"] or "").startswith("duplicate of"):
            dedup_skipped += 1
            print(f"{item_id[:8]:<10} {title[:40]:<42} {stored_bucket or '':<10} {'—':<10} DEDUP (excluded)")
            continue

        compared += 1
        rescored = score_item(
            {
                "title": title,
                "source": row["source"] or "",
                "summary": row["summary"] or "",
            }
        )
        rescore_bucket = rescored.get("bucket")
        match = stored_bucket == rescore_bucket
        if match:
            matches += 1

        print(
            f"{item_id[:8]:<10} {title[:40]:<42} {stored_bucket or '':<10} "
            f"{rescore_bucket or '':<10} {'OK' if match else 'MISMATCH'}"
        )

    total = len(rows)
    print("-" * len(header))
    print(f"Total rows: {total}  Dedup (excluded): {dedup_skipped}  Compared: {compared}  Matching buckets: {matches}")
    if matches >= PARITY_BAR:
        print(f"Parity verdict: MET ({matches} >= {PARITY_BAR} matching buckets).")
    else:
        print(
            f"Parity verdict: NOT MET ({matches} < {PARITY_BAR} matching buckets "
            "required) — do NOT cut over Fever (R6 prohibition)."
        )


if __name__ == "__main__":
    main()
