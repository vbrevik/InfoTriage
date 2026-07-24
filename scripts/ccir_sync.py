#!/usr/bin/env python3
"""Regenerate the CCIR-owned regions of generated files from the registry.

Single source of truth = libs/contracts/src/contracts/ccir.py. This script
rewrites the `<!-- ccir:begin ... -->` … `<!-- ccir:end -->` region of
apps/opml/feeds.opml with the registry's CCIR feed groups.

ccir.md is NOT generated (it is hand-authored analytical prose); its consistency
with the registry is enforced by tests/test_ccir_sync.py instead.

Usage:  make ccir-sync   (or: python scripts/ccir_sync.py)
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "libs" / "contracts" / "src"))

from contracts.ccir import render_feeds_opml_groups  # noqa: E402

BEGIN = "<!-- ccir:begin"
END = "<!-- ccir:end -->"


def _rewrite_region(text: str, body: str) -> str:
    start = text.index(BEGIN)
    end = text.index(END, start) + len(END)
    header = text[start : text.index("-->", start) + len("-->")]
    return text[:start] + header + "\n" + body + "\n    " + END + text[end:]


def sync_feeds_opml() -> bool:
    path = ROOT / "apps" / "opml" / "feeds.opml"
    text = path.read_text(encoding="utf-8")
    new = _rewrite_region(text, render_feeds_opml_groups())
    if new != text:
        path.write_text(new, encoding="utf-8")
        return True
    return False


def main() -> None:
    changed = sync_feeds_opml()
    print(f"ccir-sync: feeds.opml {'updated' if changed else 'already in sync'}")


if __name__ == "__main__":
    main()
