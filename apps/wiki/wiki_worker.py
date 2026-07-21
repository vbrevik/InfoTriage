#!/usr/bin/env python3
"""wiki_worker.py — periodic auto-wiki worker (Phase 10 Wave 1).

Generates/updates standing Obsidian wiki pages for the most-linked canonical
entities. Can run once or on a schedule.

Usage:
    python apps/wiki/wiki_worker.py --once          # generate once and exit
    python apps/wiki/wiki_worker.py --interval 3600 # regenerate every hour
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

from contracts import setup_logging
from generator import WikiGenerator
from store import PostgresStore

setup_logging("wiki")
log = logging.getLogger(__name__)

DEFAULT_INTERVAL = 3600
DEFAULT_TOP_N = 10


def _top_entities(store, *, top_n: int = DEFAULT_TOP_N):
    """Return the top-N active canonical entities for wiki generation."""
    entities = store.get_active_entities(limit=top_n)
    return [e["name"] for e in entities if e.get("name")]


def run_once(
    store,
    vault_path: Path,
    *,
    top_n: int = DEFAULT_TOP_N,
    embed=None,
    llm=None,
) -> list[Path]:
    """Generate wiki pages for the top-N active entities.

    Returns the list of paths written.
    """
    generator = WikiGenerator(store, vault_path, embed=embed, llm=llm)
    subjects = _top_entities(store, top_n=top_n)
    written: list[Path] = []
    for subject in subjects:
        try:
            path = generator.generate_page(subject)
            log.info("wiki page written: %s", path)
            written.append(path)
        except Exception as exc:
            log.error("failed to generate wiki page for %s: %s", subject, exc)
    return written


async def run_periodic(
    store,
    vault_path: Path,
    *,
    interval: int = DEFAULT_INTERVAL,
    top_n: int = DEFAULT_TOP_N,
    embed=None,
    llm=None,
) -> None:
    """Generate wiki pages periodically forever."""
    while True:
        try:
            run_once(store, vault_path, top_n=top_n, embed=embed, llm=llm)
        except Exception as exc:
            log.error("wiki worker iteration failed: %s", exc)
        log.info("sleeping for %ds before next wiki generation", interval)
        await asyncio.sleep(interval)


def main() -> None:
    parser = argparse.ArgumentParser(description="InfoTriage auto-wiki worker")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Generate pages once and exit",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_INTERVAL,
        help=f"Seconds between generations (default {DEFAULT_INTERVAL})",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=DEFAULT_TOP_N,
        help=f"Number of top entities to generate pages for (default {DEFAULT_TOP_N})",
    )
    parser.add_argument(
        "--vault-path",
        type=Path,
        default=Path(os.environ.get("INFOTRIAGE_VAULT_PATH", "data/obsidian")),
        help="Obsidian vault root path (default INFOTRIAGE_VAULT_PATH or data/obsidian)",
    )
    parser.add_argument(
        "--dsn",
        default=os.environ.get("INFOTRIAGE_PG_DSN"),
        help="Postgres DSN (default INFOTRIAGE_PG_DSN)",
    )
    parser.add_argument(
        "--blob-root",
        type=Path,
        default=Path(os.environ.get("INFOTRIAGE_BLOB_ROOT", "/data/blobs")),
        help="Blob storage root (default INFOTRIAGE_BLOB_ROOT or /data/blobs)",
    )
    args = parser.parse_args()

    if not args.dsn:
        print("ERROR: --dsn or INFOTRIAGE_PG_DSN required", file=sys.stderr)
        sys.exit(1)

    with PostgresStore(dsn=args.dsn, blob_root=args.blob_root) as store:
        if args.once:
            written = run_once(store, args.vault_path, top_n=args.top_n)
            for path in written:
                print(path)
        else:
            asyncio.run(
                run_periodic(
                    store,
                    args.vault_path,
                    interval=args.interval,
                    top_n=args.top_n,
                )
            )


if __name__ == "__main__":
    main()
