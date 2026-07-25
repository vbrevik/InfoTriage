#!/usr/bin/env python3
"""purge_noise_entities.py — remove structurally-noisy entities from the
canonical entity graph (Phase 8 UAT Test 3 gap-fix, 2026-07-25).

apps/triage/entities.py's is_noise_entity() denylist/domain filter only guards
NEW entity resolution going forward (see resolve_entities()). Entities created
before the filter landed — CI/platform chrome ("GitHub", "Black"), the
operator's own name, and bare ad-tech/newsletter sender domains
("adnuntius.com", "cw.no") — remain in Postgres and keep dominating
Entity Graph.md until re-triaged or purged. This is a one-off cleanup for that
existing backlog; it reuses is_noise_entity() so the purge stays in lockstep
with the runtime filter.

Usage:
    python scripts/purge_noise_entities.py --dsn "$INFOTRIAGE_PG_DSN" [--dry-run]
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "libs" / "store" / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from store import PostgresStore  # noqa: E402

from apps.triage.entities import is_noise_entity  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", default=os.environ.get("INFOTRIAGE_PG_DSN"))
    parser.add_argument(
        "--dry-run", action="store_true", help="List matches without deleting"
    )
    args = parser.parse_args()
    if not args.dsn:
        raise SystemExit("--dsn or INFOTRIAGE_PG_DSN required")

    with PostgresStore(dsn=args.dsn, blob_root=Path("/tmp/unused-blobs")) as store:
        entities = store.get_all_entities()
        noisy = [e for e in entities if is_noise_entity(e["name"])]

        print(f"{len(noisy)} / {len(entities)} entities match the noise filter:")
        for e in noisy:
            print(f"  - {e['name']!r} ({e['type']}, {e['link_count']} links)")

        if not noisy:
            print("Nothing to delete.")
            return
        if args.dry_run:
            print("(dry run — nothing deleted)")
            return

        ids = [int(e["id"]) for e in noisy]
        assert store._conn is not None
        store._conn.execute(
            "DELETE FROM infotriage.entity_links WHERE entity_id = ANY(%s)", (ids,)
        )
        store._conn.execute(
            "DELETE FROM infotriage.entities WHERE id = ANY(%s)", (ids,)
        )
        store._conn.commit()
        print(f"Deleted {len(ids)} noise entities + their links.")


if __name__ == "__main__":
    main()
