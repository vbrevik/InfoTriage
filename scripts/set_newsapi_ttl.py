#!/usr/bin/env python3
"""Set a conservative per-feed TTL for NewsAPI.org feeds in FreshRSS.

FreshRSS stores feed settings (including ttl) per-user in a SQLite database at
data/freshrss/users/<user>/db.sqlite. This script finds any feed whose URL
contains ``bridge=NewsAPI`` and sets its TTL so the 6 feeds stay well under the
NewsAPI.org free-tier limit of 100 requests/day.

Usage:
    python3 scripts/set_newsapi_ttl.py [ttl_seconds]

Defaults:
    ttl_seconds = 10800  (3 hours)

Recommended values:
    7200  = 2 hours  (72 requests/day for 6 feeds)
    10800 = 3 hours  (48 requests/day for 6 feeds)
    14400 = 4 hours  (36 requests/day for 6 feeds)
"""

import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TTL = 10800  # 3 hours
NEWSAPI_PATTERN = "%bridge=NewsAPI%"


def find_user_dbs(root: Path) -> list[Path]:
    """Return all FreshRSS user SQLite databases under data/freshrss/users."""
    users_dir = root / "data" / "freshrss" / "users"
    if not users_dir.exists():
        raise FileNotFoundError(f"FreshRSS users directory not found: {users_dir}")

    dbs = []
    for user_dir in users_dir.iterdir():
        db = user_dir / "db.sqlite"
        if db.is_file():
            dbs.append(db)
    return dbs


def set_newsapi_ttl(db_path: Path, ttl: int) -> list[tuple[int, str, int]]:
    """Update ttl for NewsAPI feeds in a FreshRSS SQLite database.

    Returns the list of affected (feed_id, feed_url, new_ttl) tuples.
    """
    conn = sqlite3.connect(db_path)
    try:
        # FreshRSS table/column names are stable across 1.x releases.
        cur = conn.execute(
            "SELECT id, url, ttl FROM feed WHERE url LIKE ?",
            (NEWSAPI_PATTERN,),
        )
        feeds = cur.fetchall()

        updated = []
        for feed_id, url, old_ttl in feeds:
            conn.execute(
                "UPDATE feed SET ttl = ? WHERE id = ?",
                (ttl, feed_id),
            )
            updated.append((feed_id, url, old_ttl))

        if updated:
            conn.commit()
        return updated
    finally:
        conn.close()


def main() -> int:
    try:
        ttl = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_TTL
    except ValueError:
        print("Usage: python3 scripts/set_newsapi_ttl.py [ttl_seconds]", file=sys.stderr)
        return 2

    if ttl <= 0:
        print("TTL must be a positive integer (seconds).", file=sys.stderr)
        return 2

    dbs = find_user_dbs(ROOT)
    if not dbs:
        print("No FreshRSS user databases found. Is FreshRSS set up?", file=sys.stderr)
        return 1

    total = 0
    for db_path in dbs:
        updated = set_newsapi_ttl(db_path, ttl)
        if updated:
            print(f"\nUpdated {len(updated)} NewsAPI feed(s) in {db_path} (ttl={ttl}s):")
            for feed_id, url, old_ttl in updated:
                print(f"  - id={feed_id}, old_ttl={old_ttl}s, url={url}")
            total += len(updated)
        else:
            print(f"\nNo NewsAPI feeds found in {db_path}.")

    if total:
        print(f"\nTotal NewsAPI feeds updated: {total}")
        print("Restart FreshRSS or wait for the next cron cycle for the change to take effect.")
    else:
        print("\nNo NewsAPI feeds were updated.")
        print("Hint: import apps/opml/feeds.opml into FreshRSS first, then re-run this script.")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
