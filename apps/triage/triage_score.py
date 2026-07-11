#!/usr/bin/env python3
"""InfoTriage scorer — the noise-killer.

Scores incoming items (newsletters, RSS, web) with a LOCAL model on the Mac and
buckets them read / maybe / skip against the user's interest profile. No cloud.

Usage:
  python3 triage_score.py --sample                 # demo on built-in items
  cat items.json | python3 triage_score.py         # JSON list on stdin
  python3 triage_score.py --file items.json --json  # machine-readable out

items.json = [{"title": "...", "source": "...", "summary": "..."}]
Env (or .env): LLM_BASE_URL, LLM_API_KEY, LLM_MODEL.
"""
import json, os, sys, argparse, logging, urllib.request, urllib.error

# The triage brain lives in ccir.md (Commander's Critical Information Requirements).
# Edit that file to retune — not this code.
CCIR_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "ccir.md")

log = logging.getLogger(__name__)

def load_ccir():
    try:
        return open(CCIR_PATH, encoding="utf-8").read()
    except FileNotFoundError:
        return "(no ccir.md found — keep only clearly defense/geopolitics/Norway/tech items)"

def load_dotenv(path):
    if not os.path.exists(path):
        return
    for line in open(path):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

def llm(messages, max_tokens=400):
    base = os.environ.get("LLM_BASE_URL", "http://127.0.0.1:8000/v1")
    key = os.environ.get("LLM_API_KEY", "omlx")
    model = os.environ.get("LLM_MODEL", "qwen36-ud-4bit")
    body = json.dumps({
        "model": model, "messages": messages,
        "temperature": 0, "max_tokens": max_tokens,
    }).encode()
    req = urllib.request.Request(
        base.rstrip("/") + "/chat/completions", data=body,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)["choices"][0]["message"]["content"]

def score_item(it):
    ccir = load_ccir()
    prompt = f"""You are an intelligence analyst triaging news against the commander's
CCIR below. Decide which single CCIR (if any) this item answers, and its CNR level.

{ccir}

Tier quick-reference (full descriptions in ccir.md above):
- PIR-1 Russland/Ukraina — krig, frontlinjer, våpenstøtte, sanksjoner
- PIR-2 Nordområdene & Arktis — Svalbard, ubåter, GIUK-gap, nordlig sjørute
- PIR-3 NATO & europeisk sikkerhet — toppmøter, styrkeoppbygging, østflanken
- PIR-4 Hybrid- & cybertrusler — sabotasje, påvirkning, cyberangrep + infrastrukturpostur (kabler, energinett, LNG, nordlig sjørute, arktisk logistikk, GIUK)
- PIR-5 Stormaktsrivalisering — Kina, USAs vendinger med strategisk vekt for Europa/Norden
- PIR-6 OSINT & etterforskning — krigsforbrytelser, sanksjonsomgåelse, aktør-identifisering (Bellingcat, OCCRP)
- FFIR-1 Norsk forsvar & sikkerhetspolitikk — Stortinget, Forsvaret, beredskap, E-tjenesten
- FFIR-2 Norsk politikk & samfunn — strategisk/nasjonal betydning
- FFIR-3 Egen teknologikapabilitet — lokale LLM-er (Mac/Qwen/MLX/Ollama), AI-agenter, DFIR, Rust, homelab, NVIDIA-stack (DGX Spark / GB10 Grace Blackwell / CUDA-versjoner)
- SIR-1 Midtøsten & US-Iran — IRGC, proxyer, atomprogram, sanksjonspress (tidsavgrenset)
- SIR-2 Sport — VM 2026 (FIFA) — sikkerhets-/geopolitisk dimensjon; CARVE-OUT løfter over CNR-Routine
- "none" if the item answers no CCIR at all.

PMESII operational environment domain (choose the ONE primary domain this item falls under):
- Political: Power structures and diplomacy; treaties, government policy, elections, sanctions as policy instrument.
- Military: Defense capabilities and warfare; posture, troop movements, weapons systems, military operations.
- Economic: Resource production and markets; sanctions impact, trade wars, defence budgets, financial markets, energy markets.
- Social: Demographic and cultural composition; protests, civil unrest, public opinion, cultural/sporting events with political dimension.
- Information: Information flow and systems; cyber operations, OSINT investigations, propaganda, hybrid influence, media manipulation.
- Infrastructure: Essential facilities; undersea cables, pipelines, logistics networks, energy grid, transport, maritime routes.
- "none" if ccir is "none" (irrelevant items have no operational domain).

TESSOC threat actor (UK/NATO counterintelligence framework, JDP 2-00 — choose the ONE primary threat actor type):
- Terror: Terrorism, violent extremism, attacks against civilians or symbolic targets.
- Espionage: Spying, intelligence collection, covert information gathering by state or non-state actors.
- Subversion: Undermining authority, influence operations, destabilization, fifth-column activity.
- Sabotage: Deliberate destruction or disruption of infrastructure, logistics, or capabilities.
- Organized Crime: Criminal networks, trafficking, money laundering, racketeering, corruption.
- "none" if ccir is "none".

Disambiguation guide — when an item could match multiple tiers:
- PIR-5 vs SIR-1: if the core subject is Iran, IRGC, or Middle East escalation → SIR-1. If the item is about great-power dynamics (US-China, US global posture) where the Middle East is only context → PIR-5.
- PIR-1 vs PIR-6: if the item is an OSINT investigation (identifying actors, tracing networks, sanctions evasion) about Russia/Ukraine → PIR-6. Straight war reporting, battlefield updates, or policy announcements → PIR-1.
- PIR-6 vs SIR-2: if the item is an investigation into sports corruption/fraud in FIFA context → PIR-6. If it is about security, protests, boycotts, or geopolitical tensions around VM 2026 specifically → SIR-2.
- FFIR-3 vs PIR-4: cybersecurity of Norwegian critical infra → PIR-4. Building your own local LLM / DFIR lab / homelab → FFIR-3.
- Sport (general) vs SIR-2: regular sport coverage with no security/political angle → "none". VM 2026 security, protests, boycott, terrortrussel, or political controversy → SIR-2.

Worked examples:
1. "Bellingcat identifies Russian officer behind Bucha massacre using phone metadata"
   → {{"ccir": "PIR-6", "cnr": "II", "pmesii": "Information", "tessoc": "Espionage", "score": 8, "why": "OSINT-identifisering av krigsforbryter"}}
2. "OCCRP: Shell companies helped oligarchs evade EU sanctions"
   → {{"ccir": "PIR-6", "cnr": "II", "pmesii": "Economic", "tessoc": "Organized Crime", "score": 7, "why": "Sanksjonsomgåelse via skallselskaper"}}
3. "IRGC-linked militia launches rockets at US base in Syria"
   → {{"ccir": "SIR-1", "cnr": "I", "pmesii": "Military", "tessoc": "Terror", "score": 9, "why": "IRGC-proxy angriper amerikansk base"}}
4. "Iran enriches uranium to 84% — IAEA report"
   → {{"ccir": "SIR-1", "cnr": "I", "pmesii": "Military", "tessoc": "Espionage", "score": 9, "why": "Atomprogram-oppgradering, høy beredskap"}}
5. "FIFA confirms World Cup 2026 will use expanded 48-team format"
   → {{"ccir": "SIR-2", "cnr": "II", "pmesii": "Social", "tessoc": "none", "score": 5, "why": "VM 2026 format-oppdatering"}}
6. "Threat of mass protests at US World Cup venues over immigration policy"
   → {{"ccir": "SIR-2", "cnr": "II", "pmesii": "Social", "tessoc": "Terror", "score": 7, "why": "Protest-trussel mot VM-arenaer"}}
7. "NATO summit agrees 2% GDP defence spending floor"
   → {{"ccir": "PIR-3", "cnr": "II", "pmesii": "Political", "tessoc": "none", "score": 7, "why": "NATO-toppmøte, forsvarsbudsjetter"}}
8. "Sony releases new PlayStation update"
   → {{"ccir": "none", "cnr": "none", "pmesii": "none", "tessoc": "none", "score": 0, "why": "Forbrukerteknologi, ingen CCIR"}}

Return ONLY JSON:
{{"ccir": "<PIR-1 | PIR-2 | PIR-3 | PIR-4 | PIR-5 | PIR-6 | FFIR-1 | FFIR-2 | FFIR-3 | SIR-1 | SIR-2 | none>", "cnr": "<I | II | none>", "pmesii": "<Political | Military | Economic | Social | Information | Infrastructure | none>", "tessoc": "<Terror | Espionage | Subversion | Sabotage | Organized Crime | none>",
  "score": 0-10, "why": "<=12 words, in Norwegian>"}}
Rules:
- ccir = the ONE requirement it best answers, or "none" if it answers none.
- cnr = "I" only if it meets a CAT I notification trigger; "II" if it answers a CCIR
  but is routine; "none" if ccir is none.
- score 0-10 = how strongly/importantly it answers the CCIR (none → 0-2).
- Be ruthless: most items answer no CCIR → ccir "none".

TITLE: {it.get('title','')}
SOURCE: {it.get('source','')}
SUMMARY: {it.get('summary','')}"""
    raw = llm([{"role": "user", "content": prompt}]).strip()
    if "```" in raw:
        raw = raw.split("```")[1].lstrip("json").strip()
    s, e = raw.find("{"), raw.rfind("}")
    try:
        v = json.loads(raw[s:e+1])
    except Exception:
        v = {"ccir": "none", "cnr": "none", "pmesii": "none", "tessoc": "none", "score": 0, "why": "uleselig modell-svar"}
    # Prompt-contract enforcement: ccir='none' forces pmesii='none' AND
    # tessoc='none' (PMESII: '"none" if ccir is "none"' / TESSOC: '"none" if ccir is "none"'
    # in the scoring prompt's disambiguation rules). Coerce LLM drift before
    # falling back to setdefault for valid CCIRs.
    #
    # Observability: silently coercing LLM drift would mask a prompt regression,
    # so emit log.warning whenever the LLM actually emitted non-'none'
    # enrichment alongside a ccir='none' row. The warning carries the
    # pre-coercion values for audit; downstream consumers always see the
    # clean ('none') values. Fits under Phase 7 Task 2 (structured logging).
    ccir_lower = (v.get("ccir") or "none").lower()
    if ccir_lower == "none":
        # Capture pre-coercion values BEFORE we overwrite them so the
        # warning can carry the actual drift signal.
        _pre_pmesii = v.get("pmesii")
        _pre_tessoc = v.get("tessoc")
        coerced = (
            _pre_pmesii not in (None, "", "none")
            or _pre_tessoc not in (None, "", "none")
        )
        v["pmesii"] = "none"
        v["tessoc"] = "none"
        if coerced:
            log.warning(
                "triage_score enriched ccir=none with non-'none' pmesii/tessoc; "
                "coercing to 'none' (pre-coercion: pmesii=%r tessoc=%r). "
                "Likely cause: qwen36 drift away from ccir.md's rule "
                "'\"none\" if ccir is \"none\"'.",
                _pre_pmesii, _pre_tessoc,
            )
    else:
        # ensure enrichment fields always present (LLM may omit them)
        v.setdefault("pmesii", "none")
        v.setdefault("tessoc", "none")
    # derive bucket for the Fever loop: CCIR match = keep, else skip
    ccir = ccir_lower
    v["bucket"] = "skip" if ccir == "none" else ("read" if v.get("cnr") == "I"
                                                 or v.get("score", 0) >= 7 else "maybe")
    return {**it, **v}

SAMPLE = [
    # PIR-6: OSINT & etterforskning
    {"title": "Bellingcat identifies GRU officer behind Skripal attack via passport leak",
     "source": "Bellingcat", "summary": "Open-source investigators traced a GRU colonel to the Novichok attack using leaked Russian passport records and travel data."},
    # SIR-1: Midtøsten & US-Iran
    {"title": "IRGC seizes oil tanker in Strait of Hormuz amid rising tensions",
     "source": "Crisis Group", "summary": "Iran's Revolutionary Guard boarded and detained a commercial vessel in the Strait of Hormuz, escalating US-Iran maritime standoff."},
    # SIR-2: Sport — VM 2026
    {"title": "Mass protests expected at 2026 World Cup over US immigration policy",
     "source": "BBC Sport Football", "summary": "Activist groups announce coordinated demonstrations at FIFA World Cup 2026 venues to protest US border and immigration enforcement."},
    # FFIR-3: Egen teknologikapabilitet
    {"title": "Run Claude Code Locally on a Mac: 65 tok/s with 4-bit Qwen3.6-27B + DFlash",
     "source": "Medium", "summary": "Speculative decoding to run Claude Code on local Qwen on a Mac."},
    # none: irrelevant
    {"title": "L'Oréal Builds AI Beauty Engine with OpenAI",
     "source": "MyClaw", "summary": "L'Oréal cuts production cost 40%, 50k marketing assets."},
    # none: irrelevant
    {"title": "MAMMOTION robotic lawn mowers on sale for Prime Day",
     "source": "HowToGeek", "summary": "Sponsored. Up to $1059 off robotic mowers."},
    # PIR-4: Hybrid- & cybertrusler
    {"title": "Suspected sabotage cuts undersea cable between Norway and Finland",
     "source": "NRK", "summary": "An undersea fiber optic cable in the Barents Sea was severed overnight; Norwegian authorities suspect deliberate sabotage."},
    # FFIR-1: Norsk forsvar & sikkerhetspolitikk
    {"title": "Norway orders 52 Leopard 2A7 tanks in largest defence purchase in decades",
     "source": "Forsvarets forum", "summary": "The Norwegian government approved a NOK 19 billion procurement of German Leopard 2A7 main battle tanks for the Army."},
]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", action="store_true")
    ap.add_argument("--file")
    ap.add_argument("--json", action="store_true", help="emit JSON not markdown")
    args = ap.parse_args()
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

    if args.sample:
        items = SAMPLE
    elif args.file:
        items = json.load(open(args.file))
    else:
        items = json.load(sys.stdin)

    scored = sorted((score_item(it) for it in items),
                    key=lambda x: x.get("score", 0), reverse=True)

    if args.json:
        print(json.dumps(scored, indent=2)); return

    icon = {"read": "🔥", "maybe": "🤔", "skip": "🗑️"}
    print("# InfoTriage digest\n")
    for it in scored:
        print(f"{icon.get(it.get('bucket'),'•')} **[{it.get('score')}] {it['title']}**")
        print(f"    {it.get('source','')} — {it.get('why','')}\n")

if __name__ == "__main__":
    main()
