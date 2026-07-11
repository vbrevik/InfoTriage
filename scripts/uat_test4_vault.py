#!/usr/bin/env python3
"""scripts/uat_test4_vault.py — UAT Test 4: vault writer.

Verifies the live brief container is writing Obsidian .md files to its
INFOTRIAGE_VAULT_PATH (mounted from the host's OBSIDIAN_VAULT_PATH):

  1. The vault directory exists and is a directory.
  2. The directory contains at least one .md file (per-item or SAB).
  3. The SAB projection file (obsidian-sab.md) is present.
  4. Per-item .md files have codec-parseable front-matter (per the
     contracts.to_frontmatter / from_frontmatter contract).

Non-intrusive: passive read of the live vault. Does not touch the
running brief consumer or database.

Usage:
  INFOTRIAGE_HOST_VAULT=/path/to/vault/brief-outbox python3 scripts/uat_test4_vault.py
  # or rely on DEFAULT_HOST_VAULT below.
"""
import os
import sys
from pathlib import Path

# contracts is a top-level package (sys.path adjusted below). The codec
# roundtrip is the existing contract used by tests/test_vault_writer.py.
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from contracts import from_frontmatter  # noqa: E402

# Per docker-compose.yml (2026-07-11 live inspection):
#   ${OBSIDIAN_VAULT_PATH:-./data/obsidian}/brief-outbox:/vault/brief-outbox:rw
# On this host OBSIDIAN_VAULT_PATH=/Users/vidarbrevik/Vault → brief-outbox
DEFAULT_HOST_VAULT = "/Users/vidarbrevik/Vault/brief-outbox"


def _vault_dir() -> Path:
    return Path(os.environ.get("INFOTRIAGE_HOST_VAULT", DEFAULT_HOST_VAULT))


def test_vault_dir_exists() -> None:
    vault = _vault_dir()
    assert vault.exists(), f"Vault path missing on host: {vault}"
    assert vault.is_dir(), f"Vault path is not a directory: {vault}"
    print(f"PASS: vault dir exists: {vault}")


def test_vault_has_md_files() -> None:
    vault = _vault_dir()
    md_files = sorted(vault.glob("*.md"))
    assert md_files, f"No .md files in {vault}"
    print(f"PASS: {len(md_files)} .md file(s) in vault")


def test_sab_projection_present() -> None:
    vault = _vault_dir()
    assert (vault / "obsidian-sab.md").exists(), (
        f"obsidian-sab.md missing in {vault}"
    )
    print("PASS: obsidian-sab.md present")


def test_per_item_files_have_parseable_frontmatter() -> None:
    """Per-item .md files (not the SAB projection) must have parseable front-matter."""
    vault = _vault_dir()
    # Per-item files are sha256(item_id) — 64 hex chars, no hyphens.
    # The SAB projection files (obsidian-sab*.md) lack front-matter.
    per_item = [f for f in vault.glob("*.md") if not f.name.startswith("obsidian-sab")]
    if not per_item:
        print("SKIP: no per-item .md files; cannot verify front-matter codec")
        return
    sample = per_item[:5]
    for f in sample:
        text = f.read_text(encoding="utf-8")
        fm = from_frontmatter(text)
        assert isinstance(fm, dict), f"{f.name}: frontmatter did not parse to a dict"
        # Must have at least one identity-bearing key from the write_item_obsidian schema.
        identity_keys = {"title", "url", "item_id", "ccir", "score"}
        assert identity_keys & set(fm.keys()), (
            f"{f.name}: frontmatter missing expected keys; got {list(fm.keys())}"
        )
    print(f"PASS: {len(sample)} per-item file(s) have codec-parseable front-matter")


def main() -> None:
    test_vault_dir_exists()
    test_vault_has_md_files()
    test_sab_projection_present()
    test_per_item_files_have_parseable_frontmatter()
    print("\nUAT Test 4: all checks passed")


if __name__ == "__main__":
    main()
