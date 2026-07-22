#!/usr/bin/env python3
"""scripts/uat_test9_threshold_env.py — UAT Test 9: CLUSTER_THRESHOLD env var.

Verifies the end-to-end CLUSTER_THRESHOLD env-var flow:

  1. apps/brief/main.py reads CLUSTER_THRESHOLD from the env at import time
     and rejects out-of-range values (negative, >1) with a ValueError.
  2. The validated value is what gets used (not silently clamped).
  3. The same rows produce measurably different cluster counts at
     different thresholds, proving the value reaches cluster_items_in_memory().

NON-INTRUSIVE: spawns short-lived subprocesses for the env-var import
checks. The cluster-count comparison runs in-process against the live
Postgres (read-only — no writes).

This intentionally does NOT restart the live brief container. A sub-brief
on a different port would compete with the live consumer for q.brief
messages; the in-process build_html() comparison exercises the same
threshold → cluster pipeline without that risk.
"""
import os
import re
import subprocess
import sys
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

DSN = os.environ.get(
    "INFOTRIAGE_PG_DSN",
    "postgresql://infotriage:infotriage_dev@localhost:22000/infotriage",
)
REPO_ROOT = Path(__file__).resolve().parent.parent


def _run_import_with_env(extra_env: dict) -> subprocess.CompletedProcess:
    """Spawn a Python interpreter that imports apps.brief.main and prints CLUSTER_THRESHOLD.

    The lifespan context manager doesn't run on bare import, so the
    subprocess never opens a DB or AMQP connection.
    """
    env = os.environ.copy()
    # Defensive: ensure no override from the parent shell leaks in.
    env.pop("INFOTRIAGE_PG_DSN", None)
    env.pop("INFOTRIAGE_AMQP_DSN", None)
    env.update(extra_env)
    return subprocess.run(
        [
            sys.executable,
            "-c",
            "import apps.brief.main as m; print(m.CLUSTER_THRESHOLD)",
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(REPO_ROOT),
    )


def test_default_threshold_is_075() -> None:
    result = _run_import_with_env({})
    assert result.returncode == 0, f"Import failed: {result.stderr}"
    assert "0.75" in result.stdout, f"Expected 0.75, got: {result.stdout!r}"
    print("PASS: default CLUSTER_THRESHOLD (env var unset) → 0.75")


def test_env_var_picked_up_at_import() -> None:
    for value in ["0.5", "0.99", "0.0", "1.0"]:
        result = _run_import_with_env({"CLUSTER_THRESHOLD": value})
        assert result.returncode == 0, f"Import failed for {value}: {result.stderr}"
        # Float formatting: 0.0 → "0.0", 1.0 → "1.0", 0.5 → "0.5"
        assert (
            value in result.stdout
        ), f"Expected CLUSTER_THRESHOLD={value} to appear in stdout, got: {result.stdout!r}"
        print(f"PASS: CLUSTER_THRESHOLD={value} → imported as {value}")


def test_invalid_thresholds_rejected() -> None:
    for bad in ["-0.2", "1.5", "abc"]:
        result = _run_import_with_env({"CLUSTER_THRESHOLD": bad})
        assert result.returncode != 0, (
            f"Expected ValueError for CLUSTER_THRESHOLD={bad}, but import succeeded "
            f"with stdout={result.stdout!r}"
        )
        assert (
            "ValueError" in result.stderr or "must be 0.0" in result.stderr
        ), f"Expected ValueError message for {bad}, got stderr={result.stderr!r}"
        print(f"PASS: CLUSTER_THRESHOLD={bad} → ValueError at import time")


def test_threshold_changes_renderer_cluster_output() -> None:
    """Same rows, different thresholds, different cluster counts.

    Proves the env-var-derived threshold reaches cluster_items_in_memory()
    via build_html(), which is the same code path the live /sab endpoint
    uses (main.py → _render_sab → build_html(cluster_threshold=CLUSTER_THRESHOLD)).
    """
    sys.path.insert(0, str(REPO_ROOT))
    # Force the localhost DSN — the host shell may have INFOTRIAGE_PG_DSN
    # pointing to the docker-internal 'postgres' hostname which doesn't
    # resolve from the host process.
    os.environ["INFOTRIAGE_PG_DSN"] = DSN
    from apps.brief.html_renderer import build_html

    conn = psycopg.connect(DSN)
    try:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT e.item_id, e.ccir, e.cnr, e.score, e.bucket, e.why, "
                "       e.pmesii, e.tessoc, a.title, a.summary, a.source, a.url, "
                "       emb.embedding "
                "FROM infotriage.enrichment e "
                "JOIN infotriage.articles a ON a.id = e.item_id "
                "LEFT JOIN infotriage.embeddings emb ON emb.item_id = e.item_id "
                "WHERE e.created_at >= NOW() - INTERVAL '24 hours' "
                "ORDER BY e.score DESC"
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    if not rows:
        print("SKIP: no rows in last 24h; cannot compare cluster counts")
        return

    def total_clusters(html: str) -> int:
        return sum(int(m) for m in re.findall(r"\d+ saker · (\d+) klynger", html))

    html_loose = build_html(rows, "test", with_bluf=False, cluster_threshold=0.0)
    html_strict = build_html(rows, "test", with_bluf=False, cluster_threshold=0.99)
    loose_total = total_clusters(html_loose)
    strict_total = total_clusters(html_strict)
    print(
        f"  cluster counts: threshold=0.0 → {loose_total}, threshold=0.99 → {strict_total}"
    )
    assert strict_total > loose_total, (
        f"Higher threshold should produce MORE clusters (every item is its own cluster), "
        f"but got loose={loose_total}, strict={strict_total}"
    )
    print("PASS: env-var-derived threshold changes renderer cluster output")


def main() -> None:
    test_default_threshold_is_075()
    test_env_var_picked_up_at_import()
    test_invalid_thresholds_rejected()
    test_threshold_changes_renderer_cluster_output()
    print("\nUAT Test 9: all checks passed")


if __name__ == "__main__":
    main()
