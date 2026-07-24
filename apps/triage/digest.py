#!/usr/bin/env python3
"""InfoTriage · SAB / tiered digests, CCIR-driven.

Covers everything that arrived SINCE your last situation update (default: yesterday
16:00 Europe/Oslo). Scores each item against ccir.md, then writes three views:

  cluster.md  (DEFAULT) same story across outlets collapsed; skim unique stories
  brief.md    the SAB — CNR 🚩 first, then a section per CCIR, ~10 min, links
  list.md     strict (score>=8), each with its one-line why + link

  python3 score/digest.py                       # cluster, since yesterday 16:00
  python3 score/digest.py --mode brief          # the SAB
  python3 score/digest.py --mode all
  python3 score/digest.py --since "2026-06-22 16:00"   # explicit cutoff (Oslo)
  python3 score/digest.py --hours 18                    # or a rolling window
"""
import os, sys, re, time, datetime
from zoneinfo import ZoneInfo

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
OUT = os.path.join(ROOT, "data", "digests")
OSLO = ZoneInfo("Europe/Oslo")
STOP = set(
    "the a an of to in on for and or at by with from is are as it its this that "
    "i og å en et er på til av for som med det den de har om mot ved".split()
)

# CCIR display order + titles now derive from the single-source registry.
# The old CCIR_ORDER↔ccir.md drift guard is superseded by
# tests/test_ccir_registry_sync.py (registry ↔ ccir.md consistency).
from contracts.ccir import CCIR_ORDER  # noqa: E402


def oslo_now():
    return datetime.datetime.fromtimestamp(time.time(), OSLO)


def default_cutoff():
    n = oslo_now()
    c = (n - datetime.timedelta(days=1)).replace(
        hour=16, minute=0, second=0, microsecond=0
    )
    return c


def stamp(dt):
    return dt.strftime("%Y-%m-%d %H:%M")


def keywords(title):
    return {
        w
        for w in re.findall(r"[a-zA-ZæøåÆØÅ0-9]{4,}", (title or "").lower())
        if w not in STOP
    }


def cluster(items):
    """greedy keyword-overlap clustering; returns list of clusters (lead + members)."""
    clusters = []
    for v in sorted(items, key=lambda x: -x.get("score", 0)):
        kw = keywords(v["title"])
        hit = next((c for c in clusters if len(kw & c["kw"]) >= 2), None)
        if hit:
            hit["items"].append(v)
            hit["kw"] |= kw
        else:
            clusters.append({"kw": kw, "items": [v]})
    return clusters


def line(v, withsrc=""):
    return f"- {v.get('why') or v['title']}{withsrc}  [les]({v.get('url','')})"


def _est_tokens(s):
    """Rough prompt-token estimate. Stdlib-first; chars/4 (Qwen3 average ~4 chars/tok)."""
    return max(1, len(s) // 4)


# ---- views ---------------------------------------------------------------


def kept(verdicts):
    return [v for v in verdicts if (v.get("ccir") or "none").lower() != "none"]


def write_cluster(verdicts, period):
    ks = kept(verdicts)
    cs = sorted(
        cluster(ks),
        key=lambda c: (-max(i.get("score", 0) for i in c["items"]), -len(c["items"])),
    )
    L = [
        f"# InfoTriage · cluster — {period}",
        f"\n{len(cs)} saker fra {len(ks)} elementer\n",
    ]
    for c in cs:
        lead = max(c["items"], key=lambda i: i.get("score", 0))
        srcs = sorted({i.get("source", "") for i in c["items"]})
        tag = (
            f"  _({len(c['items'])} kilder: {', '.join(srcs)})_"
            if len(c["items"]) > 1
            else ""
        )
        flag = "🚩 " if any(i.get("cnr") == "I" for i in c["items"]) else ""
        L.append(
            f"- {flag}**[{lead.get('score')}] {lead['title']}**{tag}  [les]({lead.get('url','')})"
        )
    return "cluster.md", "\n".join(L)


def write_brief(verdicts, period):
    ks = kept(verdicts)
    L = [
        f"# InfoTriage · SAB — {period}",
        f"_{len(ks)} saker som svarer på CCIR · ~10 min_\n",
    ]
    # CNR CAT I first
    cat1 = sorted(
        [v for v in ks if v.get("cnr") == "I"], key=lambda x: -x.get("score", 0)
    )
    if cat1:
        L.append("## 🚩 CNR — varsle straks")
        for c in cluster(cat1):
            lead = max(c["items"], key=lambda i: i.get("score", 0))
            L.append(line(lead))
        L.append("")
    # one section per CCIR, deduped, capped
    by = {}
    for v in ks:
        by.setdefault((v.get("ccir") or "none").upper(), []).append(v)
    for cid, title in CCIR_ORDER:
        grp = by.get(cid, [])
        if not grp:
            continue
        L.append(f"## {cid} · {title}")
        cs = sorted(
            cluster(grp), key=lambda c: -max(i.get("score", 0) for i in c["items"])
        )
        for c in cs[:6]:
            lead = max(c["items"], key=lambda i: i.get("score", 0))
            srcs = sorted({i.get("source", "") for i in c["items"]})
            extra = f"  _({len(c['items'])} kilder)_" if len(c["items"]) > 1 else ""
            L.append(line(lead, extra))
        L.append("")
    return "brief.md", "\n".join(L)


def write_bluf(verdicts, period, top_n=12, cap_total=6000):
    """Per-topic BLUF (Bottom Line Up Front) digest.

    For each CCIR, synthesize 2-3 sentences across the top-scoring items in the
    window. Every claim is footnoted via numbered refs [1]..[N]. If sources
    disagree, both positions are reported (no silent picking).
    Topic is always rendered, even when empty (-> "ingen saker").
    `top_n`: highest-scoring items per CCIR considered (default 12).
    `cap_total`: max input tokens per individual LLM prompt (default 6000).
      The "total" is the aggregate of frame + items in ONE prompt — not a
      cumulative budget across sections. If a CCIR's prompt would exceed
      this, items are dropped from the tail (lowest-score end) until the
      prompt fits; if even 1 item + frame cannot be sent, the section is
      skipped cleanly with a markdown marker. Trims are reported to stderr;
      if any trim happened, bluf.md gets a footer line. Pass --bluf-top N /
      --bluf-cap-total N from CLI.
    """
    from triage_score import llm  # dynamic: write_bluf is the only caller

    ks = kept(verdicts)
    by = {}
    for v in ks:
        by.setdefault((v.get("ccir") or "none").upper(), []).append(v)
    L = [
        f"# InfoTriage · BLUF — {period}",
        f"_{len(ks)} saker syntetisert på tvers av kilder · én blokk per CCIR · "
        f"per-prompt cap {cap_total} (estimerte tokens)_\n",
    ]
    trimmed_total = 0
    for cid, title in CCIR_ORDER:
        L.append(f"## {cid} · {title}")
        grp = by.get(cid, [])
        if not grp:
            L.append("_(ingen saker i vinduet)_\n")
            continue
        # Pre-build items + blocks already sorted high-score first. Trimming
        # pops from the tail pair-wise so ctx_items and ctx_blocks stay aligned.
        top = sorted(grp, key=lambda x: -x.get("score", 0))[:top_n]  # --bluf-top
        ctx_blocks, ctx_items = [], []
        for i, it in enumerate(top, 1):
            ctx_blocks.append(
                f"[{i}] KILDE: {it.get('source','')}\n"
                f"TITTEL: {it.get('title','')}\n"
                f"OPPSUMMERING: {(it.get('summary','') or '')[:500]}\n"
            )
            ctx_items.append(it)
        # Frame template; {N} / {CTX} are filled in once items are settled.
        # Marked `{N}` / `{CTX}` literal via doubled braces so .format plugs them.
        frame_template = (
            f"You are an intelligence analyst writing a BLUF (Bottom Line Up "
            f"Front) for the topic '{title}' ({cid}).\n\n"
            f"Recent reports ({{N}} items):\n{{CTX}}\n\n"
            "Instructions:\n"
            "1. Write a 2-3 sentence BLUF in Norwegian summarizing the "
            "overarching developments *across* these reports.\n"
            "2. Cite every claim with bracketed numeric refs, e.g. [1] or "
            "[2][4]. A claim with no citation is wrong.\n"
            "3. CONTRADICTIONS: if sources disagree on facts, attribution, or "
            "intent, you MUST report both positions explicitly. Example: "
            '"Kildene spriker: [1] hevder X, mens [3] oppgir Y." Do NOT '
            "silently pick one and discard the other.\n"
            "4. Output ONLY the BLUF text. No headers, no source list. "
            "If the items don't share one overarching story, write one "
            "sentence per cluster, each still cited with bracketed refs."
        )
        # Per-prompt truncation: drop tail items until prompt ≤ cap_total.
        while (
            len(ctx_blocks) > 1
            and _est_tokens(
                frame_template.format(N=len(ctx_blocks), CTX="".join(ctx_blocks))
            )
            > cap_total
        ):
            ctx_blocks.pop()
            ctx_items.pop()
        # If 1 item + frame still cannot fit, the cap is below useful → skip.
        skipped_for_cap = (
            bool(ctx_blocks)
            and _est_tokens(
                frame_template.format(N=len(ctx_blocks), CTX="".join(ctx_blocks))
            )
            > cap_total
        )
        if skipped_for_cap:
            ctx_blocks, ctx_items = [], []
        dropped = len(top) - len(ctx_items)
        prompt = (
            frame_template.format(N=len(ctx_items), CTX="".join(ctx_blocks))
            if ctx_items
            else None
        )
        if skipped_for_cap:
            trimmed_total += len(top)
            print(
                f"  …{cid} skipped — cap {cap_total} below frame + 1 item "
                f"({len(top)} items not sent)",
                file=sys.stderr,
                flush=True,
            )
        elif dropped:
            trimmed_total += dropped
            print(
                f"  …{cid} trimmed {dropped} item(s) (lowest-score tail) to fit "
                f"{cap_total}-tok cap ({len(ctx_items)}/{len(top)} kept)",
                file=sys.stderr,
                flush=True,
            )
        if not prompt:
            L.append(
                f"_(seksjon hoppet over — cap {cap_total} for lav til å "
                f"kjøre BLUF for {cid}, {len(top)} saker droppet)_\n"
            )
            continue
        try:
            print(
                f"  …generating BLUF for {cid} ({len(ctx_items)} items, "
                f"~{_est_tokens(prompt)} tok)",
                file=sys.stderr,
                flush=True,
            )
            bluf_text = llm(
                [{"role": "user", "content": prompt}], max_tokens=400
            ).strip()
        except Exception as e:
            # Never echo the exception into bluf.md: urllib errors can carry
            # auth headers / paths that contain env vars. Stderr keeps the
            # full detail for the operator; the digest itself is stingy.
            print(
                f"  …BLUF failure for {cid}: {type(e).__name__}: {e}",
                file=sys.stderr,
                flush=True,
            )
            bluf_text = "_(Kunne ikke generere BLUF — sjekk logg for detaljer)_"
        L.append(bluf_text)
        L.append("")
        for i, it in enumerate(ctx_items, 1):
            src = it.get("source", "") or "(ukjent kilde)"
            L.append(
                f"[{i}] **{src}** · [{it.get('title','')}]"
                f"({it.get('url','') or '#'})"
            )
        L.append("")
    if trimmed_total:
        L.append(
            "---\n"
            f"_Trimmet {trimmed_total} elementer for å holde hver LLM-prompt "
            f"innenfor cap {cap_total} estimerte tokens. "
            f"Juster `--bluf-cap-total` for å heve/grense._"
        )
    return "bluf.md", "\n".join(L)


def write_list(verdicts, period):
    strict = sorted(
        [v for v in kept(verdicts) if v.get("score", 0) >= 8], key=lambda x: -x["score"]
    )
    L = [f"# InfoTriage · list (strict 🔥) — {period}", f"\n{len(strict)} viktigste\n"]
    for v in strict:
        f = "🚩 " if v.get("cnr") == "I" else ""
        L.append(
            f"- {f}**[{v['score']}] {v['title']}**  · {v.get('source','')} · {v.get('ccir','')}"
        )
        L.append(f"  - {v.get('why','')} — [les]({v.get('url','')})")
    return "list.md", "\n".join(L)


def main():
    raise SystemExit(
        "digest.py CLI is deprecated; use the brief app event-driven renderer instead."
    )


if __name__ == "__main__":
    main()
