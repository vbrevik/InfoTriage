#!/usr/bin/env python3
"""Regression test for PMESII/TESSOC wording change in ccir.md.

Scores a fixed set of items using the current ccir.md and the version at
HEAD, then diffs the resulting PMESII and TESSOC tags.

Usage:
    python3 scripts/regression_pmesii_tessoc.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CCIR_PATH = os.path.join(ROOT, "ccir.md")
SCORE_SCRIPT = os.path.join(ROOT, "apps", "triage", "triage_score.py")
ITEMS_PATH = os.path.join(ROOT, "scripts", "regression_test_items.json")


def run_score(ccir_path: str) -> list[dict]:
    """Score items using the given ccir.md file."""
    # If using the current ccir.md, no need to swap.
    if os.path.samefile(ccir_path, CCIR_PATH):
        result = subprocess.run(
            [sys.executable, SCORE_SCRIPT, "--file", ITEMS_PATH, "--json"],
            capture_output=True,
            text=True,
            cwd=ROOT,
            timeout=300,
        )
        if result.returncode != 0:
            raise RuntimeError(f"scoring failed: {result.stderr}")
        return json.loads(result.stdout)

    # Temporarily swap ccir.md
    backup = tempfile.mktemp(suffix=".md")
    shutil.copy2(CCIR_PATH, backup)
    try:
        shutil.copy2(ccir_path, CCIR_PATH)
        result = subprocess.run(
            [sys.executable, SCORE_SCRIPT, "--file", ITEMS_PATH, "--json"],
            capture_output=True,
            text=True,
            cwd=ROOT,
            timeout=300,
        )
        if result.returncode != 0:
            raise RuntimeError(f"scoring failed: {result.stderr}")
        return json.loads(result.stdout)
    finally:
        shutil.copy2(backup, CCIR_PATH)
        os.remove(backup)


def get_old_ccir() -> str:
    """Return path to ccir.md at HEAD."""
    result = subprocess.run(
        ["git", "show", "HEAD:ccir.md"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    if result.returncode != 0:
        raise RuntimeError(f"could not retrieve old ccir.md: {result.stderr}")
    path = tempfile.mktemp(suffix=".md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(result.stdout)
    return path


def main():
    old_path = get_old_ccir()
    try:
        print("Scoring with old ccir.md (HEAD)...")
        old_results = run_score(old_path)
        print("Scoring with new ccir.md (working tree)...")
        new_results = run_score(CCIR_PATH)
    finally:
        os.remove(old_path)

    # Build lookup by title
    old_by_title = {r["title"]: r for r in old_results}
    new_by_title = {r["title"]: r for r in new_results}

    diffs = []
    for title in old_by_title:
        old = old_by_title[title]
        new = new_by_title.get(title, {})
        old_pmesii = old.get("pmesii", "none")
        new_pmesii = new.get("pmesii", "none")
        old_tessoc = old.get("tessoc", "none")
        new_tessoc = new.get("tessoc", "none")
        if old_pmesii != new_pmesii or old_tessoc != new_tessoc:
            diffs.append(
                {
                    "title": title,
                    "old_pmesii": old_pmesii,
                    "new_pmesii": new_pmesii,
                    "old_tessoc": old_tessoc,
                    "new_tessoc": new_tessoc,
                }
            )

    print(f"\nScored {len(old_results)} items.")
    print(f"PMESII/TESSOC differences: {len(diffs)}")
    if diffs:
        print("\nDifferences:")
        for d in diffs:
            print(f"  - {d['title'][:70]}")
            print(f"      PMESII: {d['old_pmesii']} -> {d['new_pmesii']}")
            print(f"      TESSOC: {d['old_tessoc']} -> {d['new_tessoc']}")
    else:
        print("No PMESII/TESSOC differences found between old and new ccir.md.")

    # Also report overall tag distributions
    def counts(results, key):
        c = {}
        for r in results:
            c[r.get(key, "none")] = c.get(r.get(key, "none"), 0) + 1
        return c

    print("\nOld PMESII distribution:", counts(old_results, "pmesii"))
    print("New PMESII distribution:", counts(new_results, "pmesii"))
    print("Old TESSOC distribution:", counts(old_results, "tessoc"))
    print("New TESSOC distribution:", counts(new_results, "tessoc"))


if __name__ == "__main__":
    main()
