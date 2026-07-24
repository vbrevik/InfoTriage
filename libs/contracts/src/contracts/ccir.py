"""CCIR registry — the single source of truth for Commander's Critical
Information Requirements (PIR / FFIR / SIR).

Before this module, a CCIR was defined across ~8 sites that drifted
independently (scorer prompt, two CCIR_ORDER literals, the COP filter set,
ccir.md prose + tables, feeds.opml groups, tests). Everything now derives from
`CCIR` below:

  - CCIR_ORDER / COP_CCIR / build_scorer_block() / active_ccir_enum()  → runtime,
    imported by apps/triage and apps/brief. Cannot drift.
  - render_feeds_opml_groups()                                         → generated
    into feeds.opml by `make ccir-sync`, guarded by test_ccir_registry_sync.py.
  - ccir.md stays hand-authored prose but is consistency-checked against this
    registry (ids + PMESII/TESSOC trailers) by the same test.

Retire a finished requirement (e.g. WC2026) by setting `active=False` — it stays
in the registry for history / re-activation but leaves every derivation.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FeedSpec:
    """One RSS source inside a CCIR-owned feeds.opml group."""

    text: str
    xml_url: str
    html_url: str = ""
    warn: bool = False  # renders the ⚠️ marker after the title


@dataclass(frozen=True)
class Example:
    """A worked few-shot example for the scorer prompt, tagged by the CCIR it
    demonstrates ('none' for the negative example). Auto-pruned when its CCIR
    retires."""

    title: str
    ccir: str
    cnr: str
    pmesii: str
    tessoc: str
    score: int
    why: str


@dataclass(frozen=True)
class CCIRSpec:
    id: str  # "PIR-1"
    title: str  # SAB section title — "Russland / Ukraina"
    scorer_line: str  # prompt quick-ref body (after the "id title — ")
    cop: bool  # True = Common Operational Picture; False = CIP
    pmesii: tuple[str, ...]  # associated operational domains (ccir.md trailer)
    tessoc: tuple[str, ...]  # associated threat actors (ccir.md trailer)
    feeds: tuple[FeedSpec, ...] = ()  # CCIR-owned feeds.opml group (SIRs today)
    active: bool = True  # False = retired


# ─────────────────────────────────────────────────────────────────────────────
# THE REGISTRY. Order here is the canonical SAB render order.
# ─────────────────────────────────────────────────────────────────────────────
CCIR: list[CCIRSpec] = [
    CCIRSpec(
        id="PIR-1",
        title="Russland / Ukraina",
        scorer_line="krig, frontlinjer, våpenstøtte, sanksjoner",
        cop=False,
        pmesii=("Military", "Economic"),
        tessoc=("Espionage", "Sabotage", "Subversion"),
    ),
    CCIRSpec(
        id="PIR-2",
        title="Nordområdene & Arktis",
        scorer_line="Svalbard, ubåter, GIUK-gap, nordlig sjørute",
        cop=False,
        pmesii=("Military", "Infrastructure"),
        tessoc=("Espionage", "Sabotage"),
    ),
    CCIRSpec(
        id="PIR-3",
        title="NATO & europeisk sikkerhet",
        scorer_line="toppmøter, styrkeoppbygging, østflanken",
        cop=True,
        pmesii=("Political", "Military"),
        tessoc=("Subversion", "Espionage"),
    ),
    CCIRSpec(
        id="PIR-4",
        title="Hybrid- & cybertrusler",
        scorer_line=(
            "sabotasje, påvirkning, cyberangrep + infrastrukturpostur "
            "(kabler, energinett, LNG, nordlig sjørute, arktisk logistikk, GIUK)"
        ),
        cop=False,
        pmesii=("Information", "Infrastructure"),
        tessoc=("Sabotage", "Subversion", "Espionage"),
    ),
    CCIRSpec(
        id="PIR-5",
        title="Stormaktsrivalisering",
        scorer_line="Kina, USAs vendinger med strategisk vekt for Europa/Norden",
        cop=False,
        pmesii=("Political", "Economic"),
        tessoc=("Espionage", "Subversion"),
    ),
    CCIRSpec(
        id="PIR-6",
        title="OSINT & etterforskning",
        scorer_line="krigsforbrytelser, sanksjonsomgåelse, aktør-identifisering (Bellingcat, OCCRP)",
        cop=False,
        pmesii=("Information",),
        tessoc=("Organized Crime", "Espionage", "Sabotage"),
    ),
    CCIRSpec(
        id="SIR-1",
        title="Midtøsten & US-Iran",
        scorer_line="IRGC, proxyer, atomprogram, sanksjonspress (tidsavgrenset)",
        cop=False,
        pmesii=("Military", "Political", "Economic"),
        tessoc=("Terror", "Sabotage", "Espionage"),
        feeds=(
            FeedSpec(
                "Crisis Group",
                "https://www.crisisgroup.org/rss.xml",
                "https://www.crisisgroup.org/",
            ),
            FeedSpec(
                "Al-Monitor",
                "https://www.al-monitor.com/rss",
                "https://www.al-monitor.com/",
            ),
            FeedSpec(
                "FDD · Long War Journal",
                "https://www.longwarjournal.org/feed",
                "https://www.longwarjournal.org/",
            ),
            FeedSpec(
                "US State Dept",
                "https://www.state.gov/rss-feed/department-press-bureau/department-of-state/feed",
                "https://www.state.gov/",
                warn=True,
            ),
        ),
    ),
    CCIRSpec(
        id="SIR-2",
        title="Sport — VM 2026 (FIFA)",
        scorer_line="sikkerhets-/geopolitisk dimensjon; CARVE-OUT løfter over CNR-Routine",
        cop=True,
        pmesii=("Political", "Social", "Infrastructure"),
        tessoc=("Terror", "Organized Crime", "Subversion"),
        feeds=(
            FeedSpec(
                "BBC Sport Football",
                "https://feeds.bbci.co.uk/sport/football/rss.xml",
                "https://www.bbc.com/sport/football",
            ),
            FeedSpec(
                "ESPN FC",
                "https://www.espn.com/espn/rss/soccer/news",
                "https://www.espn.com/soccer/",
                warn=True,
            ),
            FeedSpec(
                "Reuters Sports",
                "https://www.reutersagency.com/feed/?best-topics=sports&post_type=best",
                "https://www.reutersagency.com/",
                warn=True,
            ),
            FeedSpec(
                "Google News · WC2026",
                "https://news.google.com/rss/search?q=FIFA+World+Cup+2026&hl=en",
                "https://news.google.com/search?q=FIFA+World+Cup+2026",
            ),
        ),
    ),
    CCIRSpec(
        id="SIR-3",
        title="NATO-toppmøtet i Ankara",
        # NB: SIR-3 was missing from the scorer quick-ref AND the JSON enum
        # before the registry (a real drift bug — the scorer could never emit
        # SIR-3). Deriving from the registry fixes it.
        scorer_line="Ankara-toppmøtet: agenda, vedtak, deltakelse, sikkerhetsopplegg (tidsavgrenset)",
        cop=True,
        pmesii=("Political", "Military"),
        tessoc=("Terror", "Subversion"),
    ),
    CCIRSpec(
        id="FFIR-1",
        title="Norsk forsvar & sikkerhetspolitikk",
        scorer_line="Stortinget, Forsvaret, beredskap, E-tjenesten",
        cop=True,
        pmesii=("Military", "Political"),
        tessoc=("Espionage", "Sabotage"),
    ),
    CCIRSpec(
        id="FFIR-2",
        title="Norsk politikk & samfunn",
        scorer_line="strategisk/nasjonal betydning",
        cop=True,
        pmesii=("Political", "Social"),
        tessoc=("Subversion",),
    ),
    CCIRSpec(
        id="FFIR-3",
        title="Egen teknologikapabilitet",
        scorer_line=(
            "lokal LLM-kjøring på egen maskin — oMLX, MLX (alle varianter), Ollama, "
            "LM Studio, vLLM og liknende runtimes, kvantisering, AI-agenter/verktøy, "
            "DFIR, Rust, homelab og selvhostet tooling (f.eks. ngrok-tunnel), egen "
            "NVIDIA-stack (DGX Spark / GB10 Grace Blackwell / CUDA). Spark = egen boks → FFIR-3"
        ),
        cop=True,
        pmesii=("Information",),
        tessoc=("Espionage", "Sabotage"),
    ),
    CCIRSpec(
        id="FFIR-4",
        title="Frontier AI & LLM-landskap",
        scorer_line=(
            "det EKSTERNE frontier-AI-landskapet — modellslipp og -nyheter "
            "(Kimi, GPT, Gemini, Claude, Qwen, Llama, DeepSeek, Mistral), "
            "open-source-modeller, benchmarks/leaderboards, agent-rammeverk, "
            "AI-lab-utvikling (til forskjell fra FFIR-3: egen lokal kjøring)"
        ),
        cop=True,
        pmesii=("Information",),
        tessoc=("Espionage",),
    ),
]


# Prompt-global worked examples, tagged by the CCIR each demonstrates so a
# retired CCIR's examples drop out of the prompt automatically.
WORKED_EXAMPLES: list[Example] = [
    Example(
        "Bellingcat identifies Russian officer behind Bucha massacre using phone metadata",
        "PIR-6",
        "II",
        "Information",
        "Espionage",
        8,
        "OSINT-identifisering av krigsforbryter",
    ),
    Example(
        "OCCRP: Shell companies helped oligarchs evade EU sanctions",
        "PIR-6",
        "II",
        "Economic",
        "Organized Crime",
        7,
        "Sanksjonsomgåelse via skallselskaper",
    ),
    Example(
        "IRGC-linked militia launches rockets at US base in Syria",
        "SIR-1",
        "I",
        "Military",
        "Terror",
        9,
        "IRGC-proxy angriper amerikansk base",
    ),
    Example(
        "Iran enriches uranium to 84% — IAEA report",
        "SIR-1",
        "I",
        "Military",
        "Espionage",
        9,
        "Atomprogram-oppgradering, høy beredskap",
    ),
    Example(
        "FIFA confirms World Cup 2026 will use expanded 48-team format",
        "SIR-2",
        "II",
        "Social",
        "none",
        5,
        "VM 2026 format-oppdatering",
    ),
    Example(
        "Threat of mass protests at US World Cup venues over immigration policy",
        "SIR-2",
        "II",
        "Social",
        "Terror",
        7,
        "Protest-trussel mot VM-arenaer",
    ),
    Example(
        "NATO summit agrees 2% GDP defence spending floor",
        "PIR-3",
        "II",
        "Political",
        "none",
        7,
        "NATO-toppmøte, forsvarsbudsjetter",
    ),
    Example(
        "Kimi K3 open-source model tops coding benchmarks, rattles US AI stocks",
        "FFIR-4",
        "II",
        "Information",
        "none",
        6,
        "Frontier open-source-modell, benchmark-gjennombrudd",
    ),
    Example(
        "Running LM Studio with a 70B model on a 64GB Mac",
        "FFIR-3",
        "II",
        "Information",
        "none",
        5,
        "Egen lokal AI-kjøring (LM Studio / Mac)",
    ),
    Example(
        "Sony releases new PlayStation update",
        "none",
        "none",
        "none",
        "none",
        0,
        "Forbrukerteknologi, ingen CCIR",
    ),
]

# Disambiguation guide lines, tagged with the CCIRs each involves. A line drops
# out of the prompt when any CCIR it references is retired.
DISAMBIGUATION: list[tuple[tuple[str, ...], str]] = [
    (
        ("PIR-5", "SIR-1"),
        "PIR-5 vs SIR-1: if the core subject is Iran, IRGC, or Middle East escalation → SIR-1. If the item is about great-power dynamics (US-China, US global posture) where the Middle East is only context → PIR-5.",
    ),
    (
        ("PIR-1", "PIR-6"),
        "PIR-1 vs PIR-6: if the item is an OSINT investigation (identifying actors, tracing networks, sanctions evasion) about Russia/Ukraine → PIR-6. Straight war reporting, battlefield updates, or policy announcements → PIR-1.",
    ),
    (
        ("PIR-6", "SIR-2"),
        "PIR-6 vs SIR-2: if the item is an investigation into sports corruption/fraud in FIFA context → PIR-6. If it is about security, protests, boycotts, or geopolitical tensions around VM 2026 specifically → SIR-2.",
    ),
    (
        ("FFIR-3", "PIR-4"),
        "FFIR-3 vs PIR-4: cybersecurity of Norwegian critical infra → PIR-4. Building your own local LLM / DFIR lab / homelab → FFIR-3.",
    ),
    (
        ("FFIR-3", "FFIR-4"),
        "FFIR-3 vs FFIR-4: RUNNING or building AI on your OWN machine — oMLX, MLX, Ollama, LM Studio, vLLM, your own Spark/GB10 box, local agents, quantization → FFIR-3. NEWS about the EXTERNAL frontier landscape — model releases (Kimi K3, GPT, Gemini, Claude, Qwen, Llama, DeepSeek, Mistral), benchmarks/leaderboards, open-source drops, AI-lab developments → FFIR-4. A frontier open-source model you could ALSO run locally is FFIR-4 when the item is about the release/benchmark, FFIR-3 when it is about you running it.",
    ),
    (
        ("SIR-2",),
        'Sport (general) vs SIR-2: regular sport coverage with no security/political angle → "none". VM 2026 security, protests, boycott, terrortrussel, or political controversy → SIR-2.',
    ),
]


# ─────────────────────────────────────────────────────────────────────────────
# Derivations (runtime — cannot drift)
# ─────────────────────────────────────────────────────────────────────────────
def active_specs() -> list[CCIRSpec]:
    return [c for c in CCIR if c.active]


def spec(ccir_id: str) -> CCIRSpec:
    for c in CCIR:
        if c.id == ccir_id:
            return c
    raise KeyError(ccir_id)


CCIR_ORDER: list[tuple[str, str]] = [(c.id, c.title) for c in active_specs()]
COP_CCIR: frozenset[str] = frozenset(c.id for c in active_specs() if c.cop)


def active_ccir_enum() -> str:
    """The JSON-schema enum body: 'PIR-1 | … | none'."""
    return " | ".join(c.id for c in active_specs()) + " | none"


def build_quickref() -> str:
    """The 'Tier quick-reference' block of the scorer prompt (active CCIRs)."""
    lines = ["Tier quick-reference (full descriptions in ccir.md above):"]
    for c in active_specs():
        lines.append(f"- {c.id} {c.title} — {c.scorer_line}")
    lines.append('- "none" if the item answers no CCIR at all.')
    return "\n".join(lines)


def build_examples_and_guide() -> str:
    """The disambiguation guide + worked examples of the scorer prompt.

    Returns FINAL text with single braces (`{"ccir": …}`) because callers
    interpolate this as a plain variable into an f-string — the content is NOT
    re-processed for f-string escapes, so the braces must already be single.
    A line/example drops out when any CCIR it references is inactive.
    """
    ids = {c.id for c in active_specs()}

    disamb = [d for involved, d in DISAMBIGUATION if all(i in ids for i in involved)]
    guide = ["Disambiguation guide — when an item could match multiple tiers:"]
    guide += [f"- {d}" for d in disamb]

    examples = [e for e in WORKED_EXAMPLES if e.ccir == "none" or e.ccir in ids]
    ex_lines = ["", "Worked examples:"]
    for n, e in enumerate(examples, 1):
        payload = (
            f'{{"ccir": "{e.ccir}", "cnr": "{e.cnr}", "pmesii": "{e.pmesii}", '
            f'"tessoc": "{e.tessoc}", "score": {e.score}, "why": "{e.why}"}}'
        )
        ex_lines.append(f'{n}. "{e.title}"')
        ex_lines.append(f"   → {payload}")

    return "\n".join(guide + ex_lines)


def build_scorer_block() -> str:
    """Convenience aggregate of the CCIR-specific prompt sections (quick-ref +
    guide + examples). triage_score.py interpolates the two halves separately to
    keep the PMESII/TESSOC framework prose between them, but tests and any
    single-block consumer can use this."""
    return build_quickref() + "\n\n" + build_examples_and_guide()


def render_feeds_opml_groups() -> str:
    """Render the CCIR-owned <outline> groups for feeds.opml (only CCIRs that
    carry `feeds` — the SIRs today). Written between the ccir markers in
    apps/opml/feeds.opml by scripts/ccir_sync.py; guarded by the sync test."""
    out: list[str] = []
    for c in active_specs():
        if not c.feeds:
            continue
        label = _xml_escape(f"{c.title.replace(' (FIFA)', '')} ({c.id})")
        out.append(f'    <outline text="{label}" title="{label}">')
        for fspec in c.feeds:
            title = fspec.text + (" ⚠️" if fspec.warn else "")
            t = _xml_escape(title)
            out.append(
                f'      <outline type="rss" text="{t}" title="{t}" '
                f'xmlUrl="{_xml_escape(fspec.xml_url)}" htmlUrl="{_xml_escape(fspec.html_url)}"/>'
            )
        out.append("    </outline>")
    return "\n".join(out)


def _xml_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
