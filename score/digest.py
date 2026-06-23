#!/usr/bin/env python3
"""trimail · SAB / tiered digests, CCIR-driven.

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
import os, sys, re, json, time, argparse, datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(__file__))
from triage_score import score_item, load_dotenv                 # noqa: E402
from fever_triage import fever_key, fever, strip_html             # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
OUT = os.path.join(ROOT, "data", "digests")
STORE = os.path.join(ROOT, "data", "verdicts.jsonl")
OSLO = ZoneInfo("Europe/Oslo")
STOP = set("the a an of to in on for and or at by with from is are as it its this that "
           "i og å en et er på til av for som med det den de har om mot ved".split())

# CCIR display order + titles (must match the ids the model emits from ccir.md)
CCIR_ORDER = [
    ("PIR-1", "Russland / Ukraina"), ("PIR-2", "Nordområdene & Arktis"),
    ("PIR-3", "NATO & europeisk sikkerhet"), ("PIR-4", "Hybrid- & cybertrusler"),
    ("PIR-5", "Stormaktsrivalisering"),     ("PIR-6", "OSINT & etterforskning"),
    ("SIR-1", "Midtøsten & US-Iran"),       ("SIR-2", "Sport — VM 2026 (FIFA)"),
    ("FFIR-1", "Norsk forsvar & sikkerhetspolitikk"), ("FFIR-2", "Norsk politikk & samfunn"),
    ("FFIR-3", "Egen teknologikapabilitet"),
]

# CCIR_ORDER ↔ ccir.md sync guard (see .planning/codebase/CONCERNS.md DRIFT-1).
# Renderer order must equal the count of `- **CODE**` top-level CCIR bullets in ccir.md;
# otherwise the digest silently drops new (or stale) IDs. Explicit raise (not bare
# `assert`) so the guard survives `python3 -O`.
_ccir_md_ids = set(re.findall(r'^\s*-\s+\*\*([A-Z]{3,4}-\d+)\b', open(os.path.join(ROOT, "ccir.md"), encoding="utf-8").read(), re.MULTILINE))
_order_ids = {cid for cid, _ in CCIR_ORDER}
_missing_in_ccir = _order_ids - _ccir_md_ids
_missing_in_order = _ccir_md_ids - _order_ids
if _missing_in_ccir or _missing_in_order:
    parts = []
    if _missing_in_ccir:
        parts.append(f"in CCIR_ORDER but not in ccir.md: {sorted(_missing_in_ccir)}")
    if _missing_in_order:
        parts.append(f"in ccir.md but not in CCIR_ORDER: {sorted(_missing_in_order)}")
    raise AssertionError(f"CCIR drift detected — {'; '.join(parts)}. Fix both to match.")

def oslo_now():
    return datetime.datetime.fromtimestamp(time.time(), OSLO)

def default_cutoff():
    n = oslo_now()
    c = (n - datetime.timedelta(days=1)).replace(hour=16, minute=0, second=0, microsecond=0)
    return c

def stamp(dt):
    return dt.strftime("%Y-%m-%d %H:%M")

def fetch_window(cutoff_epoch, hardcap):
    """Page Fever items (read+unread) backwards by id until older than cutoff."""
    key = fever_key()
    if fever(key, "")["auth"] != 1:
        raise SystemExit("Fever auth failed — check .env creds / API enabled.")
    feeds = {f["id"]: f["title"] for f in fever(key, "feeds").get("feeds", [])}
    items, max_id = [], None
    while len(items) < hardcap:
        resp = fever(key, "items", **({"max_id": max_id} if max_id else {}))
        batch = resp.get("items", [])
        if not batch:
            break
        items += [it for it in batch if it.get("created_on_time", 0) >= cutoff_epoch]
        if min(it.get("created_on_time", 0) for it in batch) < cutoff_epoch or len(batch) < 50:
            break
        max_id = min(int(it["id"]) for it in batch)
    # score
    out = []
    for n, it in enumerate(items, 1):
        v = score_item({"title": it.get("title", ""),
                        "source": feeds.get(it.get("feed_id"), ""),
                        "summary": strip_html(it.get("html", ""))[:500]})
        v.update(id=it["id"], url=it.get("url", ""), t=it.get("created_on_time", 0))
        out.append(v)
        if n % 10 == 0 or n == len(items):
            print(f"  …scored {n}/{len(items)}", file=sys.stderr, flush=True)
    return out

def persist(verdicts):
    os.makedirs(os.path.dirname(STORE), exist_ok=True)
    with open(STORE, "a") as f:
        for v in verdicts:
            f.write(json.dumps(v) + "\n")

def keywords(title):
    return {w for w in re.findall(r"[a-zA-ZæøåÆØÅ0-9]{4,}", (title or "").lower()) if w not in STOP}

def cluster(items):
    """greedy keyword-overlap clustering; returns list of clusters (lead + members)."""
    clusters = []
    for v in sorted(items, key=lambda x: -x.get("score", 0)):
        kw = keywords(v["title"])
        hit = next((c for c in clusters if len(kw & c["kw"]) >= 2), None)
        if hit:
            hit["items"].append(v); hit["kw"] |= kw
        else:
            clusters.append({"kw": kw, "items": [v]})
    return clusters

def line(v, withsrc=""):
    return f"- {v.get('why') or v['title']}{withsrc}  [les]({v.get('url','')})"

# ---- views ---------------------------------------------------------------

def kept(verdicts):
    return [v for v in verdicts if (v.get("ccir") or "none").lower() != "none"]

def write_cluster(verdicts, period):
    ks = kept(verdicts)
    cs = sorted(cluster(ks), key=lambda c: (-max(i.get("score", 0) for i in c["items"]), -len(c["items"])))
    L = [f"# trimail · cluster — {period}", f"\n{len(cs)} saker fra {len(ks)} elementer\n"]
    for c in cs:
        lead = max(c["items"], key=lambda i: i.get("score", 0))
        srcs = sorted({i.get("source", "") for i in c["items"]})
        tag = f"  _({len(c['items'])} kilder: {', '.join(srcs)})_" if len(c["items"]) > 1 else ""
        flag = "🚩 " if any(i.get("cnr") == "I" for i in c["items"]) else ""
        L.append(f"- {flag}**[{lead.get('score')}] {lead['title']}**{tag}  [les]({lead.get('url','')})")
    return "cluster.md", "\n".join(L)

def write_brief(verdicts, period):
    ks = kept(verdicts)
    L = [f"# trimail · SAB — {period}",
         f"_{len(ks)} saker som svarer på CCIR · ~10 min_\n"]
    # CNR CAT I first
    cat1 = sorted([v for v in ks if v.get("cnr") == "I"], key=lambda x: -x.get("score", 0))
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
        cs = sorted(cluster(grp), key=lambda c: -max(i.get("score", 0) for i in c["items"]))
        for c in cs[:6]:
            lead = max(c["items"], key=lambda i: i.get("score", 0))
            srcs = sorted({i.get("source", "") for i in c["items"]})
            extra = f"  _({len(c['items'])} kilder)_" if len(c["items"]) > 1 else ""
            L.append(line(lead, extra))
        L.append("")
    return "brief.md", "\n".join(L)

def write_bluf(verdicts, period, top_n=12):
    """Per-topic BLUF (Bottom Line Up Front) digest.

    For each CCIR, synthesize 2-3 sentences across the top-scoring items in the
    window. Every claim is footnoted via numbered refs [1]..[N]. If sources
    disagree, both positions are reported (no silent picking).
    Topic is always rendered, even when empty (-> "ingen saker").
    `top_n` controls how many highest-scoring items per CCIR enter the LLM
    context window; default 12 (~1500 tokens). Pass --bluf-top N from CLI.
    """
    from triage_score import llm  # dynamic: write_bluf is the only caller
    ks = kept(verdicts)
    by = {}
    for v in ks:
        by.setdefault((v.get("ccir") or "none").upper(), []).append(v)
    L = [f"# trimail · BLUF — {period}",
         f"_{len(ks)} saker syntetisert på tvers av kilder · én blokk per CCIR_\n"]
    for cid, title in CCIR_ORDER:
        L.append(f"## {cid} · {title}")
        grp = by.get(cid, [])
        if not grp:
            L.append("_(ingen saker i vinduet)_\n")
            continue
        top = sorted(grp, key=lambda x: -x.get("score", 0))[:top_n]  # --bluf-top
        ctx = []
        for i, it in enumerate(top, 1):
            ctx.append(f"[{i}] KILDE: {it.get('source','')}\n"
                       f"TITTEL: {it.get('title','')}\n"
                       f"OPPSUMMERING: {(it.get('summary','') or '')[:500]}\n")
        prompt = (
            f"You are an intelligence analyst writing a BLUF (Bottom Line Up "
            f"Front) for the topic '{title}' ({cid}).\n\n"
            f"Recent reports ({len(top)} items):\n" + "\n".join(ctx) + "\n\n"
            "Instructions:\n"
            "1. Write a 2-3 sentence BLUF in Norwegian summarizing the "
            "overarching developments *across* these reports.\n"
            "2. Cite every claim with bracketed numeric refs, e.g. [1] or "
            "[2][4]. A claim with no citation is wrong.\n"
            "3. CONTRADICTIONS: if sources disagree on facts, attribution, or "
            "intent, you MUST report both positions explicitly. Example: "
            "\"Kildene spriker: [1] hevder X, mens [3] oppgir Y.\" Do NOT "
            "silently pick one and discard the other.\n"
            "4. Output ONLY the BLUF text. No headers, no source list. "
            "If the items don't share one overarching story, write one "
            "sentence per cluster, each still cited with bracketed refs."
        )
        try:
            print(f"  …generating BLUF for {cid} ({len(top)} items)",
                  file=sys.stderr, flush=True)
            bluf_text = llm([{"role": "user", "content": prompt}],
                            max_tokens=400).strip()
        except Exception as e:
            # Never echo the exception into bluf.md: urllib errors can carry
            # auth headers / paths that contain env vars. Stderr keeps the
            # full detail for the operator; the digest itself is stingy.
            print(f"  …BLUF failure for {cid}: {type(e).__name__}: {e}",
                  file=sys.stderr, flush=True)
            bluf_text = "_(Kunne ikke generere BLUF — sjekk logg for detaljer)_"
        L.append(bluf_text)
        L.append("")
        for i, it in enumerate(top, 1):
            src = it.get("source", "") or "(ukjent kilde)"
            L.append(f"[{i}] **{src}** · [{it.get('title','')}]"
                     f"({it.get('url','') or '#'})")
        L.append("")
    return "bluf.md", "\n".join(L)


def write_list(verdicts, period):
    strict = sorted([v for v in kept(verdicts) if v.get("score", 0) >= 8], key=lambda x: -x["score"])
    L = [f"# trimail · list (strict 🔥) — {period}", f"\n{len(strict)} viktigste\n"]
    for v in strict:
        f = "🚩 " if v.get("cnr") == "I" else ""
        L.append(f"- {f}**[{v['score']}] {v['title']}**  · {v.get('source','')} · {v.get('ccir','')}")
        L.append(f"  - {v.get('why','')} — [les]({v.get('url','')})")
    return "list.md", "\n".join(L)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["all", "brief", "cluster", "list", "bluf"], default="cluster")
    ap.add_argument("--since", help='cutoff "YYYY-MM-DD HH:MM" (Oslo)')
    ap.add_argument("--hours", type=int, help="rolling window instead of yesterday-1600")
    ap.add_argument("--max", type=int, default=400, help="hard cap on items scored")
    ap.add_argument("--bluf-top", type=int, default=12,
                    help="top-N items per CCIR fed to LLM (BLUF mode only); ~1500 tokens at N=12")
    args = ap.parse_args()
    load_dotenv(os.path.join(ROOT, ".env"))

    if args.since:
        cutoff = datetime.datetime.strptime(args.since, "%Y-%m-%d %H:%M").replace(tzinfo=OSLO)
    elif args.hours:
        cutoff = oslo_now() - datetime.timedelta(hours=args.hours)
    else:
        cutoff = default_cutoff()
    period = f"siden {stamp(cutoff)} → {stamp(oslo_now())}"
    print(f"window: {period}", file=sys.stderr)

    verdicts = fetch_window(int(cutoff.timestamp()), args.max)
    persist(verdicts)
    os.makedirs(OUT, exist_ok=True)

    writers = {"brief": write_brief, "cluster": write_cluster, "list": write_list, "bluf": write_bluf}
    chosen = writers if args.mode == "all" else {args.mode: writers[args.mode]}
    for name, fn in chosen.items():
        if name == "bluf":
            fname, text = fn(verdicts, period, top_n=args.bluf_top)
        else:
            fname, text = fn(verdicts, period)
        fpath = os.path.join(OUT, fname)
        tmp = fpath + ".tmp"
        with open(tmp, "w") as f:
            f.write(text + "\n")
        os.replace(tmp, fpath)
        print(f"wrote {fpath}")

if __name__ == "__main__":
    main()
