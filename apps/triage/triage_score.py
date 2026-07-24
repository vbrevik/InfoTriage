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

from contracts.ccir import build_quickref, build_examples_and_guide, active_ccir_enum

# The CCIR taxonomy lives in the registry (libs/contracts/.../ccir.py): the
# scorer's quick-reference, JSON enum, disambiguation guide, and worked examples
# all derive from it (add/edit/retire a requirement there — one place). ccir.md
# holds the human-facing analytical prose and is still inlined verbatim into the
# prompt below for the model's full context.
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
    body = json.dumps(
        {
            "model": model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": max_tokens,
        }
    ).encode()
    req = urllib.request.Request(
        base.rstrip("/") + "/chat/completions",
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)["choices"][0]["message"]["content"]


def score_item(it):
    ccir = load_ccir()
    # CCIR-specific prompt sections derive from the single-source registry
    # (contracts.ccir). The PMESII/TESSOC framework prose below is not
    # CCIR-specific and stays inline. `enum` is the JSON-schema CCIR enum.
    quickref = build_quickref()
    examples_and_guide = build_examples_and_guide()
    enum = active_ccir_enum()
    prompt = f"""You are an intelligence analyst triaging news against the commander's
CCIR below. Decide which single CCIR (if any) this item answers, and its CNR level.

{ccir}

{quickref}

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

{examples_and_guide}

Return ONLY JSON:
{{"ccir": "<{enum}>", "cnr": "<I | II | none>", "pmesii": "<Political | Military | Economic | Social | Information | Infrastructure | none>", "tessoc": "<Terror | Espionage | Subversion | Sabotage | Organized Crime | none>",
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
        v = json.loads(raw[s : e + 1])
    except Exception:
        v = {
            "ccir": "none",
            "cnr": "none",
            "pmesii": "none",
            "tessoc": "none",
            "score": 0,
            "why": "uleselig modell-svar",
        }
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
        coerced = _pre_pmesii not in (None, "", "none") or _pre_tessoc not in (
            None,
            "",
            "none",
        )
        v["pmesii"] = "none"
        v["tessoc"] = "none"
        if coerced:
            log.warning(
                "triage_score enriched ccir=none with non-'none' pmesii/tessoc; "
                "coercing to 'none' (pre-coercion: pmesii=%r tessoc=%r). "
                "Likely cause: qwen36 drift away from ccir.md's rule "
                '\'"none" if ccir is "none"\'.',
                _pre_pmesii,
                _pre_tessoc,
            )
    else:
        # ensure enrichment fields always present (LLM may omit them)
        v.setdefault("pmesii", "none")
        v.setdefault("tessoc", "none")
    # derive bucket for the Fever loop: CCIR match = keep, else skip
    ccir = ccir_lower
    v["bucket"] = (
        "skip"
        if ccir == "none"
        else ("read" if v.get("cnr") == "I" or v.get("score", 0) >= 7 else "maybe")
    )
    return {**it, **v}


SAMPLE = [
    # PIR-6: OSINT & etterforskning
    {
        "title": "Bellingcat identifies GRU officer behind Skripal attack via passport leak",
        "source": "Bellingcat",
        "summary": "Open-source investigators traced a GRU colonel to the Novichok attack using leaked Russian passport records and travel data.",
    },
    # SIR-1: Midtøsten & US-Iran
    {
        "title": "IRGC seizes oil tanker in Strait of Hormuz amid rising tensions",
        "source": "Crisis Group",
        "summary": "Iran's Revolutionary Guard boarded and detained a commercial vessel in the Strait of Hormuz, escalating US-Iran maritime standoff.",
    },
    # SIR-2: Sport — VM 2026
    {
        "title": "Mass protests expected at 2026 World Cup over US immigration policy",
        "source": "BBC Sport Football",
        "summary": "Activist groups announce coordinated demonstrations at FIFA World Cup 2026 venues to protest US border and immigration enforcement.",
    },
    # FFIR-3: Egen teknologikapabilitet
    {
        "title": "Run Claude Code Locally on a Mac: 65 tok/s with 4-bit Qwen3.6-27B + DFlash",
        "source": "Medium",
        "summary": "Speculative decoding to run Claude Code on local Qwen on a Mac.",
    },
    # none: irrelevant
    {
        "title": "L'Oréal Builds AI Beauty Engine with OpenAI",
        "source": "MyClaw",
        "summary": "L'Oréal cuts production cost 40%, 50k marketing assets.",
    },
    # none: irrelevant
    {
        "title": "MAMMOTION robotic lawn mowers on sale for Prime Day",
        "source": "HowToGeek",
        "summary": "Sponsored. Up to $1059 off robotic mowers.",
    },
    # PIR-4: Hybrid- & cybertrusler
    {
        "title": "Suspected sabotage cuts undersea cable between Norway and Finland",
        "source": "NRK",
        "summary": "An undersea fiber optic cable in the Barents Sea was severed overnight; Norwegian authorities suspect deliberate sabotage.",
    },
    # FFIR-1: Norsk forsvar & sikkerhetspolitikk
    {
        "title": "Norway orders 52 Leopard 2A7 tanks in largest defence purchase in decades",
        "source": "Forsvarets forum",
        "summary": "The Norwegian government approved a NOK 19 billion procurement of German Leopard 2A7 main battle tanks for the Army.",
    },
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

    scored = sorted(
        (score_item(it) for it in items), key=lambda x: x.get("score", 0), reverse=True
    )

    if args.json:
        print(json.dumps(scored, indent=2))
        return

    icon = {"read": "🔥", "maybe": "🤔", "skip": "🗑️"}
    print("# InfoTriage digest\n")
    for it in scored:
        print(f"{icon.get(it.get('bucket'),'•')} **[{it.get('score')}] {it['title']}**")
        print(f"    {it.get('source','')} — {it.get('why','')}\n")


if __name__ == "__main__":
    main()
