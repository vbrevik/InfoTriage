#!/usr/bin/env python3
"""_phase11_gates.py — Phase 11 ingestion gates.

Reusable validation helpers for SOCMINT/Arctic adapters. These gates are
opt-in: Phase 11 adapters (Telegram, BarentsWatch AIS, ACLED) call them
explicitly; legacy adapters remain unchanged.
"""
import os

from ._item import Item


class DisciplineRequired(ValueError):
    """Raised when a Phase 11 adapter omits the discipline tag."""


class AcledLicenseMissing(PermissionError):
    """Raised when ACLED ingestion is attempted without a valid paid license."""


def require_discipline(item: Item) -> None:
    """Ensure a Phase 11 item carries a discipline tag.

    Args:
        item: The Item to validate.

    Raises:
        DisciplineRequired: If ``item.discipline`` is None or empty.
    """
    if not item.discipline:
        raise DisciplineRequired(
            f"Phase 11 restriction: 'discipline' is required for item {item.id}"
        )


def require_acled_license() -> str:
    """Enforce the ACLED paid-license gate (ADR-014).

    Returns:
        The non-empty ACLED license key.

    Raises:
        AcledLicenseMissing: If ``ACLED_LICENSE_KEY`` is missing or empty.
    """
    key = os.environ.get("ACLED_LICENSE_KEY", "").strip()
    if not key:
        raise AcledLicenseMissing(
            "ACLED_LICENSE_KEY is missing or empty. Ingestion blocked."
        )
    return key


# --- Source-of-truth mapping: source_type -> INT collection discipline ---
# Used by Phase 11 adapter-emission tests (tests/test_phase11_gates.py) and
# consumed by libs/store/sql/010-backfill-discipline.sql for legacy NULL-row
# backfill. Keep SQL CASE + Python dict in lock-step; tests
# `test_all_source_types_mapped_to_valid_discipline` enforces conformance.
#
# Taxonomy = INT (Open Source / HUMan / SIGint / MASint / GEOint / SOCmint
# intelligence taxonomy per NATO JP 2-00 framing). NOT to be confused with
# the PMESII analytical enrichment axis (which lives in ccir.md +
# triage_score.py and drives SCORING, not metadata).
SOURCE_TYPE_TO_INT_DISCIPLINE: dict[str, str] = {
    # OSINT family (open-source / public-data)
    "rss": "OSINT",
    "obsidian": "OSINT",
    "yt": "OSINT",
    "youtube": "OSINT",
    "acled": "OSINT",  # open-source conflict-data; ACLED = CIFOR-ICIT academic OSINT
    # HUMINT family (human-mediated; e.g., email sources)
    "imap": "HUMINT",
    "gmail": "HUMINT",
    "pop3": "HUMINT",  # POP3 lane of the imap adapter (surfaced by the admission gate 2026-08-01)
    # SOCMINT (social-media intelligence; Phase 11 Telegram adapter)
    "telegram": "SOCMINT",
    # MASINT family (measurement-and-signature; Phase 11 BarentsWatch AIS)
    "barentswatch": "MASINT/AIS",
    "ais": "MASINT/AIS",  # alias for legacy ingestion rows
}


# Canonical INT discipline vocabulary. New disciplines land here BEFORE they
# appear in SOURCE_TYPE_TO_INT_DISCIPLINE — so per-ingest contract tests can
# detect drift where the mapping introduces a value the Item Pydantic regex
# does not accept (or vice versa). Mirrors the regex in _item.py exactly.
VALID_INT_DISCIPLINES: frozenset[str] = frozenset({
    "OSINT",
    "HUMINT",
    "SOCMINT",
    "MASINT",
    "GEOINT",
    "SIGINT",
    "MASINT/AIS",  # sub-discipline (AIS = Automatic Identification System)
})
