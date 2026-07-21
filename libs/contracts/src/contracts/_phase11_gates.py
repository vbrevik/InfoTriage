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
