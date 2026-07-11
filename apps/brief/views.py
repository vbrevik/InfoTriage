#!/usr/bin/env python3
"""views.py — COP / CIP / CRP view filters for the Brief App (ADR-012).

View filters are applied to enrichment rows AFTER fetching from the database
and BEFORE rendering. They do not change the LLM scorer; they are output lenses.

Enrichment row dict keys expected:
  item_id, ccir, cnr, score, bucket, why, pmesii, tessoc, title, summary, source, url
"""
from typing import Callable


# CCIR codes included in the Common Operational Picture (friendly / operational).
_COP_CCIR = {"FFIR-1", "FFIR-2", "FFIR-3", "PIR-3", "SIR-2", "SIR-3"}
_COP_PMESII = {"Political", "Military", "Infrastructure"}

# PMESII domains included in the Common Intelligence Picture (adversary / threat).
_CIP_PMESII = {"Information", "Military", "Economic"}


def _normalize(value: str | None) -> str:
    """Return a stripped, title-cased string, or empty string for None/empty.

    Title-casing lets us compare the DB value against the title-cased sets
    (_COP_PMESII, _CIP_PMESII) regardless of whether the producer wrote
    "Military" (triage scorer) or "military" (seed_sample_data.py).
    """
    if value is None:
        return ""
    return value.strip().title()


def _matches_cop(row: dict) -> bool:
    ccir = _normalize(row.get("ccir")).upper()
    pmesii = _normalize(row.get("pmesii"))
    return ccir in _COP_CCIR and pmesii in _COP_PMESII


def _matches_cip(row: dict) -> bool:
    # ccir needs .upper() after _normalize().title(): .title() corrupts
    # "PIR-1" → "Pir-1" (capitalizes first letter, lowercases the rest).
    # Without .upper() the startswith("PIR-") check fails on every row.
    ccir = _normalize(row.get("ccir")).upper()
    pmesii = _normalize(row.get("pmesii"))
    tessoc = _normalize(row.get("tessoc"))
    # tessoc.lower() in {"" "none"} — _normalize title-cases, so a DB value
    # of "none" or "None" both become "None" after normalization; the .lower()
    # is what makes the sentinel check case-insensitive.
    return (
        tessoc.lower() not in ("", "none")
        and ccir.startswith("PIR-")
        and pmesii in _CIP_PMESII
    )


def _matches_crp(row: dict, params: dict) -> bool:
    """Apply user-configurable CRP filters.

    Supported params (all optional, AND-ed):
      - ccir: comma-separated list of CCIR codes (case-insensitive)
      - pmesii: comma-separated list of PMESII domains (case-insensitive)
      - tessoc: comma-separated list of TESSOC categories (case-insensitive)
      - min_score: minimum score (inclusive)
    """
    if not params:
        return True

    ccir = _normalize(row.get("ccir")).upper()
    pmesii = _normalize(row.get("pmesii"))
    tessoc = _normalize(row.get("tessoc"))
    score = row.get("score", 0) or 0

    if "ccir" in params:
        wanted = {c.strip().upper() for c in params["ccir"].split(",")}
        if ccir not in wanted:
            return False

    if "pmesii" in params:
        wanted = {p.strip().title() for p in params["pmesii"].split(",")}
        if pmesii not in wanted:
            return False

    if "tessoc" in params:
        wanted = {t.strip().title() for t in params["tessoc"].split(",")}
        if tessoc not in wanted:
            return False

    if "min_score" in params:
        try:
            if score < int(params["min_score"]):
                return False
        except (TypeError, ValueError):
            pass

    return True


def filter_rows(rows: list[dict], view: str | None, crp_params: dict | None = None) -> list[dict]:
    """Filter enrichment rows according to the requested picture view.

    Args:
        rows: enrichment row dicts from the database
        view: one of "cop", "cip", "crp", or None (no filtering)
        crp_params: optional dict of CRP filter parameters (ccir, pmesii, tessoc, min_score)

    Returns:
        Filtered list of rows.
    """
    if view is None:
        return rows

    view = view.lower()
    if view == "cop":
        return [r for r in rows if _matches_cop(r)]
    if view == "cip":
        return [r for r in rows if _matches_cip(r)]
    if view == "crp":
        params = crp_params or {}
        return [r for r in rows if _matches_crp(r, params)]

    raise ValueError(f"unknown view: {view!r} (expected cop, cip, crp)")
