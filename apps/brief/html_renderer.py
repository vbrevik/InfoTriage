#!/usr/bin/env python3
"""html_renderer.py — HTML SAB renderer for the Brief App (Phase 6, Wave 2).

Adapts sab_html.py's build_html() to consume enrichment rows from Postgres
instead of Fever verdict dicts. The 1064-line HTML template is imported via
sab_html.build_html(), never copied (D-12) — this module is the only place
in apps/brief that touches sab_html.

Enrichment row dict keys (infotriage.enrichment):
  item_id, ccir, cnr, score, bucket, why, pmesii, tessoc, title, summary, source

CNR vocabulary (RAW): "none" | "I" | "II" — passed through unchanged;
sab_html's CNR slide matches on cnr == "I", which RAW satisfies directly.

Pure library: no HTTP, no Docker, no file IO — main.py owns serving and writes.
"""
import json
import os
import sys

# Import build_html from sab_html — template imported, never copied (D-12).
# Same path convention as renderer.py's digest import.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "triage"))
from sab_html import build_html as _sab_build_html  # noqa: E402

# Import semantic clustering from the new clustering module
from apps.brief.clustering import (
    EnrichedItem,
    cluster_items_in_memory,
)  # noqa: E402

def _row_to_verdict(row: dict) -> dict:
    """Map an enrichment row to the verdict-dict shape build_html() expects.

    Enrichment rows have no url or fetch-epoch column: url renders as an
    empty href and the "Sist hentet" fetch line is omitted (t absent).
    """
    return {
        "item_id": row.get("item_id", ""),
        "ccir": row.get("ccir"),
        "cnr": row.get("cnr", "none"),
        "score": row.get("score", 0),
        "why": row.get("why", ""),
        "pmesii": row.get("pmesii"),
        "tessoc": row.get("tessoc"),
        "title": row.get("title", ""),
        "summary": row.get("summary", ""),
        "source": row.get("source", ""),
        "url": row.get("url", ""),
        "embedding": row.get("embedding"),
    }


def _apply_semantic_clustering(verdicts: list[dict], threshold: float = 0.75) -> list[dict]:
    """Apply semantic clustering to verdicts using pgvector embeddings.

    Mirrors the clustering logic in renderer.py: per-CCIR semantic clustering
    using pgvector HNSW cosine similarity. Returns verdicts with cluster
    metadata added (_cluster_idx, _cluster_size, _sources_in_cluster).

    Args:
        verdicts: List of verdict dicts with item_id, embedding, ccir, etc.
        threshold: Cosine similarity threshold (0.0-1.0). Default 0.75.

    Returns:
        List of verdict dicts with cluster metadata added.
    """
    if not verdicts:
        return verdicts

    # Build EnrichedItem objects for clustering
    items_by_ccir: dict[str, list[EnrichedItem]] = {}
    for v in verdicts:
        emb = v.get("embedding")
        # psycopg may return pgvector vectors as JSON strings or Vector objects;
        # normalize to a plain list so cosine distance works.
        if isinstance(emb, str) and emb.startswith("["):
            try:
                emb = json.loads(emb)
            except ValueError:
                emb = None
        elif hasattr(emb, "to_list"):
            emb = emb.to_list()
        if not isinstance(emb, list) or not emb:
            emb = None
        item = EnrichedItem(
            item_id=v.get("item_id", ""),
            title=v.get("title", ""),
            source=v.get("source", ""),
            url=v.get("url", ""),
            summary=v.get("summary", ""),
            ccir=v.get("ccir", ""),
            cnr=v.get("cnr", ""),
            score=v.get("score", 0),
            bucket=v.get("bucket", ""),
            why=v.get("why", ""),
            pmesii=v.get("pmesii"),
            tessoc=v.get("tessoc"),
            embedding=emb,
        )
        cid = (v.get("ccir") or "none").upper()
        items_by_ccir.setdefault(cid, []).append(item)

    # Cluster within each CCIR section
    clustered_items = []
    for cid, items in items_by_ccir.items():
        if not items:
            continue
        clusters = cluster_items_in_memory(items, threshold=threshold)
        for cluster_idx, cluster in enumerate(clusters):
            for item in cluster:
                # Find the original verdict to add cluster metadata
                for v in verdicts:
                    if v.get("item_id") == item.item_id:
                        v["_cluster_idx"] = cluster_idx
                        v["_cluster_size"] = len(cluster)
                        v["_sources_in_cluster"] = len(
                            {i.source for i in cluster}
                        )
                        break

    return verdicts


def build_html(enrichment_rows: list[dict], period: str,
               with_bluf: bool = True, generated_at: str | None = None,
               *, cluster_threshold: float = 0.75,
               cutoff_epoch: int | None = None) -> str:
    """Render the full SAB HTML page from enrichment rows.

    Delegates to sab_html.build_html() after row mapping and semantic
    clustering — same slides, same BLUF prompt template and citation rules
    (D-07), same CCIR_ORDER.

    Args:
        enrichment_rows: Enrichment rows from Postgres (with embeddings).
        period: Human-readable period label.
        with_bluf: Whether to synthesize BLUF sections.
        generated_at: Optional timestamp string.
        cluster_threshold: Cosine similarity threshold for semantic clustering.
    """
    # Apply semantic clustering BEFORE passing to sab_html. The verdict dicts
    # carry _cluster_idx metadata; sab_html.cluster() detects it and uses the
    # pre-computed clusters directly — no monkey-patching required.
    verdicts = [_row_to_verdict(r) for r in enrichment_rows]
    verdicts = _apply_semantic_clustering(verdicts, threshold=cluster_threshold)

    return _sab_build_html(verdicts, period, with_bluf=with_bluf,
                           generated_at=generated_at,
                           cutoff_epoch=cutoff_epoch)
