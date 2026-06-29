#!/usr/bin/env python3
"""_util.py — local copy of the Atom-safe XML escape helper for ingest-youtube.

The ingest-youtube container does not COPY apps/ingest/ onto its path, so this
adapter bundles its own copy of escape() (pinned to the same contract as
apps/ingest/_util.py which is tested by tests/test_bridge_escape.py).

Only escape() is copied here — the containers do not share any other logic from
apps/ingest/.  A future consolidation would move this to libs/contracts.

Threat model: T-04-06 — all XML-interpolated fields (title, summary) in write_atom
pass through this helper before being written to the Atom file (reuse of the
tested contract).
"""
from html import escape as _html_escape


def escape(s):
    """Atom-safe XML escape (``&``, ``<``, ``>``, ``"``, ``'``); None-safe.

    Byte-identical to ``html.escape(s, quote=True)`` for any ``str``;
    treats ``None`` as empty string (bridges frequently pass raw dict
    values, some of which are ``None``). Other non-str types raise
    ``TypeError`` directly from this helper — fail loud on bad input
    rather than relying on what stdlib ``html.escape`` happens to do
    internally. Stable contract across Python versions.
    """
    if s is None:
        return ""
    if not isinstance(s, str):
        raise TypeError(
            f"escape expected str or None, got {type(s).__name__}"
        )
    return _html_escape(s, quote=True)
