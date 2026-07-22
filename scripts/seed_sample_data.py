#!/usr/bin/env python3
"""scripts/seed_sample_data.py — seed sample articles/enrichments/embeddings for UAT.

Populates the running infotriage Postgres with synthetic articles across several
CCIR sections, including CNR-I alerts and embeddings so /sab renders CNR alerts,
CCIR sections, and semantic clusters.

Usage:
    python3 scripts/seed_sample_data.py

Environment:
    INFOTRIAGE_PG_DSN — Postgres DSN (default: local dev port 22000)
"""
import datetime
import hashlib
import os
import random
import uuid

import numpy as np
import psycopg

DSN = os.environ.get(
    "INFOTRIAGE_PG_DSN",
    "postgresql://infotriage:infotriage_dev@localhost:22000/infotriage",
)

# Fixed seed for reproducible embeddings
rng = np.random.default_rng(42)


def _item_id(source_type: str, url: str, title: str) -> str:
    return hashlib.sha256(f"{source_type}\x00{url}\x00{title}".encode()).hexdigest()


def _embedding_for_ccir(ccir: str, dim: int = 1024) -> list[float]:
    """Return a deterministic 1024-dim unit vector for a CCIR bucket.

    Items in the same CCIR get very similar embeddings (so they cluster),
    items in different CCIRs get divergent embeddings.
    """
    # Hash CCIR to a stable random direction
    seed = int(hashlib.sha256(ccir.encode()).hexdigest()[:16], 16)
    rng_local = np.random.default_rng(seed)
    vec = rng_local.standard_normal(dim).astype(np.float32)
    vec /= np.linalg.norm(vec)
    return vec.tolist()


def seed() -> None:
    now = datetime.datetime.now(datetime.timezone.utc)

    # Sample data: list of (ccir, cnr, score, title, source, source_type, pmesii, tessoc)
    samples = [
        # CNR-I alerts (should appear in CNR slide)
        (
            "PIR-1",
            "I",
            9,
            "Russisk militær aktivitet øker ved ukrainsk grense",
            "NRK",
            "rss",
            "military",
            "terror",
        ),
        (
            "PIR-1",
            "I",
            8,
            "Ukraina melder om nye angrep i øst",
            "Aftenposten",
            "rss",
            "military",
            "espionage",
        ),
        (
            "PIR-3",
            "I",
            9,
            "NATO øker beredskap i Øst-Europa",
            "VG",
            "rss",
            "military",
            "subversion",
        ),
        # Other PIR-1 items (cluster with the CNR ones)
        (
            "PIR-1",
            "none",
            7,
            "EU diskuterer nye sanksjoner mot Russland",
            "Dagens Næringsliv",
            "rss",
            "political",
            "subversion",
        ),
        (
            "PIR-1",
            "none",
            6,
            "Ukrainsk president holder tale til nasjonen",
            "NRK",
            "rss",
            "political",
            "sabotage",
        ),
        # PIR-2 items
        (
            "PIR-2",
            "none",
            8,
            "Norsk militærøvelse i Barentshavet",
            "Forsvaret",
            "rss",
            "military",
            "terror",
        ),
        (
            "PIR-2",
            "none",
            7,
            "Arktisk råd møtes i Tromsø",
            "High North News",
            "rss",
            "political",
            "subversion",
        ),
        # PIR-4 items
        (
            "PIR-4",
            "II",
            8,
            "Cyberangrep rammer norsk infrastruktur",
            "Tek.no",
            "rss",
            "infrastructure",
            "sabotage",
        ),
        (
            "PIR-4",
            "none",
            6,
            "Ny malware-kampanje målretter seg nordiske bedrifter",
            "Digi.no",
            "rss",
            "information",
            "sabotage",
        ),
        # FFIR-3 items
        (
            "FFIR-3",
            "none",
            7,
            "Norsk forsvar investerer i droneteknologi",
            "Forsvaret",
            "rss",
            "military",
            "organized crime",
        ),
        (
            "FFIR-3",
            "none",
            6,
            "Forsvarsindustrien øker produksjonen",
            "DN",
            "rss",
            "economic",
            "organized crime",
        ),
    ]

    conn = psycopg.connect(DSN)
    try:
        with conn.cursor() as cur:
            for ccir, cnr, score, title, source, source_type, pmesii, tessoc in samples:
                url = f"https://example.com/{uuid.uuid4().hex[:8]}"
                item_id = _item_id(source_type, url, title)
                ts = now - datetime.timedelta(hours=random.randint(1, 12))

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
                        source_type,
                        url,
                        title,
                        ts,
                        "no",
                        f"Summary for {title}",
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
                        pmesii,
                        tessoc,
                        ts,
                    ),
                )

                embedding = _embedding_for_ccir(ccir)
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
        print(f"Seeded {len(samples)} sample articles/enrichments/embeddings.")
    finally:
        conn.close()


if __name__ == "__main__":
    seed()
