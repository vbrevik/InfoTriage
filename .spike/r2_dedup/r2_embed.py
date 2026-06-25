#!/usr/bin/env python3.12
"""R2 Dedup bake-off — embed corpus with bge-m3 and mE5-large, emit candidate triples.

Embeds title + summary[:512] ONLY (never full body — long-input caveat from RESEARCH).
Both models produce 1024-dim normalized vectors (cosine == dot product after normalization).
For mE5-large the required 'query:'/'passage:' instruction prefix is applied.
Embeddings cached to disk so r2_threshold.py does not re-encode.
"""
import json
import os
import re
import sys
import csv
from datetime import datetime, timezone, timedelta

import numpy as np

SPIKE_DIR = os.path.join(os.path.dirname(__file__), "..")
ITEMS_JSON = os.path.join(SPIKE_DIR, "items.json")
OUT_DIR = os.path.dirname(__file__)

MODELS = {
    "bge_m3": {
        "model_id": "BAAI/bge-m3",
        "prefix": None,              # bge-m3: no instruction prefix needed
        "emb_file": os.path.join(OUT_DIR, "embeddings_bge_m3.npy"),
        "ids_file": os.path.join(OUT_DIR, "item_ids.json"),
    },
    "me5_large": {
        "model_id": "intfloat/multilingual-e5-large",
        "prefix": "passage: ",       # mE5-large REQUIRES passage: prefix for corpus docs
        "emb_file": os.path.join(OUT_DIR, "embeddings_me5_large.npy"),
        "ids_file": os.path.join(OUT_DIR, "item_ids.json"),  # shared id order
    },
}

CANDIDATE_CSV = os.path.join(OUT_DIR, "same_story_triples.csv")
EXPECTED_DIM = 1024

# Stop words (NO + EN + RU common) for keyword-overlap clustering
STOP = set(
    "the a an of to in on for and or at by with from is are as it its this that "
    "i og å en et er på til av for som med det den de har om mot ved du vi "
    "в и на с к о от не по за то как но из а это мы вы они".split()
)


def load_items():
    with open(ITEMS_JSON, encoding="utf-8") as f:
        return json.load(f)


def build_text(item, prefix=None):
    """Build embedding input: title + space + summary[:512].
    Optionally prepend instruction prefix (required for mE5-large).
    """
    title = (item.get("title") or "").strip()
    summary = (item.get("summary") or "")[:512].strip()
    text = f"{title} {summary}".strip()
    if prefix:
        text = prefix + text
    return text


def embed_model(model_key, items):
    """Load model, embed all items, assert 1024-dim, cache to disk.
    Returns (embeddings_array, item_ids_list).
    """
    from sentence_transformers import SentenceTransformer

    cfg = MODELS[model_key]
    model_id = cfg["model_id"]
    prefix = cfg["prefix"]
    emb_file = cfg["emb_file"]
    ids_file = cfg["ids_file"]

    item_ids = [item["id"] for item in items]

    # Load from cache if present
    if os.path.exists(emb_file):
        print(f"  [{model_key}] Loading cached embeddings from {emb_file}")
        embeddings = np.load(emb_file)
        assert embeddings.shape == (len(items), EXPECTED_DIM), (
            f"Cache shape mismatch: {embeddings.shape} expected ({len(items)}, {EXPECTED_DIM})"
        )
        print(f"  [{model_key}] Cache OK: shape={embeddings.shape}")
        return embeddings, item_ids

    print(f"  [{model_key}] Loading model: {model_id} ...")
    model = SentenceTransformer(model_id)

    texts = [build_text(item, prefix) for item in items]
    print(f"  [{model_key}] Embedding {len(texts)} texts (normalize_embeddings=True) ...")
    embeddings = model.encode(
        texts,
        normalize_embeddings=True,   # cosine == dot product after normalization (RESEARCH Pitfall 6)
        show_progress_bar=True,
        batch_size=16,
    )

    # Assert 1024-dim (Pitfall 3)
    assert embeddings.shape[1] == EXPECTED_DIM, (
        f"[{model_key}] Expected {EXPECTED_DIM}-dim embeddings, got {embeddings.shape[1]}"
    )
    assert embeddings.shape[0] == len(items), (
        f"[{model_key}] Expected {len(items)} embeddings, got {embeddings.shape[0]}"
    )

    np.save(emb_file, embeddings)
    print(f"  [{model_key}] Saved to {emb_file} (shape={embeddings.shape})")

    # Save id order (shared for both models — same items list)
    with open(ids_file, "w") as f:
        json.dump(item_ids, f, indent=2)

    return embeddings, item_ids


def keywords(title):
    return {w for w in re.findall(r"[a-zA-ZæøåÆØÅ0-9]{4,}", (title or "").lower()) if w not in STOP}


def parse_published(item):
    """Parse ISO timestamp to UTC datetime, tolerant of offset-aware strings."""
    raw = item.get("published", "")
    if not raw:
        return None
    try:
        # Handle +00:00 and Z suffixes
        raw_clean = raw.replace("Z", "+00:00")
        return datetime.fromisoformat(raw_clean)
    except ValueError:
        return None


def cluster_by_time_and_keywords(items, window_hours=6, min_kw_overlap=2):
    """Group items into candidate same-story clusters.

    Same-source items require min_kw_overlap (default 2) word matches.
    Cross-source items use a relaxed threshold of 1 word match to catch
    cross-language same-story events (e.g. 'Venezuela' in NRK + TASS titles).
    Both still require items to fall within window_hours of each other.

    Returns: list of clusters, each cluster is a list of items.
    """
    def pub_key(item):
        dt = parse_published(item)
        return dt.timestamp() if dt else 0.0

    sorted_items = sorted(items, key=pub_key)
    clusters = []

    for item in sorted_items:
        kw = keywords(item["title"])
        pub = parse_published(item)
        placed = False

        for cluster in clusters:
            anchor_pub = parse_published(cluster[0])
            if pub and anchor_pub:
                time_diff = abs((pub - anchor_pub).total_seconds()) / 3600
                if time_diff > window_hours:
                    continue

            cluster_kw = cluster[0]["_kw"]
            overlap = len(kw & cluster_kw)
            same_source = item["source"] == cluster[0]["source"]

            # Cross-source: relax to 1 shared proper keyword (captures
            # cross-language events sharing a country/entity name like "Venezuela")
            threshold = min_kw_overlap if same_source else 1
            if overlap >= threshold:
                cluster.append(item)
                cluster[0]["_kw"] |= kw
                placed = True
                break

        if not placed:
            item_copy = dict(item)
            item_copy["_kw"] = kw
            clusters.append([item_copy])

    # Strip helper _kw key
    return [[{k: v for k, v in it.items() if k != "_kw"} for it in c] for c in clusters]


def generate_candidate_triples(clusters):
    """Propose candidate same-story triples from multi-source clusters.

    Priority:
    1. Clusters with items from 3 different sources -> propose one triple (one per source)
    2. Clusters with items from 2 different sources -> propose a pair (use two ids, leave third blank)
    3. Clusters with 3+ items from same source (intra-source near-duplicates) -> also include
    """
    rows = []
    seen_pairs = set()

    for cluster in clusters:
        if len(cluster) < 2:
            continue

        by_source = {}
        for item in cluster:
            by_source.setdefault(item["source"], []).append(item)

        sources = list(by_source.keys())
        n_sources = len(sources)

        if n_sources >= 3:
            # Pick one representative per source for the triple
            reps = [by_source[s][0] for s in sources[:3]]
            pair_key = tuple(sorted([reps[0]["id"], reps[1]["id"], reps[2]["id"]]))
            if pair_key not in seen_pairs:
                seen_pairs.add(pair_key)
                event = keywords(reps[0]["title"])
                note = "_".join(list(event)[:2]) if event else "unknown"
                rows.append({
                    "item_a_id": reps[0]["id"],
                    "item_b_id": reps[1]["id"],
                    "item_c_id": reps[2]["id"],
                    "same_story": "",
                    "notes": note,
                })
                # If one source has many items, add cross-item pairs within the same cluster
                for s in sources[:3]:
                    if len(by_source[s]) >= 2:
                        for i in range(min(2, len(by_source[s]) - 1)):
                            a = by_source[s][i]
                            b = by_source[s][i + 1]
                            pk = tuple(sorted([a["id"], b["id"], ""]))
                            if pk not in seen_pairs:
                                seen_pairs.add(pk)
                                rows.append({
                                    "item_a_id": a["id"],
                                    "item_b_id": b["id"],
                                    "item_c_id": "",
                                    "same_story": "",
                                    "notes": note + "_intra",
                                })

        elif n_sources == 2:
            for s1, s2 in [(sources[0], sources[1])]:
                a = by_source[s1][0]
                b = by_source[s2][0]
                pk = tuple(sorted([a["id"], b["id"], ""]))
                if pk not in seen_pairs:
                    seen_pairs.add(pk)
                    event = keywords(a["title"])
                    note = "_".join(list(event)[:2]) if event else "unknown"
                    rows.append({
                        "item_a_id": a["id"],
                        "item_b_id": b["id"],
                        "item_c_id": "",
                        "same_story": "",
                        "notes": note,
                    })

        else:
            # Single source — still propose if 3+ items (intra-source dedup check)
            items_in = cluster
            if len(items_in) >= 2:
                a = items_in[0]
                b = items_in[1]
                pk = tuple(sorted([a["id"], b["id"], ""]))
                if pk not in seen_pairs:
                    seen_pairs.add(pk)
                    event = keywords(a["title"])
                    note = "_".join(list(event)[:2]) if event else "unknown"
                    rows.append({
                        "item_a_id": a["id"],
                        "item_b_id": b["id"],
                        "item_c_id": items_in[2]["id"] if len(items_in) > 2 else "",
                        "same_story": "",
                        "notes": note + "_intra",
                    })

    return rows


def write_candidate_csv(rows):
    fieldnames = ["item_a_id", "item_b_id", "item_c_id", "same_story", "notes"]
    with open(CANDIDATE_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nCandidate triples CSV written: {CANDIDATE_CSV}")
    print(f"  {len(rows)} candidate rows (same_story left blank for human labeling)")


def main():
    print("=== R2 Dedup Bake-off: Embedding Phase ===\n")

    items = load_items()
    print(f"Loaded {len(items)} items from {ITEMS_JSON}")
    by_src = {}
    for item in items:
        by_src.setdefault(item["source"], 0)
        by_src[item["source"]] += 1
    for src, cnt in sorted(by_src.items()):
        print(f"  {src}: {cnt} items")

    print("\n--- Model 1: BAAI/bge-m3 ---")
    emb_bge, item_ids = embed_model("bge_m3", items)

    print("\n--- Model 2: intfloat/multilingual-e5-large ---")
    emb_me5, _ = embed_model("me5_large", items)

    print(f"\nEmbedding shapes: bge-m3={emb_bge.shape}, mE5-large={emb_me5.shape}")
    assert emb_bge.shape == emb_me5.shape == (len(items), EXPECTED_DIM), \
        f"Shape mismatch: bge={emb_bge.shape}, me5={emb_me5.shape}"
    print("Assert 1024-dim: PASS")

    # Spot-check: norms should be 1.0 after normalization
    bge_norms = np.linalg.norm(emb_bge, axis=1)
    me5_norms = np.linalg.norm(emb_me5, axis=1)
    assert np.allclose(bge_norms, 1.0, atol=1e-5), f"bge-m3 norms not 1: {bge_norms[:5]}"
    assert np.allclose(me5_norms, 1.0, atol=1e-5), f"mE5 norms not 1: {me5_norms[:5]}"
    print("Assert normalize_embeddings=1.0: PASS")

    # Generate candidate triple skeleton
    print("\n--- Clustering for candidate triples ---")
    clusters = cluster_by_time_and_keywords(items, window_hours=3, min_kw_overlap=2)
    multi_clusters = [c for c in clusters if len(c) >= 2]
    print(f"  Total clusters: {len(clusters)}, multi-item clusters: {len(multi_clusters)}")

    rows = generate_candidate_triples(clusters)
    write_candidate_csv(rows)

    print("\n=== Done ===")
    print("Next step: open same_story_triples.csv and hand-label each row:")
    print("  - Set same_story='yes' for rows covering the same real-world event")
    print("  - Set same_story='no' for control pairs that must NOT be merged")
    print("  - Ensure >= 10 same_story=yes rows AND >= 5 same_story=no rows")
    print("Then run: python3.12 r2_threshold.py")


if __name__ == "__main__":
    main()
