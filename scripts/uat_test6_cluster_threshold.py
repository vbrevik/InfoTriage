#!/usr/bin/env python3
"""scripts/uat_test6_cluster_threshold.py — UAT Test 6.

Verifies:
  1. Default CLUSTER_THRESHOLD is 0.75 when env var is missing.
  2. Out-of-range values (negative or >1) raise ValueError at import time.
  3. main.py passes the validated threshold through to the renderer and consumer.
  4. A different threshold produces measurably different clustering output.
"""
import os
import re
import subprocess
import sys

import psycopg
from psycopg.rows import dict_row

DSN = os.environ.get(
    "INFOTRIAGE_PG_DSN",
    "postgresql://infotriage:infotriage_dev@localhost:22000/infotriage",
)


def _run_import_with_env(extra_env: dict) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.update(extra_env)
    return subprocess.run(
        [
            sys.executable,
            "-c",
            "import apps.brief.main as m; print('CLUSTER_THRESHOLD=', m.CLUSTER_THRESHOLD, sep='')",
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=os.path.dirname(os.path.dirname(__file__)),
    )


def test_default_threshold():
    env = {k: v for k, v in os.environ.items() if k != "CLUSTER_THRESHOLD"}
    env.pop("CLUSTER_THRESHOLD", None)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import apps.brief.main as m; print('CLUSTER_THRESHOLD=', m.CLUSTER_THRESHOLD, sep='')",
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=os.path.dirname(os.path.dirname(__file__)),
    )
    assert result.returncode == 0, f"Import failed: {result.stderr}"
    assert "CLUSTER_THRESHOLD=0.75" in result.stdout, result.stdout
    print("PASS: default CLUSTER_THRESHOLD is 0.75")


def test_invalid_thresholds():
    for bad in ["-0.2", "1.5"]:
        result = _run_import_with_env({"CLUSTER_THRESHOLD": bad})
        assert (
            result.returncode != 0
        ), f"Expected ValueError for {bad}, but import succeeded"
        assert (
            "ValueError" in result.stderr or "must be 0.0" in result.stderr
        ), result.stderr
        print(f"PASS: CLUSTER_THRESHOLD={bad} raises ValueError")


def test_threshold_pass_through():
    """Check that main.py wires CLUSTER_THRESHOLD into build_html and consumer."""
    main_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "apps", "brief", "main.py"
    )
    with open(main_path, encoding="utf-8") as f:
        source = f.read()

    occurrences = source.count("cluster_threshold=CLUSTER_THRESHOLD")
    assert occurrences >= 2, (
        f"main.py should pass cluster_threshold to both renderer and consumer, "
        f"found only {occurrences} occurrence(s)"
    )
    print("PASS: main.py passes CLUSTER_THRESHOLD to renderer and consumer")


def test_end_to_end_threshold_effect():
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from apps.brief.html_renderer import build_html

    conn = psycopg.connect(DSN)
    try:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT e.item_id, e.ccir, e.cnr, e.score, e.bucket, e.why,
                       e.pmesii, e.tessoc,
                       a.title, a.summary, a.source, a.url,
                       emb.embedding
                FROM infotriage.enrichment e
                JOIN infotriage.articles a ON a.id = e.item_id
                LEFT JOIN infotriage.embeddings emb ON emb.item_id = e.item_id
                WHERE e.created_at >= NOW() - INTERVAL '24 hours'
                ORDER BY e.score DESC
                """
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    def total_clusters(html: str) -> int:
        return sum(int(m) for m in re.findall(r"\d+ saker · (\d+) klynger", html))

    html_strict = build_html(rows, "test", with_bluf=False, cluster_threshold=0.99)
    html_loose = build_html(rows, "test", with_bluf=False, cluster_threshold=0.0)

    strict_total = total_clusters(html_strict)
    loose_total = total_clusters(html_loose)

    print(f"Total clusters: strict=0.99 -> {strict_total}, loose=0.0 -> {loose_total}")
    assert (
        loose_total < strict_total
    ), "Lower threshold should produce fewer total clusters than high threshold"
    print("PASS: different thresholds produce different clustering output")


def main():
    test_default_threshold()
    test_invalid_thresholds()
    test_threshold_pass_through()
    test_end_to_end_threshold_effect()
    print("\nUAT Test 6: all checks passed")


if __name__ == "__main__":
    main()
