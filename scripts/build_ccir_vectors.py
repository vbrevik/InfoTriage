#!/usr/bin/env python3
"""build_ccir_vectors.py — build/maintain CCIR vectors from ccir.md.

Usage:
    python scripts/build_ccir_vectors.py --dsn "$INFOTRIAGE_PG_DSN"

Reads the canonical ccir.md from the project root, extracts each CCIR section
(PIR-1..6, FFIR-1..3, SIR-1..3), embeds the section text with the mE5-large
`query:` prefix, and upserts the vectors into infotriage.ccir_vectors.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from pathlib import Path
from typing import cast

sys.path.insert(0, str(Path(__file__).parent.parent / "libs" / "store" / "src"))

from store import PostgresStore  # noqa: E402


CCIR_PATH = Path(__file__).parent.parent / "ccir.md"
EMBED_MODEL = "intfloat/multilingual-e5-large"


def _get_embedding(text: str) -> list[float]:
    base = os.environ.get("LLM_BASE_URL", "http://127.0.0.1:8000/v1")
    key = os.environ.get("LLM_API_KEY", "omlx")
    body = json.dumps({"model": EMBED_MODEL, "input": text}).encode()
    req = urllib.request.Request(
        base.rstrip("/") + "/embeddings",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return cast(list[float], json.load(r)["data"][0]["embedding"])


def _extract_sections(path: Path) -> dict[str, str]:
    """Parse individual CCIR bullet items from ccir.md.

    ccir.md uses `## PIR`/`## FFIR`/`## SIR` section headings, with each CCIR
    as a bullet line starting with `- **PIR-N Title** — description...`. The
    description may continue on subsequent indented lines until the next bullet.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    sections: dict[str, str] = {}
    current: tuple[str, str] | None = None
    body_lines: list[str] = []

    bullet_re = re.compile(r"^- \*\*(PIR|FFIR|SIR)-(\d+)\s+(.+?)\*\*\s*—\s*(.*)$")

    def _flush() -> None:
        nonlocal current, body_lines
        if current is not None:
            ccir_id, title = current
            sections[ccir_id] = (
                f"{ccir_id} {title}\n" + "\n".join(body_lines).strip()
            )
            current = None
            body_lines = []

    for line in lines:
        match = bullet_re.match(line)
        if match:
            _flush()
            kind, num, title, first_body = match.groups()
            current = (f"{kind}-{num}", title.strip())
            body_lines = [first_body.strip()]
        elif current is not None:
            stripped = line.strip()
            if stripped.startswith("## "):
                _flush()
            elif stripped:
                body_lines.append(stripped)

    _flush()
    return sections


def _truncate(text: str, max_chars: int = 2048) -> str:
    return text if len(text) <= max_chars else text[:max_chars]


def main() -> None:
    parser = argparse.ArgumentParser(description="Build CCIR vectors from ccir.md")
    parser.add_argument("--dsn", required=True, help="Postgres DSN")
    args = parser.parse_args()

    sections = _extract_sections(CCIR_PATH)
    if not sections:
        print("No CCIR sections found in", CCIR_PATH, file=sys.stderr)
        sys.exit(1)

    with PostgresStore(dsn=args.dsn, blob_root=Path("/tmp/blobs")) as store:
        store.init_schema()
        for ccir_id, section_text in sorted(sections.items()):
            text = _truncate(section_text)
            vec = _get_embedding(f"query: {text}")
            store.put_ccir_vector(ccir_id, vec)
            print(f"Upserted {ccir_id}")

    print(f"Built {len(sections)} CCIR vectors")


if __name__ == "__main__":
    main()
