#!/usr/bin/env python3
"""html_renderer.py — HTML SAB renderer for the Brief App (Phase 6, Wave 2).

Adapts sab_html.py's build_html() to consume enrichment rows from Postgres
instead of Fever verdict dicts. The 1064-line HTML template is imported via
sab_html.build_html(), never copied (D-12) — this module is the only place
in apps/brief that touches sab_html.

Enrichment row dict keys (infotriage.enrichment):
  item_id, ccir, cnr, score, bucket, why, pmesii, tessoc, title, summary, source

CNR vocabulary (RAW): "none" | "I" | "II" — passed through unchanged;
sab_html's CNR slide matches on cnr == "I", which RAW satisfies directly.

Pure library: no HTTP, no Docker, no file IO — main.py owns serving and writes.
"""
import os
import sys

# Import build_html from sab_html — template imported, never copied (D-12).
# Same path convention as renderer.py's digest import.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "triage"))
from sab_html import build_html as _sab_build_html  # noqa: E402


def _row_to_verdict(row: dict) -> dict:
    """Map an enrichment row to the verdict-dict shape build_html() expects.

    Enrichment rows have no url or fetch-epoch column: url renders as an
    empty href and the "Sist hentet" fetch line is omitted (t absent).
    """
    return {
        "item_id": row.get("item_id", ""),
        "ccir": row.get("ccir"),
        "cnr": row.get("cnr", "none"),
        "score": row.get("score", 0),
        "why": row.get("why", ""),
        "pmesii": row.get("pmesii"),
        "tessoc": row.get("tessoc"),
        "title": row.get("title", ""),
        "summary": row.get("summary", ""),
        "source": row.get("source", ""),
        "url": row.get("url", ""),
    }


def build_html(enrichment_rows: list[dict], period: str,
               with_bluf: bool = True, generated_at: str | None = None) -> str:
    """Render the full SAB HTML page from enrichment rows.

    Delegates to sab_html.build_html() after row mapping — same slides,
    same BLUF prompt template and citation rules (D-07), same CCIR_ORDER.
    """
    verdicts = [_row_to_verdict(r) for r in enrichment_rows]
    return _sab_build_html(verdicts, period, with_bluf=with_bluf,
                           generated_at=generated_at)
