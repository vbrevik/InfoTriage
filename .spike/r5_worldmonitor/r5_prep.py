#!/usr/bin/env python3
"""R5 World Monitor prep — pre-score 20 corpus items + build the comparison brief.

D-03 / D-05: reuse the shared fresh corpus (.spike/items.json, read-only) and the
EXISTING InfoTriage pipeline (score/triage_score.py -> {ccir,cnr,pmesii,tessoc,score,why}
against ccir.md). Exports a World-Monitor-compatible event shape (RESEARCH § R5
Injection Strategy, Option A) so the pre-scored items can be displayed on the COP
globe, and ALSO renders the InfoTriage baseline CCIR brief via the existing
score/digest.py write_bluf() for the head-to-head comparison the R5 verdict needs.

All synthesis/scoring runs on the LOCAL qwen36 model (ADR-004) via the pipeline's
own llm() — the same default endpoint score/triage_score.py uses. No cloud call.
This script only READS .spike/items.json and only WRITES under .spike/r5_worldmonitor/;
it never touches data/verdicts.jsonl or any production state.

Run:
  omlx-ensure-server >/dev/null 2>&1
  python3 .spike/r5_worldmonitor/r5_prep.py
"""
import os
import sys
import json

# --- locate the repo + the existing pipeline (reuse, never re-implement) -------
HERE = os.path.dirname(os.path.abspath(__file__))          # .spike/r5_worldmonitor
SPIKE_DIR = os.path.dirname(HERE)                            # .spike
REPO_ROOT = os.path.dirname(SPIKE_DIR)                       # repo root
SCORE_DIR = os.path.join(REPO_ROOT, "score")
sys.path.insert(0, SCORE_DIR)

from triage_score import llm, score_item, load_dotenv       # existing scorer
from digest import write_bluf                                # existing CCIR brief

ITEMS_PATH = os.path.join(SPIKE_DIR, "items.json")           # shared corpus (read-only)
SCORED_PATH = os.path.join(HERE, "scored_20.json")           # WM-compatible export
BRIEF_PATH = os.path.join(HERE, "baseline_brief.md")         # write_bluf() comparison

N = 20


def health_check():
    """RESEARCH Pitfall 8: confirm the local qwen36 endpoint answers before a long run."""
    try:
        reply = llm([{"role": "user", "content": "Reply with exactly: OK"}], max_tokens=10)
    except Exception as e:
        sys.exit(f"FATAL: local LLM health-check failed ({type(e).__name__}: {e}). "
                 f"Start the local model (omlx-ensure-server) before running R5.")
    if "OK" not in reply.upper():
        sys.exit(f"FATAL: local LLM returned an unexpected health reply: {reply!r}")
    print("  local qwen36 health-check: OK", file=sys.stderr, flush=True)


def select_20(items):
    """Deterministic, source-stratified pick of 20 items from the shared corpus.

    Round-robins across sources (nrk/bbc/tass) so the COP brief comparison spans
    all three languages/regions rather than 20 consecutive same-source items.
    """
    by_src = {}
    for it in items:
        by_src.setdefault(it.get("source", "?"), []).append(it)
    for src in by_src:
        by_src[src].sort(key=lambda x: x.get("id", ""))   # stable order within a source
    order = sorted(by_src)                                  # stable source order
    picked, i = [], 0
    while len(picked) < N and any(i < len(by_src[s]) for s in order):
        for s in order:
            if i < len(by_src[s]) and len(picked) < N:
                picked.append(by_src[s][i])
        i += 1
    return picked[:N]


def severity(v):
    """Map InfoTriage CNR/score onto a WM-style severity bucket for the COP layer."""
    if (v.get("ccir") or "none").lower() == "none":
        return "info"
    if v.get("cnr") == "I":
        return "critical"
    s = v.get("score", 0) or 0
    return "high" if s >= 7 else "medium" if s >= 4 else "low"


def to_wm_event(v):
    """Shape a scored item as a World-Monitor-compatible COP event (RESEARCH Option A).

    Keeps the full InfoTriage scoring at top level (ccir/cnr/score/why + pmesii/tessoc)
    so WM can render it and the qwen36 brief can reference the CCIR tags as context.
    """
    return {
        "id": v.get("id"),
        "title": v.get("title", ""),
        "description": v.get("summary", ""),
        "source": v.get("source", ""),
        "url": v.get("link", ""),
        "lang": v.get("lang", ""),
        "timestamp": v.get("published", ""),
        "category": v.get("ccir", "none"),     # WM event category <- CCIR tier
        "severity": severity(v),
        # InfoTriage scoring (the CCIR taxonomy WM natively lacks)
        "ccir": v.get("ccir", "none"),
        "cnr": v.get("cnr", "none"),
        "pmesii": v.get("pmesii", "none"),
        "tessoc": v.get("tessoc", "none"),
        "score": v.get("score", 0),
        "why": v.get("why", ""),
        "bucket": v.get("bucket", ""),
    }


def prep_20():
    """Score 20 corpus items via the existing pipeline; export WM events + baseline brief."""
    load_dotenv(os.path.join(REPO_ROOT, ".env"))
    health_check()

    items = json.load(open(ITEMS_PATH, encoding="utf-8"))   # read-only
    chosen = select_20(items)
    print(f"  selected {len(chosen)} items from {len(items)} corpus items "
          f"(sources: {sorted({c.get('source') for c in chosen})})",
          file=sys.stderr, flush=True)

    scored = []
    for n, it in enumerate(chosen, 1):
        v = score_item(it)                                  # existing scorer, local qwen36
        scored.append(v)
        print(f"  …scored {n}/{len(chosen)}  {it.get('id')} -> "
              f"{v.get('ccir')}/{v.get('cnr')} (score {v.get('score')})",
              file=sys.stderr, flush=True)

    # 1) WM-compatible event export
    events = [to_wm_event(v) for v in scored]
    with open(SCORED_PATH, "w", encoding="utf-8") as f:
        json.dump(events, f, ensure_ascii=False, indent=2)
    print(f"wrote {SCORED_PATH} ({len(events)} WM events)", file=sys.stderr, flush=True)

    # 2) InfoTriage baseline CCIR brief over the SAME 20 items (write_bluf, local qwen36).
    #    write_bluf reads url/source/title/summary/ccir/score/cnr — score_item output
    #    carries all of these (url comes from the item's `link`).
    verdicts = []
    for v in scored:
        w = dict(v)
        w.setdefault("url", v.get("link", ""))
        verdicts.append(w)
    period = "R5 spike — 20 pre-scored corpus items (write_bluf baseline)"
    _, brief_text = write_bluf(verdicts, period)
    with open(BRIEF_PATH, "w", encoding="utf-8") as f:
        f.write(brief_text + "\n")
    print(f"wrote {BRIEF_PATH} (InfoTriage write_bluf baseline brief)", file=sys.stderr, flush=True)

    return events


if __name__ == "__main__":
    prep_20()
