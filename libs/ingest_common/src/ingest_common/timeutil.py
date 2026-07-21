#!/usr/bin/env python3
"""timeutil.py — shared date/time utilities for InfoTriage ingest adapters."""
import datetime
import re
from typing import Optional


def parse_since(since: Optional[str]) -> Optional[datetime.datetime]:
    """Parse a relative window like '24h' or '7d' into a UTC datetime.

    Returns None if since is None, empty, or whitespace-only.
    """
    if not since or not since.strip():
        return None
    since = since.strip()
    match = re.fullmatch(r"(\d+)([hd])", since, re.IGNORECASE)
    if not match:
        raise ValueError(f"Invalid --since value: {since!r}; expected e.g. 24h or 7d")
    value, unit = int(match.group(1)), match.group(2).lower()
    delta = (
        datetime.timedelta(hours=value)
        if unit == "h"
        else datetime.timedelta(days=value)
    )
    return datetime.datetime.now(tz=datetime.timezone.utc) - delta
