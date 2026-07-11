#!/usr/bin/env python3
"""scripts/uat_test5_email.py — UAT Test 5: email items in vault by default.

Verifies two things:

  1. The default vault writer includes email-sourced items
     (source starts with "imap://") when VAULT_INCLUDE_EMAIL is unset
     or set to "1" (the compose default).

  2. Setting VAULT_INCLUDE_EMAIL=0 in the environment filters imap://
     items out of the vault.

Non-intrusive: no DB writes. The "live" check is against the same
Postgres the running consumer uses. The negative check uses a fixture
row in a tempdir so it never touches the real vault.

Usage:
  INFOTRIAGE_PG_DSN='postgresql://infotriage:infotriage_dev@localhost:22000/infotriage' \
      python3 scripts/uat_test5_email.py
"""
import os
import sys
import tempfile
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

DSN = os.environ.get(
    "INFOTRIAGE_PG_DSN",
    "postgresql://infotriage:infotriage_dev@localhost:22000/infotriage",
)


def _count_imap_rows() -> int:
    conn = psycopg.connect(DSN)
    try:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT COUNT(*) AS n FROM infotriage.articles WHERE source LIKE 'imap://%'"
            )
            return cur.fetchone()["n"]
    finally:
        conn.close()


def _pick_enriched_imap_row() -> dict | None:
    """Return one enriched imap:// row from the live DB, or None if none exist."""
    conn = psycopg.connect(DSN)
    try:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT e.item_id, e.ccir, e.cnr, e.score, e.bucket, e.why, "
                "       e.pmesii, e.tessoc, a.title, a.summary, a.source, a.url, a.ts "
                "FROM infotriage.enrichment e "
                "JOIN infotriage.articles a ON a.id = e.item_id "
                "WHERE a.source LIKE 'imap://%' "
                "  AND e.ccir IS NOT NULL AND e.ccir <> 'none' "
                "ORDER BY e.score DESC LIMIT 1"
            )
            return cur.fetchone()
    finally:
        conn.close()


def test_live_imap_rows_present() -> int:
    n = _count_imap_rows()
    print(f"INFO: {n} imap:// row(s) in infotriage.articles")
    return n


def test_vault_includes_live_imap_row() -> None:
    """If imap:// rows exist in DB, write_vault_digest must include them."""
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    # Default (no override) honors VAULT_INCLUDE_EMAIL=1 from compose.
    os.environ.pop("VAULT_INCLUDE_EMAIL", None)

    from apps.brief.vault_writer import write_vault_digest

    row = _pick_enriched_imap_row()
    if row is None:
        print("SKIP: no enriched imap:// rows in DB; cannot verify live inclusion")
        return

    with tempfile.TemporaryDirectory() as tmp:
        tmp_vault = Path(tmp)
        write_vault_digest([row], tmp_vault, write_items=True, sab_filename="obsidian-sab.md")
        item_filename = f"{row['item_id']}.md"
        assert (tmp_vault / item_filename).exists(), (
            f"imap:// item not written to vault: {item_filename} missing in {tmp_vault}"
        )
        assert (tmp_vault / "obsidian-sab.md").exists(), "obsidian-sab.md missing"
        # And the SAB projection body must reference the imap:// row's title.
        sab_body = (tmp_vault / "obsidian-sab.md").read_text(encoding="utf-8")
        assert row["title"] in sab_body, (
            f"imap:// item title not in obsidian-sab.md body: {row['title']!r}"
        )
    print(f"PASS: imap:// item included in vault by default ({item_filename})")


def test_vaul_include_email_zero_filters_out_imap() -> None:
    """With VAULT_INCLUDE_EMAIL=0, imap:// items must be excluded."""
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from apps.brief.vault_writer import write_vault_digest

    imap_row = {
        "item_id": "uat5-fixture-imap",
        "ccir": "PIR-1",
        "cnr": "II",
        "score": 9,
        "bucket": "read",
        "why": "Email-source filter test",
        "pmesii": "Military",
        "tessoc": "Espionage",
        "title": "Email-only fixture row (UAT-5)",
        "summary": "Fixture summary",
        "source": "imap://inbox/uat5-fixture",
        "url": "imap://inbox/uat5-fixture",
        "ts": "2026-07-11T12:00:00+00:00",
    }
    os.environ["VAULT_INCLUDE_EMAIL"] = "0"
    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_vault = Path(tmp)
            write_vault_digest([imap_row], tmp_vault, write_items=True, sab_filename="obsidian-sab.md")
            item_filename = f"{imap_row['item_id']}.md"
            assert not (tmp_vault / item_filename).exists(), (
                f"imap:// item leaked into vault despite VAULT_INCLUDE_EMAIL=0: {item_filename}"
            )
    finally:
        os.environ.pop("VAULT_INCLUDE_EMAIL", None)
    print("PASS: VAULT_INCLUDE_EMAIL=0 correctly filters imap:// rows")


def main() -> None:
    n = test_live_imap_rows_present()
    if n > 0:
        test_vault_includes_live_imap_row()
    else:
        print("NOTE: no imap:// rows in DB; live inclusion check skipped "
              "(the negative filter check below still proves the gate works)")
    test_vaul_include_email_zero_filters_out_imap()
    print("\nUAT Test 5: all checks passed")


if __name__ == "__main__":
    main()
