#!/usr/bin/env python3
"""scripts/uat_test8_semantic.py — UAT Test 8: confirm semantic clustering path.

Inserts three synthetic articles:
  * item1 (PIR-1): title with no keyword overlap with item2, embedding = vector A
  * item2 (PIR-1): title with no keyword overlap with item1, embedding = vector A
  * item3 (PIR-2): title shares keywords with item1, embedding = vector B (different)

Because clustering runs per-CCIR, the cross-CCIR keyword overlap is irrelevant.
Keyword fallback within PIR-1 would NOT merge item1 and item2 (no shared keywords).
Semantic clustering SHOULD merge item1 and item2 (nearly identical embeddings).

The script then calls the same clustering path used by the brief app and prints
the cluster assignments, plus fetches /sab to verify rendered multi-item clusters.
"""
import datetime
import hashlib
import os
import subprocess
import sys
import time
import uuid

import numpy as np
import psycopg
from psycopg.rows import dict_row

DSN = os.environ.get(
    "INFOTRIAGE_PG_DSN",
    "postgresql://infotriage:infotriage_dev@localhost:22000/infotriage",
)

# Two divergent unit vectors (cosine similarity ~0.0)
rng = np.random.default_rng(123)
_vec_a = rng.standard_normal(1024).astype(np.float32)
_vec_a /= np.linalg.norm(_vec_a)
_vec_b = rng.standard_normal(1024).astype(np.float32)
_vec_b /= np.linalg.norm(_vec_b)


def _item_id(title: str) -> str:
    return hashlib.sha256(f"uat8\x00{title}".encode()).hexdigest()


def _seed() -> list[str]:
    now = datetime.datetime.now(datetime.timezone.utc)
    rows = [
        # PIR-1 items with same embedding but dissimilar titles
        (
            "PIR-1",
            "none",
            8,
            "Zebra migration patterns observed in savannah",
            "UAT-A",
            _vec_a.tolist(),
        ),
        (
            "PIR-1",
            "none",
            7,
            "Quantum computing advances accelerate research",
            "UAT-B",
            _vec_a.tolist(),
        ),
        # PIR-2 item with title keywords overlapping item1 but different embedding
        (
            "PIR-2",
            "none",
            8,
            "Zebra migration patterns shift northward",
            "UAT-C",
            _vec_b.tolist(),
        ),
    ]

    conn = psycopg.connect(DSN)
    item_ids = []
    try:
        with conn.cursor() as cur:
            # Clean up any previous UAT-8 rows
            cur.execute(
                "DELETE FROM infotriage.embeddings WHERE item_id IN (SELECT id FROM infotriage.articles WHERE source_type = 'uat8')"
            )
            cur.execute(
                "DELETE FROM infotriage.enrichment WHERE item_id IN (SELECT id FROM infotriage.articles WHERE source_type = 'uat8')"
            )
            cur.execute("DELETE FROM infotriage.articles WHERE source_type = 'uat8'")

            for ccir, cnr, score, title, source, embedding in rows:
                item_id = _item_id(title)
                item_ids.append(item_id)
                url = f"https://uat8.example.com/{uuid.uuid4().hex[:8]}"
                ts = now - datetime.timedelta(hours=1)

                cur.execute(
                    """
                    INSERT INTO infotriage.articles (id, source, source_type, url, title, ts, lang, summary)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        source = EXCLUDED.source,
                        source_type = EXCLUDED.source_type,
                        url = EXCLUDED.url,
                        title = EXCLUDED.title,
                        ts = EXCLUDED.ts,
                        lang = EXCLUDED.lang,
                        summary = EXCLUDED.summary
                    """,
                    (
                        item_id,
                        source,
                        "uat8",
                        url,
                        title,
                        ts,
                        "no",
                        f"Summary: {title}",
                    ),
                )

                cur.execute(
                    """
                    INSERT INTO infotriage.enrichment
                        (item_id, ccir, cnr, score, bucket, why, pmesii, tessoc, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (item_id) DO UPDATE SET
                        ccir = EXCLUDED.ccir,
                        cnr = EXCLUDED.cnr,
                        score = EXCLUDED.score,
                        bucket = EXCLUDED.bucket,
                        why = EXCLUDED.why,
                        pmesii = EXCLUDED.pmesii,
                        tessoc = EXCLUDED.tessoc,
                        created_at = EXCLUDED.created_at
                    """,
                    (
                        item_id,
                        ccir,
                        cnr,
                        score,
                        "read",
                        f"Why: {title}",
                        "political",
                        "time",
                        ts,
                    ),
                )

                cur.execute(
                    """
                    INSERT INTO infotriage.embeddings (item_id, embedding, model)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (item_id) DO UPDATE SET
                        embedding = EXCLUDED.embedding,
                        model = EXCLUDED.model
                    """,
                    (item_id, embedding, "intfloat/multilingual-e5-large"),
                )
        conn.commit()
        print(f"Seeded {len(rows)} UAT-8 test rows: {item_ids}")
    finally:
        conn.close()
    return item_ids


def _cluster_assignments() -> dict[str, list[list[str]]]:
    """Return cluster assignments by CCIR using the brief app clustering path."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from apps.brief.html_renderer import _apply_semantic_clustering, _row_to_verdict

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
                WHERE a.source_type = 'uat8'
                ORDER BY e.score DESC
                """
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    verdicts = [_row_to_verdict(r) for r in rows]
    clustered = _apply_semantic_clustering(verdicts, threshold=0.75)

    by_ccir: dict[str, list[list[str]]] = {}
    for v in clustered:
        by_ccir.setdefault(v["ccir"], []).append((v["item_id"], v.get("_cluster_idx")))

    # Group item_ids by cluster index per CCIR
    result: dict[str, list[list[str]]] = {}
    for ccir, items in by_ccir.items():
        clusters: dict[int, list[str]] = {}
        for item_id, idx in items:
            clusters.setdefault(idx if idx is not None else -1, []).append(item_id)
        result[ccir] = list(clusters.values())
    return result


def _check_sab() -> str:
    # Clear cache and fetch fresh /sab
    subprocess.run(["rm", "-f", "data/digests/sab.html"], check=True)
    time.sleep(2)
    result = subprocess.run(
        ["curl", "-s", "http://localhost:22040/sab"],
        capture_output=True,
        text=True,
    )
    result.check_returncode()
    html = result.stdout

    # Extract cluster counts for PIR-1 and PIR-2
    import re

    matches = re.findall(
        r'<section class="slide" id="pir-1"[\s\S]*?ccir-count">(\d+) saker · (\d+) klynger',
        html,
    )
    pir1 = matches[0] if matches else ("?", "?")
    matches = re.findall(
        r'<section class="slide" id="pir-2"[\s\S]*?ccir-count">(\d+) saker · (\d+) klynger',
        html,
    )
    pir2 = matches[0] if matches else ("?", "?")
    return f"PIR-1: {pir1[0]} saker · {pir1[1]} klynger; PIR-2: {pir2[0]} saker · {pir2[1]} klynger"


def main():
    item_ids = _seed()
    assignments = _cluster_assignments()
    print("Cluster assignments by CCIR:")
    for ccir, clusters in assignments.items():
        print(f"  {ccir}: {clusters}")

    # Assertions
    pir1 = assignments.get("PIR-1", [])
    pir2 = assignments.get("PIR-2", [])

    assert any(
        len(c) == 2 for c in pir1
    ), "Expected two PIR-1 items to be merged into one semantic cluster"
    assert all(
        len(c) == 1 for c in pir2
    ), "Expected PIR-2 item to remain a singleton (different embedding)"
    print("Semantic clustering assertions passed.")

    sab_summary = _check_sab()
    print(f"Rendered /sab: {sab_summary}")


if __name__ == "__main__":
    main()
