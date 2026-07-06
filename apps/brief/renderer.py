#!/usr/bin/env python3
"""renderer.py — Markdown renderer for the Brief App (Phase 6).

Produces brief.md, cluster.md, list.md, and bluf.md from enrichment rows
in Postgres. Adapts digest.py's write_brief()/write_list()/write_bluf() to
read from enrichment rows instead of Fever verdict dicts.

Import conventions:
- CCIR_ORDER: import from apps.triage.digest (never redefine)
- llm: import from apps.triage.triage_score
- HTML_TEMPLATE: only html_renderer.py should import this from sab_html

Enrichment row dict keys:
  item_id, ccir, cnr, score, bucket, why, pmesii, tessoc, title, summary, source

CNR vocabulary (RAW): "none" | "I" | "II"
  → "none" = Routine, "I" = CAT I, "II" = CAT II
Bucket vocabulary (RAW): "read" | "maybe" | "skip"
  → "read" = keep, "maybe" = maybe, "skip" = skip
"""
import os
import re
import sys
from typing import Optional

# Import CCIR_ORDER from digest.py — never redefine here
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "triage"))
from digest import CCIR_ORDER, line as _digest_line  # noqa: E402
from apps.brief.clustering import cluster_items_in_memory, EnrichedItem  # noqa: E402

# LLM import for BLUF synthesis
try:
    from triage_score import llm  # noqa: E402
except ImportError:
    llm = None  # type: ignore[misc,assignment]

# CNR display mapping
_CNR_DISPLAY = {
    "none": "Routine",
    "I": "I",
    "II": "II",
}

# CNR priority for sorting (lower = higher priority)
_CNR_PRIORITY = {
    "none": 2,  # Routine last
    "I": 0,     # CAT I first
    "II": 1,    # CAT II second
}


def _parse_ccir_display(title_map: dict[str, str], ccir: Optional[str]) -> str:
    """Return display string for a CCIR ID."""
    if not ccir:
        return ""
    return title_map.get(ccir, ccir)


def _group_by_cnr_and_ccir(rows: list[dict], ccir_order: list[tuple[str, str]]) -> dict[str, list[dict]]:
    """Group enrichment rows by CNR priority then CCIR section.
    
    Returns dict keyed by "CAT_I", "CAT_II", "ROUTINE", each value is list of rows.
    Within each group, rows are further groupable by CCIR via the caller.
    """
    # Sort by CNR priority, then score descending
    sorted_rows = sorted(
        rows,
        key=lambda r: (_CNR_PRIORITY.get(r.get("cnr", "none"), 2), -r.get("score", 0)),
    )
    
    cat_i = [r for r in sorted_rows if r.get("cnr") == "I"]
    cat_ii = [r for r in sorted_rows if r.get("cnr") == "II"]
    routine = [r for r in sorted_rows if r.get("cnr") in ("none", "")]
    
    return {
        "CAT_I": cat_i,
        "CAT_II": cat_ii,
        "ROUTINE": routine,
    }


def _group_by_ccir(rows: list[dict], ccir_order: list[tuple[str, str]]) -> dict[str, list[dict]]:
    """Group rows by CCIR section, preserving CCIR_ORDER."""
    title_map = dict(ccir_order)
    by_ccir: dict[str, list[dict]] = {}
    for r in rows:
        key = (r.get("ccir") or "none").upper()
        by_ccir.setdefault(key, []).append(r)
    # Return in CCIR_ORDER, then any extras
    ordered: list[dict] = []
    for cid, _ in ccir_order:
        if cid in by_ccir:
            ordered.extend(by_ccir[cid])
    # Add any CCIRs not in the order
    for cid, items in by_ccir.items():
        if not any(cid == co[0] for co in ccir_order):
            ordered.extend(items)
    return dict(zip(ccir_order + tuple(cid for cid in by_ccir if cid not in dict(ccir_order)),
                    [by_ccir.get(ccid, []) for ccid, _ in ccir_order] +
                    [by_ccir[cid] for cid in by_ccir if cid not in dict(ccir_order)]))


def _rows_to_enriched_items(rows: list[dict]) -> list[EnrichedItem]:
    """Convert enrichment row dicts to EnrichedItem objects for clustering."""
    return [
        EnrichedItem(
            item_id=r.get("item_id", f"tmp-{i}"),
            title=r.get("title", ""),
            source=r.get("source", ""),
            url=r.get("url", ""),
            summary=r.get("summary", ""),
            ccir=r.get("ccir", ""),
            cnr=r.get("cnr", ""),
            score=r.get("score", 0),
            bucket=r.get("bucket", ""),
            why=r.get("why", ""),
            pmesii=r.get("pmesii"),
            tessoc=r.get("tessoc"),
            embedding=r.get("embedding", [0.0] * 4),
        )
        for i, r in enumerate(rows)
    ]


def _enriched_to_dicts(items: list[EnrichedItem]) -> list[dict]:
    """Convert EnrichedItem objects back to dicts for rendering."""
    return [{
        "item_id": i.item_id,
        "title": i.title,
        "source": i.source,
        "url": i.url,
        "summary": i.summary,
        "ccir": i.ccir,
        "cnr": i.cnr,
        "score": i.score,
        "bucket": i.bucket,
        "why": i.why,
        "pmesii": i.pmesii,
        "tessoc": i.tessoc,
        "embedding": i.embedding,
    } for i in items]


def _cluster_rows(rows: list[dict]) -> list[dict]:
    """Cluster enrichment rows using pgvector. Returns same format as _digest_cluster.
    
    Returns list of dicts: [{"items": [dict, dict, ...]}, ...]
    """
    items = _rows_to_enriched_items(rows)
    clusters_raw = cluster_items_in_memory(items, threshold=0.75)
    return [{"items": _enriched_to_dicts(cl)} for cl in clusters_raw]

def render_brief(
    enrichment_rows: list[dict],
    ccir_order: list[tuple[str, str]] | None = None,
) -> str:
    """Produce SAB markdown: CNR CAT I first, then CCIR sections.
    
    Args:
        enrichment_rows: list of enrichment row dicts
        ccir_order: CCIR display order (default from digest.py)
    
    Returns:
        Markdown string for brief.md
    """
    if ccir_order is None:
        ccir_order = CCIR_ORDER
    title_map = dict(ccir_order)
    
    # Filter to items with a CCIR (exclude "none")
    kept = [r for r in enrichment_rows if (r.get("ccir") or "none").lower() != "none"]
    
    # Group by CNR priority
    by_cnr = _group_by_cnr_and_ccir(kept, ccir_order)
    
    lines: list[str] = [
        "# InfoTriage · SAB",
        f"_{len(kept)} saker · ~10 min_\n",
    ]
    
    # CNR CAT I first (flagged)
    cat_i = by_cnr["CAT_I"]
    if cat_i:
        lines.append("## 🚩 CNR — varsle straks")
        # Cluster items
        clusters = _cluster_rows(cat_i)
        for cl in clusters:
            lead = max(cl["items"], key=lambda i: i.get("score", 0))
            srcs = sorted({i.get("source", "") for i in cl["items"]})
            tag = f"  _({len(cl['items'])} kilder: {', '.join(srcs)})_" if len(cl["items"]) > 1 else ""
            flag = "🚩 " if any(i.get("cnr") == "I" for i in cl["items"]) else ""
            lines.append(
                f"- {flag}**[{lead.get('score')}] {lead.get('title','')}**{tag}"
                f"  [les]({lead.get('url','')})"
            )
        lines.append("")
    
    # CCIR sections per priority group
    for priority_label, group_rows in [("CAT_I", cat_i), ("CAT_II", by_cnr["CAT_II"]), ("ROUTINE", by_cnr["ROUTINE"])]:
        if not group_rows:
            continue
        # Group by CCIR within this priority
        by_ccir: dict[str, list[dict]] = {}
        for r in group_rows:
            cid = (r.get("ccir") or "none").upper()
            by_ccir.setdefault(cid, []).append(r)
        
        for cid, title in ccir_order:
            items = by_ccir.get(cid, [])
            if not items:
                continue
            lines.append(f"## {cid} · {title}")
            cs = sorted(
                _cluster_rows(items),
                key=lambda c: -max(i.get("score", 0) for i in c["items"]),
            )
            for cl in cs[:6]:
                lead = max(cl["items"], key=lambda i: i.get("score", 0))
                srcs = sorted({i.get("source", "") for i in cl["items"]})
                extra = f"  _({len(cl['items'])} kilder)_" if len(cl["items"]) > 1 else ""
                lines.append(_digest_line(lead, extra))
            lines.append("")
    
    # Routine without CCIR
    routine_no_ccir = [r for r in enrichment_rows if (r.get("ccir") or "none").lower() == "none" and r.get("cnr") in ("none", "")]
    if routine_no_ccir:
        lines.append("## Routine")
        for r in sorted(routine_no_ccir, key=lambda x: -x.get("score", 0))[:10]:
            lines.append(f"- {r.get('title', '')}  _[{r.get('score', 0)}]_  [les]({r.get('url', '')})")
        lines.append("")
    
    return "\n".join(lines)


def render_list(
    enrichment_rows: list[dict],
) -> str:
    """Return markdown with items having score >= 8, sorted by score descending.
    
    Args:
        enrichment_rows: list of enrichment row dicts
    
    Returns:
        Markdown string for list.md
    """
    strict = sorted(
        [r for r in enrichment_rows if r.get("score", 0) >= 8],
        key=lambda x: -x["score"],
    )
    
    lines: list[str] = [
        "# InfoTriage · list (strict 🔥)",
        f"\n{len(strict)} viktigste\n",
    ]
    
    for r in strict:
        flag = "🚩 " if r.get("cnr") == "I" else ""
        ccir_display = _parse_ccir_display(dict(CCIR_ORDER), r.get("ccir"))
        lines.append(
            f"- {flag}**[{r['score']}] {r.get('title','')}**"
            f"  · {r.get('source','')}  ·  {ccir_display or 'none'}"
        )
        lines.append(f"  - {r.get('why','')} — [les]({r.get('url','')})")
    
    return "\n".join(lines)


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: chars/4 (Qwen3 average ~4 chars/tok)."""
    return max(1, len(text) // 4)


def render_bluf(
    items: list[dict],
    ccir_title: str,
    ccir_id: str = "",
    top_n: int = 5,
    cap_total: int = 6000,
) -> str:
    """Generate LLM-synthesized BLUF for a CCIR section.
    
    Uses the same prompt template frame as digest.py write_bluf().
    Every claim must have [N] bracketed citations.
    
    Args:
        items: enrichment rows for this CCIR section
        ccir_title: display title for the CCIR
        ccir_id: CCIR ID (e.g., "PIR-1")
        top_n: number of top items to include
        cap_total: max input tokens per LLM prompt
    
    Returns:
        BLUF text from LLM, or placeholder on failure
    """
    if not items or llm is None:
        return "_(BLUF utilgjengelig — sjekk logg for detaljer)_"
    
    # Sort by score, take top_n
    top = sorted(items, key=lambda x: -x.get("score", 0))[:top_n]
    
    # Build context blocks
    ctx_blocks: list[str] = []
    for i, it in enumerate(top, 1):
        summary = (it.get("summary") or "")[:500]
        ctx_blocks.append(
            f"[{i}] KILDE: {it.get('source', '')}\n"
            f"TITTEL: {it.get('title', '')}\n"
            f"OPPSUMMERING: {summary}\n"
        )
    
    # Frame template (same as digest.py)
    frame_template = (
        f"You are an intelligence analyst writing a BLUF (Bottom Line Up "
        f"Front) for the topic '{ccir_title}' ({ccir_id}).\n\n"
        f"Recent reports ({{N}} items):\n{{CTX}}\n\n"
        "Instructions:\n"
        "1. Write a 2-3 sentence BLUF in Norwegian summarizing the "
        "overarching developments *across* these reports.\n"
        "2. Cite every claim with bracketed numeric refs, e.g. [1] or "
        "[2][4]. A claim with no citation is wrong.\n"
        "3. CONTRADICTIONS: if sources disagree on facts, attribution, or "
        "intent, you MUST report both positions explicitly. Example: "
        "\"Kildene spriker: [1] hevender X, mens [3] oppgir Y.\" Do NOT "
        "silently pick one and discard the other.\n"
        "4. Output ONLY the BLUF text. No headers, no source list. "
        "If the items don't share one overarching story, write one "
        "sentence per cluster, each still cited with bracketed refs."
    )
    
    # Per-prompt truncation
    ctx_blocks_copy = ctx_blocks[:]
    while len(ctx_blocks_copy) > 1 and _estimate_tokens(
        frame_template.format(N=len(ctx_blocks_copy), CTX="".join(ctx_blocks_copy))
    ) > cap_total:
        ctx_blocks_copy.pop()
    
    if not ctx_blocks_copy:
        return "_(BLUF sevisjon hoppet over — cap for lav)_\n"
    
    prompt = frame_template.format(N=len(ctx_blocks_copy), CTX="".join(ctx_blocks_copy))
    
    try:
        print(f"  …generating BLUF for {ccir_id or 'topic'} ({len(ctx_blocks_copy)} items, "
              f"~{_estimate_tokens(prompt)} tok)", file=sys.stderr, flush=True)
        bluf_text = llm([{"role": "user", "content": prompt}], max_tokens=400).strip()
        return bluf_text
    except Exception as e:
        print(f"  …BLUF failure for {ccir_id or 'topic'}: {type(e).__name__}: {e}",
              file=sys.stderr, flush=True)
        return "_(BLUF unavailable — check log for details)_\n"


def render_cluster(
    enrichment_rows: list[dict],
    ccir_order: list[tuple[str, str]] | None = None,
) -> str:
    """Produce cluster markdown grouped by CCIR section.
    
    Uses pgvector HNSW semantic clustering per CCIR section.
    
    Args:
        enrichment_rows: list of enrichment row dicts
        ccir_order: CCIR display order
    
    Returns:
        Markdown string for cluster.md
    """
    if ccir_order is None:
        ccir_order = CCIR_ORDER
    title_map = dict(ccir_order)
    
    # Filter to items with a CCIR
    kept = [r for r in enrichment_rows if (r.get("ccir") or "none").lower() != "none"]
    
    lines: list[str] = [
        "# InfoTriage · cluster",
        f"\n{len(kept)} saker\n",
    ]
    
    # Group by CCIR first, then cluster within each
    by_ccir: dict[str, list[dict]] = {}
    for r in kept:
        cid = (r.get("ccir") or "none").upper()
        by_ccir.setdefault(cid, []).append(r)
    
    for cid, title in ccir_order:
        items = by_ccir.get(cid, [])
        if not items:
            continue
        lines.append(f"## {cid} · {title}")
        clusters = _cluster_rows(items)
        for cl in clusters:
            lead = max(cl["items"], key=lambda i: i.get("score", 0))
            srcs = sorted({i.get("source", "") for i in cl["items"]})
            tag = f"  _({len(cl['items'])} kilder: {', '.join(srcs)})_" if len(cl["items"]) > 1 else ""
            flag = "🚩 " if any(i.get("cnr") == "I" for i in cl["items"]) else ""
            lines.append(
                f"- {flag}**[{lead.get('score')}] {lead.get('title','')}**{tag}"
                f"  [les]({lead.get('url','')})"
            )
        lines.append("")
    
    # Items without a CCIR
    no_ccir = [r for r in enrichment_rows if (r.get("ccir") or "none").lower() == "none"]
    if no_ccir:
        lines.append("## Uten CCIR")
        for cl in _cluster_rows(no_ccir):
            lead = max(cl["items"], key=lambda i: i.get("score", 0))
            lines.append(
                f"- **[{lead.get('score')}] {lead.get('title','')}**"
                f"  [les]({lead.get('url','')})"
            )
        lines.append("")
    
    return "\n".join(lines)
