#!/usr/bin/env python3
"""apps/ingest/_util.py — shared helpers for the bridge entry points.

Routed:
- apps/ingest/imap_to_atom.py    (4 call sites, inside write_atom)
- apps/ingest/yt_to_atom.py      (2 call sites: title + summary)

Why a helper instead of two inline ``html.escape(...)`` calls?
  1. Defense-in-depth — one place owns the Atom-XML escape contract. A future
     policy change (e.g. ``quote=False``, custom ``safe=``) flips for all
     three bridges simultaneously.
  2. Testability — pinned by tests/test_bridge_escape.py at CI time, so
     drift is caught before a malformed feed breaks FreshRSS.
  3. None-safety — bridges iterate dict values / RSS-bridge output where a
     missing field is ``None``. stdlib ``html.escape(None)`` raises. We
     coerce ``None`` to ``""`` so callers can pass raw mappings through.
"""
from html import escape as _html_escape


def escape(s):
    """Atom-safe XML escape (``&``, ``<``, ``>``, ``"``, ``'``); None-safe.

    Byte-identical to ``html.escape(s, quote=True)`` for any ``str``;
    treats ``None`` as empty string (bridges frequently pass raw dict
    values, some of which are ``None``). Other non-str types raise
    ``TypeError`` directly from this helper — fail loud on bad input
    rather than relying on what stdlib ``html.escape`` happens to do
    internally (Python 3.13 raises ``AttributeError`` for ``int`` etc.,
    earlier versions differ). Stable contract across Python versions.
    """
    if s is None:
        return ""
    if not isinstance(s, str):
        raise TypeError(
            f"escape expected str or None, got {type(s).__name__}")
    return _html_escape(s, quote=True)
