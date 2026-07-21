#!/usr/bin/env python3
"""acled_ingest.py — stub ACLED ingestion adapter (Phase 11).

This module is intentionally minimal: it enforces the ACLED paid-license gate
(ADR-014) and provides a hook for future ACLED data fetching. No real ACLED
data is ingested when the gate is open.

Environment variables:
    ACLED_LICENSE_KEY — required, non-empty paid-license key
"""
import logging

from contracts import require_acled_license

log = logging.getLogger(__name__)


async def ingest() -> None:
    """Stub ACLED ingestion entry point.

    Raises:
        PermissionError: If ACLED_LICENSE_KEY is missing or empty.
    """
    require_acled_license()
    log.info("ACLED license verified. Ingestion stub complete.")
