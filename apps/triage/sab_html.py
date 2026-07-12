#!/usr/bin/env python3
"""InfoTriage · SAB HTML renderer (dual-mode: presentation + scroll).

Reads data/verdicts.jsonl (written by digest.py) and produces a styled
HTML Situational Awareness Brief at data/digests/sab.html with two view
modes togglable in-page:

  • Presentation mode — fullscreen slides, keyboard nav (←→), index overlay
  • Scroll mode      — continuous single-page scroll for reading on screen

Usage:
  python3 score/sab_html.py                  # since yesterday 16:00
  python3 score/sab_html.py --since "2026-06-22 16:00"
  python3 score/sab_html.py --hours 18
  python3 score/sab_html.py --no-bluf        # skip LLM synthesis
"""
import os, sys, json, time, argparse, datetime
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(__file__))

# Import semantic clustering from brief app
try:
    from apps.brief.clustering import (
        EnrichedItem,
        cluster_items_in_memory,
    )

    SEMANTIC_CLUSTERING_AVAILABLE = True
except ImportError:
    SEMANTIC_CLUSTERING_AVAILABLE = False
from triage_score import load_dotenv, llm  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
STORE = os.path.join(ROOT, "data", "verdicts.jsonl")
OUT = os.path.join(ROOT, "data", "digests", "sab.html")
OSLO = ZoneInfo("Europe/Oslo")

CCIR_ORDER = [
    ("PIR-1", "Russland / Ukraina"),
    ("PIR-2", "Nordområdene & Arktis"),
    ("PIR-3", "NATO & europeisk sikkerhet"),
    ("PIR-4", "Hybrid- & cybertrusler"),
    ("PIR-5", "Stormaktsrivalisering"),
    ("PIR-6", "OSINT & etterforskning"),
    ("SIR-1", "Midtøsten & US-Iran"),
    ("SIR-2", "Sport — VM 2026 (FIFA)"),
    ("SIR-3", "NATO-toppmøtet i Ankara"),
    ("FFIR-1", "Norsk forsvar & sikkerhetspolitikk"),
    ("FFIR-2", "Norsk politikk & samfunn"),
    ("FFIR-3", "Egen teknologikapabilitet"),
]

STOP = set(
    "the a an of to in on for and or at by with from is are as it its this that "
    "i og å en et er på til av for som med det den de har om mot ved".split()
)

PMESII_ICONS = {
    "political": "🏛️",
    "military": "⚔️",
    "economic": "💰",
    "social": "👥",
    "information": "📡",
    "infrastructure": "🌉",
}

TESSOC_ICONS = {
    "terror": "💣",
    "espionage": "🕵️",
    "subversion": "🎭",
    "sabotage": "⚡",
    "organized crime": "🏴‍☠️",
}

# Placeholder text shown when a CCIR has no items in the current window
_PLACEHOLDER_BLUF = "Intet nytt å rapportere i perioden."


def oslo_now():
    return datetime.datetime.fromtimestamp(time.time(), OSLO)


def default_cutoff():
    n = oslo_now()
    return (n - datetime.timedelta(days=1)).replace(
        hour=16, minute=0, second=0, microsecond=0
    )


def stamp(dt):
    return dt.strftime("%Y-%m-%d %H:%M")


def load_verdicts(cutoff_epoch):
    if not os.path.exists(STORE):
        return []
    out = []
    for line in open(STORE, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            v = json.loads(line)
        except json.JSONDecodeError:
            continue
        if v.get("t", 0) >= cutoff_epoch:
            out.append(v)
    return out


def parse_opml_sources(opml_path: str | None = None) -> list[str]:
    """Return configured RSS source titles from the OPML feed list.

    Falls back to an empty list if the OPML file is not present.
    """
    if opml_path is None:
        candidates = [
            os.path.join(ROOT, "apps", "opml", "feeds.opml"),
            os.path.join(ROOT, "opml", "feeds.opml"),
            "/app/opml/feeds.opml",
        ]
    else:
        candidates = [opml_path]
    opml_path = None
    for candidate in candidates:
        if os.path.exists(candidate):
            opml_path = candidate
            break
    if not opml_path:
        return []
    try:
        tree = ET.parse(opml_path)
    except ET.ParseError:
        return []
    sources = []
    seen = set()
    for outline in tree.iter("outline"):
        if outline.attrib.get("type") == "rss":
            title = outline.attrib.get("title") or outline.attrib.get("text") or ""
            title = title.strip()
            if title and title not in seen:
                seen.add(title)
                sources.append(title)
    return sources


def aggregate_source_timestamps(verdicts: list[dict]) -> dict[str, int]:
    """Return the latest epoch timestamp per source from verdicts."""
    latest: dict[str, int] = {}
    for v in verdicts:
        source = (v.get("source") or "").strip()
        if not source:
            continue
        t = v.get("t", 0) or 0
        if t > latest.get(source, 0):
            latest[source] = t
    return latest


def render_source_status_card(
    sources: list[str],
    last_by_source: dict[str, int],
    cutoff_epoch: int,
    generated_at: str,
) -> str:
    """Render the floating source-status card in the upper right corner.

    Sources are listed alphabetically. A green checkmark is shown if the
    source provided data within the current window; otherwise a red cross.
    The timestamp shows when the source last provided data.
    """
    if not sources:
        sources = sorted(last_by_source.keys())
    if not sources:
        return ""

    active_count = 0
    rows = []
    for source in sorted(sources, key=lambda s: s.lower()):
        last_ts = last_by_source.get(source)
        if last_ts and last_ts >= cutoff_epoch:
            active_count += 1
            icon = '<span class="source-status ok" aria-label="Hentet">✓</span>'
            ts_text = escape(stamp(datetime.datetime.fromtimestamp(last_ts, OSLO)))
        else:
            icon = '<span class="source-status fail" aria-label="Ikke hentet">✕</span>'
            ts_text = "Ikke hentet"
        rows.append(
            f'<div class="source-row">'
            f"  {icon}"
            f'  <span class="source-name">{escape(source)}</span>'
            f'  <span class="source-ts">{ts_text}</span>'
            f"</div>"
        )

    summary = f"{active_count}/{len(sources)} aktive"
    rows_html = "\n".join(rows)
    return (
        f'<div class="source-status-card collapsed" id="sourceStatusCard">\n'
        f'  <div class="source-status-header" onclick="toggleSourceCard()">\n'
        f'    <span class="source-status-title">📡 Kilder</span>\n'
        f'    <span class="source-status-summary">{escape(summary)}</span>\n'
        f'    <span class="source-status-chevron" id="sourceCardChevron">▼</span>\n'
        f"  </div>\n"
        f'  <div class="source-status-body" id="sourceStatusBody">\n'
        f"    {rows_html}\n"
        f"  </div>\n"
        f"</div>\n"
    )


def keywords(title):
    return {
        w
        for w in __import__("re").findall(
            r"[a-zA-ZæøåÆØÅ0-9]{4,}", (title or "").lower()
        )
        if w not in STOP
    }


def _semantic_cluster(items, threshold=0.75):
    """Semantic clustering using pgvector embeddings.

    Falls back to keyword clustering if embeddings are not available.
    """
    if not SEMANTIC_CLUSTERING_AVAILABLE:
        return _keyword_cluster(items)

    # Build EnrichedItem objects for clustering
    items_by_ccir = {}
    for v in items:
        emb = v.get("embedding")
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
    all_clusters = []
    for cid, items in items_by_ccir.items():
        if not items:
            continue
        clusters = cluster_items_in_memory(items, threshold=threshold)
        for cluster in clusters:
            all_clusters.append({"kw": set(), "items": cluster})

    return all_clusters


def _keyword_cluster(items):
    """Original keyword-based clustering (fallback)."""
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


def _group_by_cluster_idx(items):
    """Group items by pre-computed _cluster_idx metadata (CCIR-scoped).

    Used by the brief app's html_renderer to pass semantic clusters through
    without monkey-patching the cluster function.
    """
    by_cluster = {}
    for item in items:
        cluster_idx = item.get("_cluster_idx", -1)
        if cluster_idx >= 0:
            key = f"{item.get('ccir', 'none')}_{cluster_idx}"
            if key not in by_cluster:
                by_cluster[key] = {"kw": set(), "items": []}
            by_cluster[key]["items"].append(item)
            by_cluster[key]["kw"] |= keywords(item.get("title", ""))
        else:
            by_cluster[f"singleton_{id(item)}"] = {"kw": set(), "items": [item]}

    clusters = list(by_cluster.values())
    for c in clusters:
        if len(c["items"]) > 1:
            lead = max(c["items"], key=lambda i: i.get("score", 0))
            lead["_sources_in_cluster"] = len({i.get("source", "") for i in c["items"]})
    return clusters


def cluster(items):
    """Cluster items using semantic clustering when embeddings are available."""
    # If the caller already computed semantic clusters, use them directly.
    if items and any("_cluster_idx" in item for item in items):
        return _group_by_cluster_idx(items)
    return _semantic_cluster(items)


def kept(verdicts):
    return [v for v in verdicts if (v.get("ccir") or "none").lower() != "none"]


def score_class(score):
    if score >= 8:
        return "hot"
    if score >= 6:
        return "warm"
    return "cool"


def ccir_type(cid):
    if cid.startswith("PIR"):
        return "pir"
    if cid.startswith("SIR"):
        return "sir"
    return "ffir"


def escape(text):
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_item(v):
    score = v.get("score", 0)
    cls = score_class(score)
    why = escape(v.get("why") or v.get("title", ""))
    source = escape(v.get("source", ""))
    url = escape(v.get("url", ""))
    sources_count = v.get("_sources_in_cluster", 0)
    tag = (
        f'<span class="sources-tag">({sources_count} kilder)</span>'
        if sources_count > 1
        else ""
    )
    pmesii = (v.get("pmesii") or "none").lower()
    pmesii_icon = PMESII_ICONS.get(pmesii, "")
    pmesii_span = (
        f'<span class="pmesii-badge" title="PMESII: {escape(pmesii.capitalize())}">{pmesii_icon}</span> '
        if pmesii_icon
        else ""
    )
    tessoc = (v.get("tessoc") or "none").lower()
    tessoc_icon = TESSOC_ICONS.get(tessoc, "")
    tessoc_span = (
        f'<span class="pmesii-badge" title="TESSOC: {escape(tessoc.capitalize())}">{tessoc_icon}</span> '
        if tessoc_icon
        else ""
    )
    return (
        f'<a class="item" href="{url}">'
        f'<span class="item-score {cls}">{score}</span>'
        f'<div class="item-body">'
        f'<div class="item-why">{pmesii_span}{tessoc_span}{why}</div>'
        f'<div class="item-source">{source}{(" · " + tag) if tag else ""}</div>'
        f"</div>"
        f'<span class="item-link">les →</span>'
        f"</a>\n"
    )


def render_filtered_item(v):
    """Render a skipped/non-CCIR item for the 'Filtrert ut' slide."""
    score = v.get("score", 0)
    title = escape(v.get("title", ""))
    why = escape(v.get("why", ""))
    source = escape(v.get("source", ""))
    url = escape(v.get("url", ""))
    return (
        f'<a class="item filtered" href="{url}">'
        f'<span class="item-score cool">{score}</span>'
        f'<div class="item-body">'
        f'<div class="item-why">{title}</div>'
        f'<div class="item-source">{source}{" · " if source and why else ""}{why}</div>'
        f"</div>"
        f'<span class="item-link">les →</span>'
        f"</a>\n"
    )


def render_filtered_section(items):
    """Render a slide showing items that were filtered out (ccir='none')."""
    if not items:
        return ""
    items_html = "".join(render_filtered_item(v) for v in items[:30])
    return (
        f'<section class="slide" id="filtered">\n'
        f'  <div class="slide-inner">\n'
        f'    <div class="slide-header">\n'
        f'      <div class="slide-header-left">\n'
        f'        <span class="ccir-badge" style="background:var(--text-dim);color:var(--bg);">FILTER</span>\n'
        f'        <span class="ccir-title">Filtrert ut</span>\n'
        f"      </div>\n"
        f'      <span class="ccir-count">{len(items)} saker · vist: {min(len(items), 30)}</span>\n'
        f"    </div>\n"
        f'    <div class="bluf">Saker vurdert som ikke CCIR-relevante i perioden.</div>\n'
        f'    <div class="items">{items_html}</div>\n'
        f"  </div>\n"
        f"</section>\n"
    )


def render_bluf_section(blufs_by_ccir: dict[str, str], exec_bluf: str = "") -> str:
    """Render a slide aggregating all CCIR BLUFs in one place."""
    rows = []
    for cid, title in CCIR_ORDER:
        bluf = escape(blufs_by_ccir.get(cid, ""))
        c_type = ccir_type(cid)
        rows.append(
            f'<div class="bluf-row collapsed">\n'
            f'  <div class="bluf-row-header" role="button" tabindex="0" aria-expanded="false" onclick="toggleBlufRow(this)">\n'
            f"    <div>\n"
            f'      <span class="ccir-badge {c_type}">{cid}</span>\n'
            f'      <span class="ccir-title-small">{escape(title)}</span>\n'
            f"    </div>\n"
            f'    <span class="bluf-chevron">▼</span>\n'
            f"  </div>\n"
            f'  <div class="bluf-row-body">\n'
            f'    <div class="bluf-text">{bluf}</div>\n'
            f"  </div>\n"
            f"</div>"
        )
    rows_html = "\n      ".join(rows)
    exec_html = ""
    if exec_bluf:
        exec_html = (
            f'<div class="exec-bluf-box">\n'
            f'  <div class="exec-bluf-title">EXECUTIVE SUMMARY</div>\n'
            f'  <div class="bluf-text">{escape(exec_bluf)}</div>\n'
            f"</div>\n"
        )
    return (
        f'<section class="slide" id="blufs">\n'
        f'  <div class="slide-inner">\n'
        f'    <div class="slide-header">\n'
        f'      <div class="slide-header-left">\n'
        f'        <span class="ccir-badge" style="background:var(--purple);color:#fff;">BLUF</span>\n'
        f'        <span class="ccir-title">Alle BLUF</span>\n'
        f"      </div>\n"
        f'      <button type="button" class="copy-blufs-btn" id="copyBlufsBtn" onclick="copyAllBlufs()" title="Kopier alle BLUFs til utklippstavlen" aria-label="Kopier alle BLUFs til utklippstavlen">\n'
        f'        <span class="copy-icon">📋</span>\n'
        f'        <span class="copy-label">Kopier alle BLUFs</span>\n'
        f"      </button>\n"
        f"    </div>\n"
        f"    {exec_html}"
        f'    <div class="bluf-list" id="blufsList">\n'
        f"      {rows_html}\n"
        f"    </div>\n"
        f"  </div>\n"
        f"</section>\n"
    )


def generate_exec_summary(blufs_by_ccir: dict[str, str]) -> str:
    """Generate a short executive summary from all per-CCIR BLUFs."""
    valid_blufs = [
        f"[{cid}] {bluf}"
        for cid, bluf in blufs_by_ccir.items()
        if bluf and not bluf.startswith("_(") and bluf != _PLACEHOLDER_BLUF
    ]
    if not valid_blufs:
        return "Ingen signifikant aktivitet å rapportere for perioden."

    prompt = (
        "Du er en senior etterretningsoffiser som skriver en kort overordnet "
        "oppsummering (executive summary) på norsk.\n\n"
        "Her er de gjeldende BLUF-ene per CCIR:\n\n" + "\n\n".join(valid_blufs) + "\n\n"
        "Instruksjoner:\n"
        "1. Skriv 1-2 setninger som oppsummerer de viktigste overordnede "
        "temaene eller trusselbildet på tvers av CCIR-ene.\n"
        "2. Fokuser på det mest kritiske. Ikke list opp hver CCIR.\n"
        "3. Returner KUN oppsummeringsteksten. Ingen overskrifter, ingen intro."
    )
    try:
        print("  …Executive Summary BLUF", file=sys.stderr, flush=True)
        return llm([{"role": "user", "content": prompt}], max_tokens=150).strip()
    except Exception as e:
        print(
            f"  …Exec BLUF failure: {type(e).__name__}: {e}",
            file=sys.stderr,
            flush=True,
        )
        return (
            "_(Kunne ikke generere overordnet oppsummering — sjekk logg for detaljer)_"
        )


def generate_bluf(cid, title, items, top_n=12):
    top = sorted(items, key=lambda x: -x.get("score", 0))[:top_n]
    ctx = []
    for i, it in enumerate(top, 1):
        ctx.append(
            f"[{i}] KILDE: {it.get('source', '')}\n"
            f"TITTEL: {it.get('title', '')}\n"
            f"OPPSUMMERING: {(it.get('summary', '') or '')[:500]}\n"
        )
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
        '"Kildene spriker: [1] hevder X, mens [3] oppgir Y." Do NOT '
        "silently pick one and discard the other.\n"
        "4. Output ONLY the BLUF text. No headers, no source list. "
        "If the items don't share one overarching story, write one "
        "sentence per cluster, each still cited with bracketed refs."
    )
    try:
        print(f"  …BLUF for {cid} ({len(top)} items)", file=sys.stderr, flush=True)
        return llm([{"role": "user", "content": prompt}], max_tokens=400).strip()
    except Exception as e:
        print(
            f"  …BLUF failure for {cid}: {type(e).__name__}: {e}",
            file=sys.stderr,
            flush=True,
        )
        return "_(Kunne ikke generere BLUF — sjekk logg for detaljer)_"


def render_section(cid, title, items, total_scanned, bluf_text=""):
    c_type = ccir_type(cid)
    clusters = cluster(items)
    cluster_count = len(clusters)

    for c in clusters:
        lead = max(c["items"], key=lambda i: i.get("score", 0))
        if len(c["items"]) > 1:
            lead["_sources_in_cluster"] = len({i.get("source", "") for i in c["items"]})

    items_html = ""
    for c in sorted(
        clusters, key=lambda c: -max(i.get("score", 0) for i in c["items"])
    )[:6]:
        lead = max(c["items"], key=lambda i: i.get("score", 0))
        items_html += render_item(lead)

    bluf_html = f'<div class="bluf">{escape(bluf_text)}</div>' if bluf_text else ""

    all_srcs = sorted({escape(v.get("source", "")) for v in items if v.get("source")})
    src_footer = ""
    if all_srcs:
        src_list = " · ".join(f"<a href='#'>{s}</a>" for s in all_srcs[:8])
        src_footer = f'<div class="section-sources">Kilder: {src_list}</div>'

    scores = [v.get("score", 0) for v in items]
    max_score = max(scores) if scores else 0

    return (
        f'<section class="slide" id="{cid.lower()}">\n'
        f'  <div class="slide-inner">\n'
        f'    <div class="slide-header">\n'
        f'      <div class="slide-header-left">\n'
        f'        <span class="ccir-badge {c_type}">{cid}</span>\n'
        f'        <span class="ccir-title">{escape(title)}</span>\n'
        f"      </div>\n"
        f'      <span class="ccir-count">{len(items)} saker · {cluster_count} klynger · max {max_score}</span>\n'
        f"    </div>\n"
        f"    {bluf_html}\n"
        f"    {src_footer}\n"
        f'    <div class="items">{items_html}</div>\n'
        f"  </div>\n"
        f"</section>\n"
    )


def render_cnr(items):
    cat1 = sorted(
        [v for v in items if v.get("cnr") == "I"], key=lambda x: -x.get("score", 0)
    )
    if not cat1:
        return ""

    clusters = cluster(cat1)
    alerts = ""
    for c in clusters:
        lead = max(c["items"], key=lambda i: i.get("score", 0))
        srcs = sorted({i.get("source", "") for i in c["items"]})
        src_html = " · ".join(f"<a href='#'>{escape(s)}</a>" for s in srcs[:5])
        count = len(c["items"])
        extra = f" · {count} kilder" if count > 1 else ""
        alerts += (
            f'<div class="alert-item">'
            f'<div class="alert-title">{escape(lead.get("title", ""))}</div>'
            f'<div class="alert-sources">{src_html}{extra}</div>'
            f"</div>\n"
        )

    return (
        f'<section class="slide" id="cnr">\n'
        f'  <div class="slide-inner">\n'
        f'    <div class="cnr-alert">\n'
        f"      <h2>🚩 CNR — varsle straks</h2>\n"
        f"      {alerts}\n"
        f"    </div>\n"
        f"  </div>\n"
        f"</section>\n"
    )


def render_nav(verdicts):
    by = {}
    for v in kept(verdicts):
        cid = (v.get("ccir") or "none").upper()
        by.setdefault(cid, []).append(v)

    rows = ""
    for cid, title in CCIR_ORDER:
        count = len(by.get(cid, []))
        if count == 0:
            continue
        dot = "active"
        c_type = ccir_type(cid)
        rows += (
            f'<li><span class="nav-dot {dot}"></span>'
            f'<span class="nav-id {c_type}">{cid}</span>'
            f'<span class="nav-title">{escape(title)}</span>'
            f'<span class="nav-count">{count}</span></li>\n'
        )
    return rows


def build_html(verdicts, period, with_bluf=True, generated_at=None, cutoff_epoch=None):
    total = len(verdicts)
    ks = kept(verdicts)
    ccir_count = len(ks)
    filtered = total - ccir_count
    rate = f"{round(ccir_count / total * 100)}%" if total > 0 else "0%"

    by = {}
    for v in ks:
        by.setdefault((v.get("ccir") or "none").upper(), []).append(v)

    gen_ts = generated_at or stamp(oslo_now())
    if cutoff_epoch is None:
        cutoff_epoch = int(default_cutoff().timestamp())

    # Latest data fetch time from verdicts
    latest_fetch_ts = ""
    if verdicts:
        max_t = max(v.get("t", 0) for v in verdicts)
        if max_t > 0:
            latest_fetch_ts = stamp(datetime.datetime.fromtimestamp(max_t, OSLO))
    fetch_line = (
        f"<span>📥 Sist hentet: {escape(latest_fetch_ts)}</span>"
        if latest_fetch_ts
        else ""
    )

    # Build source status card (uses all configured OPML sources)
    opml_sources = parse_opml_sources()
    last_by_source = aggregate_source_timestamps(verdicts)
    source_status_card = render_source_status_card(
        opml_sources, last_by_source, cutoff_epoch, gen_ts
    )

    # Build slide index and slides
    has_cnr = any(v.get("cnr") == "I" for v in ks)
    slide_index = []
    slide_num = 0

    # Slide 0: Title
    slide_num += 1
    slide_index.append((slide_num, "title", "InfoTriage · SAB", ""))

    # Slide 1: CNR (if any)
    cnr_html = ""
    if has_cnr:
        slide_num += 1
        cat1_count = len([v for v in ks if v.get("cnr") == "I"])
        slide_index.append(
            (slide_num, "cnr", "🚩 CNR — varsle straks", f"{cat1_count} saker")
        )
        cnr_html = render_cnr(ks)

    # Generate BLUFs once for both per-CCIR sections and the aggregate BLUF slide
    blufs_by_ccir: dict[str, str] = {}
    for cid, title in CCIR_ORDER:
        grp = by.get(cid, [])
        if with_bluf and grp:
            blufs_by_ccir[cid] = generate_bluf(cid, title, grp)
        elif with_bluf:
            blufs_by_ccir[cid] = _PLACEHOLDER_BLUF
        else:
            blufs_by_ccir[cid] = ""

    # CCIR slides (only render if there are items in the current window)
    sections = ""
    visible_ccirs = []
    for cid, title in CCIR_ORDER:
        grp = by.get(cid, [])
        if not grp:
            continue
        visible_ccirs.append((cid, title))
        bluf_text = blufs_by_ccir.get(cid, "")
        section_html = render_section(cid, title, grp, total, bluf_text=bluf_text)
        slide_num += 1
        c_type = ccir_type(cid)
        slide_index.append((slide_num, c_type, f"{cid} · {title}", f"{len(grp)} saker"))
        sections += section_html

    # Filtered / non-CCIR slide
    filtered_items = [
        v for v in verdicts if (v.get("ccir") or "none").lower() == "none"
    ]
    filtered_html = render_filtered_section(filtered_items)
    if filtered_html:
        slide_num += 1
        slide_index.append(
            (slide_num, "filtered", "Filtrert ut", f"{len(filtered_items)} saker")
        )
        sections += filtered_html

    # Aggregate BLUF slide (below all CCIR/CNR/SIR/PIR sections)
    if with_bluf:
        slide_num += 1
        exec_bluf = generate_exec_summary(blufs_by_ccir)
        slide_index.append((slide_num, "blufs", "Alle BLUF", f"{len(CCIR_ORDER)} CCIR"))
        sections += render_bluf_section(blufs_by_ccir, exec_bluf=exec_bluf)

    # Stats slide
    slide_num += 1
    slide_index.append((slide_num, "stats", "📊 Statistikk", ""))
    total_slides = slide_num

    # Build index HTML
    index_items = ""
    for num, typ, label, sub in slide_index:
        dot_class = (
            f"idx-{typ}"
            if typ in ("pir", "sir", "ffir", "cnr", "stats", "filtered")
            else "idx-gray"
        )
        sub_html = f'<span class="idx-sub">{escape(sub)}</span>' if sub else ""
        index_items += (
            f'<div class="idx-item" onclick="goToSlide({num - 1})">'
            f'<span class="idx-dot {dot_class}"></span>'
            f'<span class="idx-label">{escape(label)}</span>'
            f"{sub_html}"
            f'<span class="idx-num">{num}</span>'
            f"</div>\n"
        )

    nav_html = render_nav(verdicts)

    # Stats slide CCIR list (only CCIRs with items)
    stats_ccir_list_html = ""
    for cid, title in CCIR_ORDER:
        count = len(by.get(cid, []))
        if count == 0:
            continue
        c_type = ccir_type(cid)
        max_score = max((v.get("score", 0) for v in by.get(cid, [])), default=0)
        bar_width = min(100, max_score * 10)
        stats_ccir_list_html += (
            f"<li>"
            f'  <span class="sid {c_type}">{cid}</span>'
            f'  <span class="stitle">{escape(title)}</span>'
            f'  <span class="scount">{count}</span>'
            f'  <span class="sbar"><span class="sbar-fill" style="width:{bar_width}%;background:var(--{c_type})"></span></span>'
            f"</li>\n"
        )

    # PMESII domain distribution
    from collections import Counter

    pmesii_counts = Counter((v.get("pmesii") or "none").lower() for v in ks)
    pmesii_domains = [
        "political",
        "military",
        "economic",
        "social",
        "information",
        "infrastructure",
    ]
    max_pmesii = max((pmesii_counts.get(d, 0) for d in pmesii_domains), default=1) or 1
    pmesii_cards = ""
    for domain in pmesii_domains:
        cnt = pmesii_counts.get(domain, 0)
        if cnt == 0:
            continue
        icon = PMESII_ICONS.get(domain, "")
        pct = round(cnt / max_pmesii * 100)
        color_map = {
            "political": "var(--blue)",
            "military": "var(--red)",
            "economic": "var(--amber)",
            "social": "var(--purple)",
            "information": "var(--cyan)",
            "infrastructure": "var(--green)",
        }
        color = color_map.get(domain, "var(--text-dim)")
        pmesii_cards += (
            f'<div class="pmesii-dist-card">'
            f'<span class="p-icon">{icon}</span>'
            f'<span class="p-name">{domain}</span>'
            f'<span class="p-count">{cnt}</span>'
            f'<span class="p-bar"><span class="p-bar-fill" style="width:{pct}%;background:{color}"></span></span>'
            f"</div>\n"
        )
    pmesii_dist_html = (
        f'<div class="pmesii-dist">{pmesii_cards}</div>' if pmesii_cards else ""
    )

    # TESSOC threat-actor distribution
    tessoc_counts = Counter((v.get("tessoc") or "none").lower() for v in ks)
    tessoc_vars = ["terror", "espionage", "subversion", "sabotage", "organized crime"]
    max_tessoc = max((tessoc_counts.get(d, 0) for d in tessoc_vars), default=1) or 1
    tessoc_cards = ""
    for var in tessoc_vars:
        cnt = tessoc_counts.get(var, 0)
        if cnt == 0:
            continue
        icon = TESSOC_ICONS.get(var, "")
        pct = round(cnt / max_tessoc * 100)
        tessoc_color_map = {
            "terror": "var(--red)",
            "espionage": "var(--blue)",
            "subversion": "var(--purple)",
            "sabotage": "var(--amber)",
            "organized crime": "var(--green)",
        }
        color = tessoc_color_map.get(var, "var(--text-dim)")
        tessoc_cards += (
            f'<div class="pmesii-dist-card">'
            f'<span class="p-icon">{icon}</span>'
            f'<span class="p-name">{var}</span>'
            f'<span class="p-count">{cnt}</span>'
            f'<span class="p-bar"><span class="p-bar-fill" style="width:{pct}%;background:{color}"></span></span>'
            f"</div>\n"
        )
    tessoc_dist_html = (
        f'<div class="pmesii-dist">{tessoc_cards}</div>' if tessoc_cards else ""
    )

    return HTML_TEMPLATE.format(
        period=escape(period),
        generated_at=escape(gen_ts),
        fetch_line=fetch_line,
        scanned=total,
        ccir_hits=ccir_count,
        filtered=filtered,
        rate=rate,
        total_slides=total_slides,
        cnr=cnr_html,
        sections=sections,
        index_items=index_items,
        nav=nav_html,
        stats_ccir_list=stats_ccir_list_html,
        pmesii_dist=pmesii_dist_html,
        tessoc_dist=tessoc_dist_html,
        source_status_card=source_status_card,
    )


HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="no">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>InfoTriage · SAB — {period}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,600;1,8..60,400&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  :root {{
    --bg: #0d1117;
    --bg-card: #161b22;
    --bg-hover: #1c2129;
    --border: #21262d;
    --border-accent: #30363d;
    --text: #c9d1d9;
    --text-dim: #8b949e;
    --text-bright: #f0f6fc;
    --red: #f85149;
    --red-dim: #3d1214;
    --red-glow: #f8514922;
    --amber: #d29922;
    --amber-dim: #2d1f04;
    --green: #3fb950;
    --green-dim: #0d2818;
    --blue: #58a6ff;
    --blue-dim: #0d1d31;
    --cyan: #39d2c0;
    --purple: #bc8cff;
    --mono: 'JetBrains Mono', monospace;
    --serif: 'Source Serif 4', Georgia, serif;
    --sans: 'Inter', -apple-system, sans-serif;
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  html {{ scroll-behavior: smooth; scroll-snap-type: y mandatory; }}
  body {{
    background: var(--bg);
    color: var(--text);
    font-family: var(--serif);
    font-size: 15px;
    line-height: 1.7;
    overflow-x: hidden;
  }}

  /* ═══ SLIDES ═══ */
  .slide {{
    width: 100vw;
    min-height: 100vh;
    scroll-snap-align: start;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 60px 80px;
    position: relative;
  }}
  .slide-inner {{
    width: 100%;
    max-width: 1100px;
    opacity: 0;
    transform: translateY(20px);
    transition: opacity 0.5s ease, transform 0.5s ease;
  }}
  .slide.visible .slide-inner {{
    opacity: 1;
    transform: translateY(0);
  }}

  /* ═══ TITLE SLIDE ═══ */
  .title-slide {{
    flex-direction: column;
    text-align: center;
    gap: 24px;
  }}
  .title-slide h1 {{
    font-family: var(--sans);
    font-size: 48px;
    font-weight: 700;
    color: var(--text-bright);
    letter-spacing: -1px;
  }}
  .title-slide .subtitle {{
    font-family: var(--mono);
    font-size: 14px;
    color: var(--text-dim);
    display: flex;
    gap: 24px;
    justify-content: center;
    flex-wrap: wrap;
  }}
  .title-slide .subtitle span {{ display: flex; align-items: center; gap: 6px; }}
  .title-slide .stats-row {{
    display: flex;
    gap: 32px;
    justify-content: center;
    margin-top: 32px;
  }}
  .title-slide .stat {{
    text-align: center;
  }}
  .title-slide .stat-val {{
    font-family: var(--mono);
    font-size: 42px;
    font-weight: 700;
    line-height: 1;
  }}
  .title-slide .stat-val.red {{ color: var(--red); }}
  .title-slide .stat-val.green {{ color: var(--green); }}
  .title-slide .stat-val.amber {{ color: var(--amber); }}
  .title-slide .stat-val.blue {{ color: var(--blue); }}
  .title-slide .stat-lbl {{
    font-family: var(--mono);
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: var(--text-dim);
    margin-top: 6px;
  }}
  .title-slide .classification {{
    background: var(--red);
    color: #fff;
    font-family: var(--mono);
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 2px;
    padding: 4px 16px;
    margin-top: 16px;
  }}

  /* ═══ SLIDE HEADER ═══ */
  .slide-header {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 24px;
    padding-bottom: 16px;
    border-bottom: 1px solid var(--border);
  }}
  .slide-header-left {{
    display: flex;
    align-items: center;
    gap: 14px;
  }}
  .ccir-badge {{
    font-family: var(--mono);
    font-size: 13px;
    font-weight: 700;
    padding: 4px 12px;
    border-radius: 2px;
    letter-spacing: 0.5px;
    white-space: nowrap;
  }}
  .ccir-badge.pir {{ background: var(--blue-dim); color: var(--blue); border: 1px solid #58a6ff33; }}
  .ccir-badge.sir {{ background: var(--amber-dim); color: var(--amber); border: 1px solid #d2992233; }}
  .ccir-badge.ffir {{ background: var(--green-dim); color: var(--green); border: 1px solid #3fb95033; }}
  .ccir-title {{
    font-family: var(--sans);
    font-size: 20px;
    font-weight: 600;
    color: var(--text-bright);
  }}
  .ccir-count {{
    font-family: var(--mono);
    font-size: 11px;
    color: var(--text-dim);
  }}

  /* ═══ CNR ALERT ═══ */
  .cnr-alert {{
    background: var(--red-dim);
    border: 2px solid var(--red);
    border-left: 6px solid var(--red);
    padding: 32px 40px;
    border-radius: 4px;
    animation: alert-pulse 3s ease-in-out infinite;
  }}
  @keyframes alert-pulse {{
    0%, 100% {{ box-shadow: 0 0 0 0 var(--red-glow); }}
    50% {{ box-shadow: 0 0 40px 8px var(--red-glow); }}
  }}
  .cnr-alert h2 {{
    font-family: var(--mono);
    font-size: 18px;
    font-weight: 700;
    color: var(--red);
    text-transform: uppercase;
    letter-spacing: 1.5px;
    margin-bottom: 20px;
  }}
  .cnr-alert .alert-item {{ padding: 14px 0; border-bottom: 1px solid #ffffff0a; }}
  .cnr-alert .alert-item:last-child {{ border-bottom: none; }}
  .cnr-alert .alert-title {{
    font-family: var(--serif);
    font-size: 20px;
    font-weight: 600;
    color: var(--text-bright);
    margin-bottom: 4px;
  }}
  .cnr-alert .alert-sources {{
    font-family: var(--mono);
    font-size: 11px;
    color: var(--text-dim);
    margin-top: 6px;
  }}
  .cnr-alert .alert-sources a {{ color: var(--blue); text-decoration: none; }}

  /* ═══ BLUF ═══ */
  .bluf {{
    font-size: 17px;
    line-height: 1.8;
    color: var(--text);
    margin-bottom: 20px;
    padding-left: 20px;
    border-left: 3px solid var(--border-accent);
  }}
  .section-sources {{
    font-family: var(--mono);
    font-size: 11px;
    color: var(--text-dim);
    margin-bottom: 16px;
    padding-left: 20px;
  }}
  .section-sources a {{ color: var(--blue); text-decoration: none; }}

  /* ═══ ITEMS ═══ */
  .items {{ display: flex; flex-direction: column; gap: 8px; }}
  .item {{
    display: grid;
    grid-template-columns: 36px 1fr auto;
    gap: 14px;
    align-items: start;
    padding: 14px 16px;
    border-radius: 4px;
    transition: background 0.15s;
    text-decoration: none;
    color: inherit;
  }}
  .item:hover {{ background: var(--bg-hover); }}
  .item-score {{
    font-family: var(--mono);
    font-size: 14px;
    font-weight: 700;
    width: 36px;
    height: 30px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 3px;
  }}
  .item-score.hot {{ background: var(--red-dim); color: var(--red); }}
  .item-score.warm {{ background: var(--amber-dim); color: var(--amber); }}
  .item-score.cool {{ background: var(--blue-dim); color: var(--blue); }}
  .item-body {{ min-width: 0; }}
  .item-why {{
    font-family: var(--serif);
    font-size: 16px;
    color: var(--text-bright);
    line-height: 1.5;
  }}
  .item-source {{ font-family: var(--mono); font-size: 11px; color: var(--text-dim); margin-top: 4px; }}
  .item-source .sources-tag {{ color: var(--cyan); }}
  .item-link {{
    font-family: var(--mono);
    font-size: 11px;
    color: var(--blue);
    text-decoration: none;
    opacity: 0;
    transition: opacity 0.15s;
    white-space: nowrap;
  }}
  .item:hover .item-link {{ opacity: 1; }}
  .item.filtered {{ opacity: 0.7; }}
  .item.filtered:hover {{ opacity: 1; }}

  /* ═══ AGGREGATE BLUF SLIDE ═══ */
  .bluf-list {{ display: flex; flex-direction: column; gap: 8px; }}
  .bluf-row {{
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-left: 4px solid var(--border-accent);
    border-radius: 4px;
  }}
  .bluf-row-header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 14px 18px;
    cursor: pointer;
    user-select: none;
    transition: background 0.15s;
  }}
  .bluf-row-header:hover {{
    background: var(--bg-hover);
  }}
  .bluf-row-header > div {{
    display: flex;
    align-items: center;
  }}
  .bluf-chevron {{
    font-size: 10px;
    color: var(--text-dim);
    transition: transform 0.2s ease;
  }}
  .bluf-row.collapsed .bluf-chevron {{
    transform: rotate(-90deg);
  }}
  .bluf-row-body {{
    padding: 0 18px 16px 18px;
  }}
  .bluf-row.collapsed .bluf-row-body {{
    display: none;
  }}
  .bluf-row .ccir-title-small {{
    font-family: var(--sans);
    font-size: 15px;
    font-weight: 600;
    color: var(--text-bright);
    margin-left: 10px;
  }}
  .bluf-row .bluf-text {{
    font-size: 15px;
    line-height: 1.7;
    color: var(--text);
    padding-left: 0;
    border-left: none;
  }}

  /* ═══ COPY BLUFS BUTTON ═══ */
  .copy-blufs-btn {{
    display: inline-flex;
    align-items: center;
    gap: 8px;
    background: var(--bg-card);
    border: 1px solid var(--border-accent);
    color: var(--text);
    font-family: var(--mono);
    font-size: 12px;
    padding: 8px 14px;
    border-radius: 4px;
    cursor: pointer;
    transition: all 0.15s ease;
    user-select: none;
  }}
  .copy-blufs-btn:hover {{
    background: var(--bg-hover);
    border-color: var(--blue);
    color: var(--text-bright);
  }}
  .copy-blufs-btn:active {{
    background: var(--border);
  }}
  .copy-blufs-btn.copied {{
    background: var(--green-dim);
    border-color: var(--green);
    color: var(--green);
  }}
  .copy-blufs-btn .copy-icon {{
    font-size: 14px;
  }}
  .copy-blufs-btn .copy-label {{
    white-space: nowrap;
  }}

  /* ═══ EXECUTIVE SUMMARY ═══ */
  .exec-bluf-box {{
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-left: 4px solid var(--red);
    padding: 16px 18px;
    border-radius: 4px;
    margin-bottom: 24px;
  }}
  .exec-bluf-box .exec-bluf-title {{
    font-family: var(--mono);
    font-size: 11px;
    font-weight: 700;
    color: var(--red);
    letter-spacing: 1px;
    margin-bottom: 8px;
  }}
  .exec-bluf-box .bluf-text {{
    font-size: 16px;
    line-height: 1.8;
    color: var(--text-bright);
    padding-left: 0;
    border-left: none;
  }}

  /* ═══ STATS SLIDE ═══ */
  .stats-slide-grid {{
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 16px;
    margin-top: 24px;
  }}
  .stats-slide-card {{
    background: var(--bg-card);
    border: 1px solid var(--border);
    padding: 20px;
    border-radius: 4px;
    text-align: center;
  }}
  .stats-slide-card .val {{
    font-family: var(--mono);
    font-size: 32px;
    font-weight: 700;
    color: var(--text-bright);
    line-height: 1;
  }}
  .stats-slide-card .lbl {{
    font-family: var(--mono);
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: var(--text-dim);
    margin-top: 6px;
  }}
  .stats-ccir-list {{ list-style: none; margin-top: 24px; }}
  .stats-ccir-list li {{
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 12px;
    border-bottom: 1px solid var(--border);
    font-size: 14px;
  }}
  .stats-ccir-list .sid {{ font-family: var(--mono); font-size: 12px; font-weight: 600; width: 56px; }}
  .stats-ccir-list .sid.pir {{ color: var(--blue); }}
  .stats-ccir-list .sid.sir {{ color: var(--amber); }}
  .stats-ccir-list .sid.ffir {{ color: var(--green); }}
  .stats-ccir-list .stitle {{ color: var(--text-dim); flex: 1; }}
  .stats-ccir-list .scount {{ font-family: var(--mono); font-size: 12px; color: var(--text-bright); }}
  .stats-ccir-list .sbar {{ width: 80px; height: 4px; background: var(--border); border-radius: 2px; overflow: hidden; }}
  .stats-ccir-list .sbar-fill {{ height: 100%; border-radius: 2px; }}

  /* ═══ CONTROLS ═══ */
  .controls {{
    position: fixed;
    bottom: 24px;
    left: 50%;
    transform: translateX(-50%);
    display: flex;
    align-items: center;
    gap: 16px;
    background: var(--bg-card);
    border: 1px solid var(--border);
    padding: 8px 16px;
    border-radius: 8px;
    z-index: 200;
    font-family: var(--mono);
    font-size: 12px;
    backdrop-filter: blur(12px);
  }}
  .controls button {{
    background: none;
    border: 1px solid var(--border);
    color: var(--text);
    padding: 6px 14px;
    border-radius: 4px;
    cursor: pointer;
    font-family: var(--mono);
    font-size: 12px;
    transition: all 0.15s;
  }}
  .controls button:hover {{ background: var(--bg-hover); border-color: var(--border-accent); }}
  .controls button:active {{ background: var(--border); }}
  .controls .slide-counter {{ color: var(--text-dim); min-width: 60px; text-align: center; }}
  .controls .slide-counter .current {{ color: var(--text-bright); font-weight: 700; }}

  /* ═══ PROGRESS BAR ═══ */
  .progress {{
    position: fixed;
    top: 0;
    left: 0;
    height: 3px;
    background: var(--blue);
    z-index: 300;
    transition: width 0.3s ease;
  }}

  /* ═══ INDEX OVERLAY ═══ */
  .index-overlay {{
    position: fixed;
    inset: 0;
    background: rgba(13, 17, 23, 0.95);
    backdrop-filter: blur(20px);
    z-index: 400;
    display: none;
    align-items: center;
    justify-content: center;
  }}
  .index-overlay.visible {{ display: flex; }}
  .index-box {{
    width: 100%;
    max-width: 600px;
    max-height: 80vh;
    overflow-y: auto;
    padding: 32px;
  }}
  .index-box h2 {{
    font-family: var(--sans);
    font-size: 24px;
    font-weight: 600;
    color: var(--text-bright);
    margin-bottom: 24px;
    text-align: center;
  }}
  .idx-item {{
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 14px;
    border-radius: 4px;
    cursor: pointer;
    transition: background 0.15s;
  }}
  .idx-item:hover {{ background: var(--bg-hover); }}
  .idx-dot {{
    width: 10px;
    height: 10px;
    border-radius: 50%;
    flex-shrink: 0;
  }}
  .idx-dot.idx-pir {{ background: var(--blue); }}
  .idx-dot.idx-sir {{ background: var(--amber); }}
  .idx-dot.idx-ffir {{ background: var(--green); }}
  .idx-dot.idx-cnr {{ background: var(--red); }}
  .idx-dot.idx-stats {{ background: var(--purple); }}
  .idx-dot.idx-gray {{ background: var(--text-dim); }}
  .idx-dot.idx-filtered {{ background: var(--text-dim); }}
  .idx-dot.idx-blufs {{ background: var(--purple); }}
  .idx-label {{
    font-family: var(--sans);
    font-size: 14px;
    color: var(--text-bright);
    flex: 1;
  }}
  .idx-sub {{
    font-family: var(--mono);
    font-size: 10px;
    color: var(--text-dim);
  }}
  .idx-num {{
    font-family: var(--mono);
    font-size: 11px;
    color: var(--text-dim);
    width: 24px;
    text-align: right;
  }}

  /* ═══ KEYBOARD HINT ═══ */
  .kbd-hint {{
    position: fixed;
    bottom: 80px;
    left: 50%;
    transform: translateX(-50%);
    font-family: var(--mono);
    font-size: 10px;
    color: var(--text-dim);
    opacity: 0.5;
    z-index: 200;
    text-align: center;
    pointer-events: none;
  }}

  /* ═══ SCROLL MODE OVERRIDES ═══ */
  html.mode-scroll {{ scroll-snap-type: none; }}
  body.mode-scroll .slide {{
    min-height: auto;
    scroll-snap-align: none;
    align-items: flex-start;
    padding: 40px 80px 60px;
  }}
  body.mode-scroll .slide-inner {{
    opacity: 1;
    transform: none;
  }}
  body.mode-scroll .slide .slide-inner {{
    opacity: 1;
    transform: none;
  }}
  body.mode-scroll .kbd-hint {{ display: none; }}
  body.mode-scroll .controls {{
    position: sticky;
    top: 0;
    bottom: auto;
    left: 0;
    transform: none;
    border-radius: 0;
    border-left: none;
    border-right: none;
    justify-content: center;
  }}
  body.mode-scroll .controls .nav-arrows {{ display: none; }}
  body.mode-scroll .progress {{ position: sticky; }}
  body.mode-scroll .title-slide {{
    min-height: 50vh;
    padding-top: 80px;
  }}

  /* ═══ MODE TOGGLE BUTTON ═══ */
  .mode-toggle {{
    display: flex;
    align-items: center;
    gap: 6px;
    font-family: var(--mono);
    font-size: 11px;
    color: var(--text-dim);
    padding: 4px 10px;
    border: 1px solid var(--border);
    border-radius: 4px;
    cursor: pointer;
    transition: all 0.15s;
    user-select: none;
  }}
  .mode-toggle:hover {{ background: var(--bg-hover); border-color: var(--border-accent); color: var(--text); }}
  .mode-toggle .mode-icon {{ font-size: 14px; }}

  /* ═══ PMESII BADGES ═══ */
  .pmesii-badge {{
    font-size: 14px;
    margin-right: 4px;
    vertical-align: middle;
    opacity: 0.85;
  }}
  .pmesii-dist {{
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 12px;
    margin-top: 20px;
  }}
  .pmesii-dist-card {{
    display: flex;
    align-items: center;
    gap: 10px;
    background: var(--bg-card);
    border: 1px solid var(--border);
    padding: 14px 16px;
    border-radius: 4px;
  }}
  .pmesii-dist-card .p-icon {{ font-size: 22px; }}
  .pmesii-dist-card .p-name {{
    font-family: var(--mono);
    font-size: 11px;
    color: var(--text-dim);
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }}
  .pmesii-dist-card .p-count {{
    font-family: var(--mono);
    font-size: 22px;
    font-weight: 700;
    color: var(--text-bright);
    margin-left: auto;
  }}
  .pmesii-dist-card .p-bar {{
    width: 60px;
    height: 4px;
    background: var(--border);
    border-radius: 2px;
    overflow: hidden;
    margin-left: 8px;
  }}
  .pmesii-dist-card .p-bar-fill {{
    height: 100%;
    border-radius: 2px;
  }}

  ::-webkit-scrollbar {{ width: 6px; }}
  ::-webkit-scrollbar-track {{ background: transparent; }}
  ::-webkit-scrollbar-thumb {{ background: var(--border); border-radius: 3px; }}

  /* ═══ WINDOW SELECTOR ═══ */
  .window-selector {{
    display: inline-flex;
    align-items: center;
    gap: 8px;
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 999px;
    padding: 6px;
    margin-bottom: 28px;
    box-shadow: 0 4px 16px rgba(0,0,0,0.25);
  }}
  .window-selector .ws-btn {{
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 8px 16px;
    border-radius: 999px;
    font-family: var(--mono);
    font-size: 12px;
    font-weight: 600;
    color: var(--text-dim);
    text-decoration: none;
    border: 1px solid transparent;
    background: transparent;
    transition: all 0.15s ease;
    cursor: pointer;
  }}
  .window-selector .ws-btn:hover {{
    color: var(--text);
    background: var(--bg-hover);
    border-color: var(--border-accent);
  }}
  .window-selector .ws-btn.active {{
    color: var(--text-bright);
    background: var(--blue-dim);
    border-color: var(--blue);
    box-shadow: 0 0 12px var(--blue-dim);
  }}
  .window-selector .ws-btn .ws-badge {{
    font-size: 9px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    padding: 2px 6px;
    border-radius: 999px;
    background: var(--amber-dim);
    color: var(--amber);
    border: 1px solid var(--amber);
    white-space: nowrap;
  }}
  .window-selector .ws-btn.active .ws-badge {{
    background: var(--amber);
    color: var(--bg);
  }}

  /* ═══ SOURCE STATUS CARD ═══ */
  .source-status-card {{
    position: fixed;
    top: 20px;
    right: 20px;
    min-width: 220px;
    max-width: 320px;
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 6px;
    box-shadow: 0 8px 24px rgba(0,0,0,0.35);
    z-index: 500;
    backdrop-filter: blur(12px);
    overflow: hidden;
    transition: max-height 0.25s ease;
  }}
  .source-status-card.collapsed {{ max-height: 44px; }}
  .source-status-card:not(.collapsed) {{ max-height: 70vh; }}
  .source-status-header {{
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 12px 14px;
    cursor: pointer;
    user-select: none;
    border-bottom: 1px solid transparent;
    transition: background 0.15s, border-color 0.15s;
  }}
  .source-status-card:not(.collapsed) .source-status-header {{
    border-bottom-color: var(--border);
  }}
  .source-status-header:hover {{ background: var(--bg-hover); }}
  .source-status-title {{
    font-family: var(--sans);
    font-size: 13px;
    font-weight: 600;
    color: var(--text-bright);
  }}
  .source-status-summary {{
    margin-left: auto;
    font-family: var(--mono);
    font-size: 10px;
    color: var(--text-dim);
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }}
  .source-status-chevron {{
    font-size: 10px;
    color: var(--text-dim);
    transition: transform 0.2s ease;
  }}
  .source-status-card:not(.collapsed) .source-status-chevron {{
    transform: rotate(180deg);
  }}
  .source-status-body {{
    overflow-y: auto;
    max-height: calc(70vh - 44px);
    padding: 8px 0;
  }}
  .source-row {{
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 7px 14px;
    font-size: 12px;
    line-height: 1.4;
  }}
  .source-row:nth-child(even) {{ background: rgba(255,255,255,0.02); }}
  .source-status {{
    flex-shrink: 0;
    width: 18px;
    height: 18px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 10px;
    font-weight: 700;
  }}
  .source-status.ok {{ background: var(--green-dim); color: var(--green); }}
  .source-status.fail {{ background: var(--red-dim); color: var(--red); }}
  .source-name {{
    flex: 1;
    color: var(--text-bright);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }}
  .source-ts {{
    flex-shrink: 0;
    font-family: var(--mono);
    font-size: 10px;
    color: var(--text-dim);
    white-space: nowrap;
  }}

  ::-webkit-scrollbar {{ width: 6px; }}
  ::-webkit-scrollbar-track {{ background: transparent; }}
  ::-webkit-scrollbar-thumb {{ background: var(--border); border-radius: 3px; }}
</style>
</head>
<body class="mode-present">

<!-- Source status card -->
{source_status_card}

<!-- Progress bar -->
<div class="progress" id="progress"></div>

<!-- ═══ TITLE SLIDE ═══ -->
<section class="slide title-slide" id="sab-title">
  <div class="slide-inner">
    <div class="classification">FOUO</div>
    <nav class="window-selector" aria-label="Velg tidsvindu">
      <a class="ws-btn" href="/sab?window=24h" data-window="24h" title="Siste 24 timer">
        <span>🕒</span>
        <span>24h</span>
      </a>
      <a class="ws-btn" href="/sab?window=72h" data-window="72h" title="Siste 72 timer — helgestandard">
        <span>📅</span>
        <span>72h</span>
        <span class="ws-badge">helg</span>
      </a>
      <a class="ws-btn" href="/sab?window=168h" data-window="168h" title="Siste uke">
        <span>🗓️</span>
        <span>1 uke</span>
      </a>
    </nav>
    <h1>InfoTriage · Situational Awareness Brief</h1>
    <div class="subtitle">
      <span>📅 {period}</span>
      <span>⏱ Generert: {generated_at}</span>
      {fetch_line}
      <span>🧠 qwen36 via oMLX · ADR-004</span>
    </div>
    <div class="stats-row">
      <div class="stat">
        <div class="stat-val red">{scanned}</div>
        <div class="stat-lbl">Skannet</div>
      </div>
      <div class="stat">
        <div class="stat-val green">{ccir_hits}</div>
        <div class="stat-lbl">CCIR-treff</div>
      </div>
      <div class="stat">
        <div class="stat-val amber">{filtered}</div>
        <div class="stat-lbl">Filtrert ut</div>
      </div>
      <div class="stat">
        <div class="stat-val blue">{rate}</div>
        <div class="stat-lbl">Treffrate</div>
      </div>
    </div>
  </div>
</section>

<!-- CNR slide -->
{cnr}

<!-- CCIR slides -->
{sections}

<!-- Stats slide -->
<section class="slide" id="stats">
  <div class="slide-inner">
    <div class="slide-header">
      <div class="slide-header-left">
        <span class="ccir-badge" style="background:var(--purple);color:#fff;">📊</span>
        <span class="ccir-title">Vindu-statistikk</span>
      </div>
      <span class="ccir-count">{scanned} totalt · {ccir_hits} CCIR · {filtered} ut</span>
    </div>
    <div class="stats-slide-grid">
      <div class="stats-slide-card">
        <div class="val" style="color:var(--red)">{scanned}</div>
        <div class="lbl">Skannet</div>
      </div>
      <div class="stats-slide-card">
        <div class="val" style="color:var(--green)">{ccir_hits}</div>
        <div class="lbl">CCIR-treff</div>
      </div>
      <div class="stats-slide-card">
        <div class="val" style="color:var(--blue)">{rate}</div>
        <div class="lbl">Treffrate</div>
      </div>
    </div>
    <ul class="stats-ccir-list">
      {stats_ccir_list}
    </ul>
    <h3 style="font-family:var(--sans);font-size:16px;font-weight:600;color:var(--text-bright);margin-top:32px;margin-bottom:4px;">PMESII — operasjonelle domener</h3>
    {pmesii_dist}
    <h3 style="font-family:var(--sans);font-size:16px;font-weight:600;color:var(--text-bright);margin-top:24px;margin-bottom:4px;">TESSOC — trusselaktører</h3>
    {tessoc_dist}
    <div style="font-family:var(--mono);font-size:11px;color:var(--text-dim);margin-top:24px;text-align:center;">
      qwen36-ud-4bit · oMLX :8000/v1 · ADR-004 ✅<br>
      <a href="https://github.com/vbrevik/InfoTriage" style="color:var(--blue);text-decoration:none;">github.com/vbrevik/InfoTriage</a>
    </div>
  </div>
</section>

<!-- Index overlay -->
<div class="index-overlay" id="indexOverlay">
  <div class="index-box">
    <h2>Slide-oversikt · trykk Esc for å lukke</h2>
    {index_items}
  </div>
</div>

<!-- Controls -->
<div class="controls">
  <span class="mode-toggle" onclick="toggleMode()" title="Bytt visning (M)">
    <span class="mode-icon" id="modeIcon">📊</span>
    <span id="modeLabel">Presentasjon</span>
  </span>
  <span class="nav-arrows">
    <button onclick="prevSlide()">← Forrige</button>
    <div class="slide-counter">
      <span class="current" id="currentSlide">1</span> / {total_slides}
    </div>
    <button onclick="nextSlide()">Neste →</button>
  </span>
  <button onclick="toggleIndex()" title="Trykk Esc">☰ Indeks</button>
</div>

<!-- Keyboard hint -->
<div class="kbd-hint">← → naviger · Esc indeks · F fullskjerm · M bytt modus</div>

<script>
  const slides = document.querySelectorAll('.slide');
  const progress = document.getElementById('progress');
  const currentEl = document.getElementById('currentSlide');
  const overlay = document.getElementById('indexOverlay');
  let current = 0;

  function goToSlide(n) {{
    if (n < 0) n = 0;
    if (n >= slides.length) n = slides.length - 1;
    current = n;
    slides[n].scrollIntoView({{ behavior: 'smooth' }});
    updateUI();
    overlay.classList.remove('visible');
  }}

  function copyAllBlufs() {{
    const section = document.getElementById('blufs');
    if (!section) return;
    const lines = [];

    // Include executive summary first
    const execBox = section.querySelector('.exec-bluf-box');
    if (execBox) {{
      const execText = execBox.querySelector('.bluf-text');
      if (execText && execText.textContent.trim()) {{
        lines.push('EXECUTIVE SUMMARY');
        lines.push(execText.textContent.trim());
        lines.push('');
      }}
    }}

    const rows = section.querySelectorAll('.bluf-row');
    rows.forEach(row => {{
      const badge = row.querySelector('.ccir-badge');
      const title = row.querySelector('.ccir-title-small');
      const text = row.querySelector('.bluf-text');
      const cid = badge ? badge.textContent.trim() : '';
      const ttl = title ? title.textContent.trim() : '';
      const bluf = text ? text.textContent.trim() : '';
      if (cid && bluf) {{
        lines.push(`${{cid}} — ${{ttl}}`);
        lines.push(bluf);
        lines.push('');
      }}
    }});
    const payload = lines.join('\\n');
    const btn = document.getElementById('copyBlufsBtn');
    const label = btn ? btn.querySelector('.copy-label') : null;
    if (navigator.clipboard && navigator.clipboard.writeText) {{
      navigator.clipboard.writeText(payload).then(() => {{
        if (btn) btn.classList.add('copied');
        if (label) label.textContent = 'Kopiert!';
        setTimeout(() => {{
          if (btn) btn.classList.remove('copied');
          if (label) label.textContent = 'Kopier alle BLUFs';
        }}, 2000);
      }}).catch(err => {{
        console.error('Kunne ikke kopiere BLUFs:', err);
        if (label) label.textContent = 'Kopiering feilet';
        setTimeout(() => {{ if (label) label.textContent = 'Kopier alle BLUFs'; }}, 2000);
      }});
    }} else {{
      // Fallback for older browsers / insecure contexts
      try {{
        const ta = document.createElement('textarea');
        ta.value = payload;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        if (btn) btn.classList.add('copied');
        if (label) label.textContent = 'Kopiert!';
        setTimeout(() => {{
          if (btn) btn.classList.remove('copied');
          if (label) label.textContent = 'Kopier alle BLUFs';
        }}, 2000);
      }} catch (err) {{
        console.error('Kunne ikke kopiere BLUFs:', err);
        if (label) label.textContent = 'Kopiering feilet';
        setTimeout(() => {{ if (label) label.textContent = 'Kopier alle BLUFs'; }}, 2000);
      }}
    }}
  }}

  function nextSlide() {{ goToSlide(current + 1); }}
  function prevSlide() {{ goToSlide(current - 1); }}

  function toggleBlufRow(header) {{
    const row = header.parentElement;
    if (!row) return;
    const isCollapsed = row.classList.toggle('collapsed');
    header.setAttribute('aria-expanded', String(!isCollapsed));
  }}

  function toggleSourceCard() {{
    const card = document.getElementById('sourceStatusCard');
    if (!card) return;
    card.classList.toggle('collapsed');
  }}

  // Keyboard accessibility for collapsible BLUF rows
  document.addEventListener('keydown', (e) => {{
    if (e.key !== 'Enter' && e.key !== ' ') return;
    const header = e.target.closest('.bluf-row-header');
    if (!header) return;
    e.preventDefault();
    toggleBlufRow(header);
  }});

  function toggleIndex() {{
    overlay.classList.toggle('visible');
  }}

  function updateUI() {{
    currentEl.textContent = current + 1;
    progress.style.width = ((current + 1) / slides.length * 100) + '%';
  }}

  // Intersection observer for slide visibility
  const observer = new IntersectionObserver((entries) => {{
    entries.forEach(entry => {{
      if (entry.isIntersecting) {{
        entry.target.classList.add('visible');
        const idx = Array.from(slides).indexOf(entry.target);
        if (idx >= 0) {{ current = idx; updateUI(); }}
      }}
    }});
  }}, {{ threshold: 0.5 }});

  slides.forEach(s => observer.observe(s));

  // Mode toggle
  let scrollMode = localStorage.getItem('sab-mode') === 'scroll';
  const modeIcon = document.getElementById('modeIcon');
  const modeLabel = document.getElementById('modeLabel');

  function applyMode() {{
    document.documentElement.classList.toggle('mode-scroll', scrollMode);
    document.body.classList.toggle('mode-scroll', scrollMode);
    document.body.classList.toggle('mode-present', !scrollMode);
    modeIcon.textContent = scrollMode ? '📜' : '📊';
    modeLabel.textContent = scrollMode ? 'Rulling' : 'Presentasjon';
    // In scroll mode, make all slide-inners visible immediately
    if (scrollMode) {{
      document.querySelectorAll('.slide-inner').forEach(el => {{
        el.style.opacity = '1';
        el.style.transform = 'none';
      }});
    }} else {{
      document.querySelectorAll('.slide-inner').forEach(el => {{
        el.style.opacity = '';
        el.style.transform = '';
      }});
    }}
  }}
  function toggleMode() {{
    scrollMode = !scrollMode;
    localStorage.setItem('sab-mode', scrollMode ? 'scroll' : 'present');
    applyMode();
    if (!scrollMode) goToSlide(current);
  }}
  applyMode();

  // Keyboard
  document.addEventListener('keydown', (e) => {{
    if (overlay.classList.contains('visible')) {{
      if (e.key === 'Escape') {{ overlay.classList.remove('visible'); e.preventDefault(); }}
      return;
    }}
    if (e.key === 'm' || e.key === 'M') {{ toggleMode(); e.preventDefault(); return; }}
    if (scrollMode) return; // arrow nav only in presentation mode
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown' || e.key === ' ') {{ nextSlide(); e.preventDefault(); }}
    if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {{ prevSlide(); e.preventDefault(); }}
    if (e.key === 'Escape') {{ toggleIndex(); e.preventDefault(); }}
    if (e.key === 'f' || e.key === 'F') {{
      if (!document.fullscreenElement) document.documentElement.requestFullscreen();
      else document.exitFullscreen();
    }}
  }});

  // Initial state
  slides[0].classList.add('visible');
  updateUI();

  // Highlight active window selector button based on URL
  (function setActiveWindow() {{
    const params = new URLSearchParams(window.location.search);
    const windowParam = params.get('window') || '24h';
    document.querySelectorAll('.window-selector .ws-btn').forEach(btn => {{
      if (btn.dataset.window === windowParam) {{
        btn.classList.add('active');
      }} else {{
        btn.classList.remove('active');
      }}
    }});
  }})();

  // Collapse source status card by default on small screens
  if (window.innerWidth < 768) {{
    const sourceCard = document.getElementById('sourceStatusCard');
    if (sourceCard) sourceCard.classList.add('collapsed');
  }} else {{
    const sourceCard = document.getElementById('sourceStatusCard');
    if (sourceCard) sourceCard.classList.add('collapsed');
  }}
</script>

</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser(
        description="Generate SAB HTML presentation from verdicts.jsonl"
    )
    ap.add_argument("--since", help='cutoff "YYYY-MM-DD HH:MM" (Oslo)')
    ap.add_argument("--hours", type=int, help="rolling window")
    ap.add_argument("--out", default=OUT, help="output HTML path")
    ap.add_argument(
        "--no-bluf",
        action="store_true",
        help="skip BLUF LLM synthesis (faster, no citations)",
    )
    args = ap.parse_args()

    load_dotenv(os.path.join(ROOT, ".env"))

    if args.since:
        cutoff = datetime.datetime.strptime(args.since, "%Y-%m-%d %H:%M").replace(
            tzinfo=OSLO
        )
    elif args.hours:
        cutoff = oslo_now() - datetime.timedelta(hours=args.hours)
    else:
        cutoff = default_cutoff()

    period = f"siden {stamp(cutoff)} → {stamp(oslo_now())}"
    print(f"window: {period}", file=sys.stderr)

    verdicts = load_verdicts(int(cutoff.timestamp()))
    print(f"loaded {len(verdicts)} verdicts from {STORE}", file=sys.stderr)

    if not verdicts:
        print("no verdicts in window — writing empty-state page", file=sys.stderr)

    gen_ts = stamp(oslo_now())
    html = build_html(
        verdicts,
        period,
        with_bluf=not args.no_bluf,
        generated_at=gen_ts,
        cutoff_epoch=int(cutoff.timestamp()),
    )

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    tmp = args.out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(html)
    os.replace(tmp, args.out)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
