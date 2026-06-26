#!/usr/bin/env python3
"""R4 Wiki-LLM feasibility spike — cited intel wiki synthesis on local qwen36.

Extends the write_bluf() cite-grounded [N] pattern from score/digest.py into a
wiki-structured prompt (Background, Key Developments, Current Assessment, Open
Questions) with inline bracketed numeric citations and explicit contradiction
reporting. ADR-004 compliant: all synthesis runs on the local qwen36 via llm()
from score/triage_score.py (oMLX :8000/v1) — no cloud.

Usage:
  python3 .spike/r4_wiki/r4_wiki.py                       # STANDING page (NATO set)
  python3 .spike/r4_wiki/r4_wiki.py --on-demand --topic "NATO"   # ON-DEMAND article

Item gathering reuses R3 entity resolution: items mentioning the topic entity are
collected across languages from the spike `entity_links` table (D-03 corpus reuse),
falling back to keyword match over .spike/items.json if R3 / the spike DB is
unavailable. Spike-only, ephemeral — deleted at Plan 07 closeout.
"""
import json, os, sys, re, argparse, urllib.request, urllib.error

# Reuse llm() from score/triage_score.py (ADR-004: local qwen36, oMLX :8000/v1)
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(_REPO_ROOT, "score"))
from triage_score import llm  # noqa: E402

ITEMS_JSON = os.path.join(_REPO_ROOT, ".spike", "items.json")
OUT_DIR = os.path.dirname(os.path.abspath(__file__))

# Spike pgvector DB (R3 entity_links) — same creds/port as r3_link.py
DB = dict(host="localhost", port=22062, dbname="spike", user="spike", password="spike")


# ── Health-check oMLX before first LLM call (RESEARCH Pitfall 8) ─────────────
def _check_omlx():
    base = os.environ.get("LLM_BASE_URL", "http://127.0.0.1:8000/v1")
    model = os.environ.get("LLM_MODEL", "qwen36-ud-4bit")
    key = os.environ.get("LLM_API_KEY", "omlx")
    try:
        req = urllib.request.Request(
            base.rstrip("/") + "/models",
            headers={"Authorization": f"Bearer {key}"})
        with urllib.request.urlopen(req, timeout=15) as r:
            ids = {m["id"] for m in json.load(r).get("data", [])}
    except (urllib.error.URLError, OSError) as e:
        sys.exit(f"[r4_wiki] FATAL: oMLX not reachable at {base} ({e}). "
                 f"Run `omlx-ensure-server` first.")
    if model not in ids:
        sys.exit(f"[r4_wiki] FATAL: model '{model}' not registered on oMLX "
                 f"(have: {sorted(ids)}).")
    print(f"[r4_wiki] oMLX up at {base}; model '{model}' available.", file=sys.stderr)


# ── Item gathering ──────────────────────────────────────────────────────────
def _load_corpus():
    return json.load(open(ITEMS_JSON, encoding="utf-8"))


def gather_via_entity_links(topic):
    """Gather item_ids mentioning the topic entity from the R3 entity_links table
    (across languages). Returns a list of item_ids, or None if the DB/R3 is a no-go."""
    try:
        import psycopg2
    except ImportError:
        print("[r4_wiki] psycopg2 unavailable — falling back to keyword match.",
              file=sys.stderr)
        return None
    try:
        conn = psycopg2.connect(**DB)
    except Exception as e:  # spike DB down / R3 not run
        print(f"[r4_wiki] entity_links DB unreachable ({e}) — keyword fallback.",
              file=sys.stderr)
        return None
    try:
        cur = conn.cursor()
        # Match the topic entity by normalized name, collect all linked items
        # across every source language (D-03 cross-language reuse).
        cur.execute(
            """
            SELECT DISTINCT el.item_id
            FROM entity_links el
            JOIN entities e ON e.id = el.entity_id
            WHERE e.name_norm LIKE %s OR e.name ILIKE %s
            """,
            (f"%{topic.lower().strip()}%", f"%{topic.strip()}%"),
        )
        ids = [r[0] for r in cur.fetchall()]
        # Report language spread for the on-demand cross-language demonstration.
        if ids:
            cur.execute(
                """
                SELECT DISTINCT el.lang
                FROM entity_links el
                JOIN entities e ON e.id = el.entity_id
                WHERE e.name_norm LIKE %s OR e.name ILIKE %s
                """,
                (f"%{topic.lower().strip()}%", f"%{topic.strip()}%"),
            )
            langs = sorted(x[0] for x in cur.fetchall() if x[0])
            print(f"[r4_wiki] entity_links: {len(ids)} items for '{topic}' "
                  f"across langs {langs}.", file=sys.stderr)
        return ids or None
    finally:
        conn.close()


def gather_via_keyword(topic):
    """Fallback: keyword match over the corpus title+summary."""
    corpus = _load_corpus()
    t = topic.lower().strip()
    ids = [it["id"] for it in corpus
           if t in (it.get("title", "") + " " + it.get("summary", "")).lower()]
    print(f"[r4_wiki] keyword match: {len(ids)} items for '{topic}'.",
          file=sys.stderr)
    return ids


def gather_items(topic, prefer_entity_links=True):
    """Return full item dicts for the topic. Tries R3 entity_links first
    (cross-language), falls back to keyword match over items.json."""
    corpus = _load_corpus()
    by_id = {it["id"]: it for it in corpus}
    ids = None
    if prefer_entity_links:
        ids = gather_via_entity_links(topic)
    if not ids:
        ids = gather_via_keyword(topic)
    # Preserve a stable, deterministic order (sorted by item id).
    items = [by_id[i] for i in sorted(set(ids)) if i in by_id]
    return items


# ── Wiki synthesis (extends write_bluf() [N] cite-grounded pattern) ──────────
WIKI_PROMPT_TEMPLATE = """\
You are an intelligence analyst maintaining a structured intel wiki.
Write a comprehensive wiki page for: {topic}

Source items ({n} items):
{context}

Instructions:
1. Write these four structured sections, in this order: ## Bakgrunn,
   ## Sentrale utviklingstrekk, ## Aktuell vurdering, ## Åpne spørsmål.
2. Every factual claim MUST carry a bracketed citation [N] pointing at the
   numbered source items above, e.g. [1] or [2][4]. A claim without a citation
   is wrong. Only cite numbers that exist in the source list (1..{n}).
3. CONTRADICTIONS: if sources disagree on facts, attribution, or intent, you
   MUST report both positions explicitly, e.g. "Kildene spriker: [1] hevder X,
   mens [3] melder Y." Do NOT silently pick one and discard the other.
4. Write in Norwegian. Max 600 words total.
5. Output ONLY the wiki text (the four sections). No preamble, no source list
   (citations are inline).
"""


def generate_wiki(topic, items):
    """Synthesize a cited wiki page for `topic` from `items` on local qwen36.

    Builds a numbered context block (each tagged with its source id), then calls
    llm() with the wiki-structured prompt. Extends write_bluf()'s [N] cite-grounded
    + contradiction-reporting approach from score/digest.py."""
    context_blocks = []
    for i, it in enumerate(items[:10], 1):
        context_blocks.append(
            f"[{i}] KILDE: {it.get('source', '')} (id={it.get('id', '')}, "
            f"lang={it.get('lang', '')})\n"
            f"TITTEL: {it.get('title', '')}\n"
            f"OPPSUMMERING: {(it.get('summary', '') or '')[:400]}\n"
        )
    prompt = WIKI_PROMPT_TEMPLATE.format(
        topic=topic, n=len(context_blocks), context="".join(context_blocks))
    # 1100 tokens lets all four sections (incl. ## Åpne spørsmål) complete; the
    # 600-word prompt cap keeps the page bounded so this is not a runaway budget.
    return llm([{"role": "user", "content": prompt}], max_tokens=1100).strip()


# ── Citation grounding check ────────────────────────────────────────────────
def grounding_check(wiki_text, items):
    """Every bracketed [N] must map to a real source id in `items`.

    Returns (ok, cited_refs, bad_refs, ref_to_id). A cited ref is grounded iff
    1 <= N <= len(items); item N maps to source id items[N-1]['id']."""
    n = len(items)
    cited = sorted({int(m) for m in re.findall(r"\[(\d+)\]", wiki_text)})
    bad = [r for r in cited if r < 1 or r > n]
    ref_to_id = {r: items[r - 1]["id"] for r in cited if 1 <= r <= n}
    return (len(bad) == 0, cited, bad, ref_to_id)


def _emit(topic, items, kind, out_name):
    if len(items) < 5 and kind == "standing":
        sys.exit(f"[r4_wiki] FATAL: standing page needs >=5 items, got "
                 f"{len(items)} for '{topic}'.")
    if not items:
        sys.exit(f"[r4_wiki] FATAL: no corpus items found for '{topic}'.")
    print(f"[r4_wiki] generating {kind} page for '{topic}' from {len(items)} "
          f"items ({', '.join(it['id'] for it in items)})...", file=sys.stderr)
    wiki = generate_wiki(topic, items)

    ok, cited, bad, ref_to_id = grounding_check(wiki, items)

    # Build the saved sample: header + source map + body. The inline source map
    # makes the [N]->id grounding auditable in the saved artifact.
    lines = [f"# Intel-wiki: {topic}", ""]
    lines.append(f"_Syntetisert på lokal qwen36 (oMLX) fra {len(items)} "
                 f"korpus-elementer · {kind} · {len(cited)} [N]-sitater_")
    lines.append("")
    lines.append(wiki)
    lines.append("")
    lines.append("---")
    lines.append("## Kildekart (citation grounding)")
    for i, it in enumerate(items, 1):
        used = "✓ sitert" if i in cited else "· ikke sitert"
        lines.append(f"- [{i}] `{it['id']}` — {it.get('source', '')} "
                     f"({it.get('lang', '')}) — {it.get('title', '')}  _{used}_")
    lines.append("")
    status = "PASS" if ok else "FAIL"
    lines.append(f"**Grounding check: {status}** — citations {cited}; "
                 f"every [N] maps to a real source id: {ok}"
                 + (f"; UNGROUNDED refs {bad}" if bad else ""))

    out_path = os.path.join(OUT_DIR, out_name)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"[r4_wiki] wrote {out_path}", file=sys.stderr)
    print(f"[r4_wiki] grounding: {status} (cited={cited}, "
          f"ref->id={ref_to_id})", file=sys.stderr)
    if not ok:
        sys.exit(f"[r4_wiki] FATAL: grounding check FAILED — ungrounded refs {bad}.")
    return out_path, cited


def main():
    ap = argparse.ArgumentParser(description="R4 Wiki-LLM spike")
    ap.add_argument("--on-demand", action="store_true",
                    help="produce an on-demand article for --topic")
    ap.add_argument("--topic", default="NATO",
                    help="entity/topic to synthesize (default: NATO)")
    args = ap.parse_args()

    _check_omlx()

    if args.on_demand:
        # On-demand: gather cross-language mentions via R3 entity_links.
        items = gather_items(args.topic, prefer_entity_links=True)
        _emit(args.topic, items, "on-demand", "on_demand_article.md")
    else:
        # Standing page: default topic covered by >=5 corpus items (NATO set).
        topic = args.topic
        items = gather_items(topic, prefer_entity_links=True)
        _emit(topic, items, "standing", "standing_page.md")


if __name__ == "__main__":
    main()
