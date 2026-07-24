# InfoTriage CCIR — Commander's Critical Information Requirements

This file is the canonical taxonomy. The scorer's LLM prompt inlines the full
file (`score/triage_score.py:score_item`'s CCIR section) and layers on a
disambiguation guide + worked examples so the model can route items — so
editing here changes triage. Carve-out intent (se SIR-2 / CNR Routine NB
nedenfor) utføres av scorer-promptens regler + worked examples, ikke av en
hardkodet parser mot denne filen. Edit freely — add/remove/retune.

## PIR — Priority Intelligence Requirements (eksternt: verden, trussel, miljø)

- **PIR-1 Russland/Ukraina** — krigsutvikling, frontlinjer, eskalering/de-eskalering,
  vestlig våpenstøtte, sanksjoner, russisk mobilisering og økonomi.
  `PMESII: Military, Economic` · `TESSOC: Espionage, Sabotage, Subversion`
- **PIR-2 Nordområdene & Arktis** — militær aktivitet, russisk og alliert
  tilstedeværelse, Svalbard, ubåt-/maritim aktivitet, GIUK-gapet, nordlig sjørute.
  `PMESII: Military, Infrastructure` · `TESSOC: Espionage, Sabotage`
- **PIR-3 NATO & europeisk sikkerhet** — alliansevedtak, toppmøter, styrkeoppbygging,
  forsvarsbudsjetter, Sverige/Finland, østflanken.
  `PMESII: Political, Military` · `TESSOC: Subversion, Espionage`
- **PIR-4 Hybrid- & cybertrusler** — sabotasje mot infrastruktur (sjøkabler, kraft,
  gass), påvirknings-/informasjonsoperasjoner, cyberangrep — særlig mot Norge/Norden.
  **Infrastrukturpostur:** også strategisk infrastrukturutvikling — nye kabeltraseer,
  energinettkapasitet, LNG-terminaler, nordlig sjørute-utvikling, arktisk logistikk,
  GIUK-gap-overvåking, havne- og forsyningsbasestatus. Både trusselbildet *og*
  den sivile/militære infrastrukturens sårbarhet og utvikling.
  `PMESII: Information, Infrastructure` · `TESSOC: Sabotage, Subversion, Espionage`
- **PIR-5 Stormaktsrivalisering** — Kina, USAs sikkerhetspolitikk og vendinger som
  påvirker europeisk/nordisk sikkerhet, Midtøsten når det har strategisk vekt.
  `PMESII: Political, Economic` · `TESSOC: Espionage, Subversion`

- **PIR-6 OSINT & etterforskning** — åpne kilder for
  krigsforbrytelsesdokumentasjon, sanksjonsomgåelse, identifisering av aktører
  (skip/tog/fly/enheter), kjemiske våpen-påstander, samt langvarige
  granskingssaker i sivil/politisk sfære. Primær kildegruppe: Bellingcat, OCCRP.
  Tett kobling til PIR-1 (Russland/Ukraina), PIR-4 (Hybrid/sabotasje) og
  PIR-5 (Stormakter); overlap er forventet og en sak kan trigge flere PIR-er.
  `PMESII: Information` · `TESSOC: Organized Crime, Espionage, Sabotage`

## FFIR — Friendly Force Information Requirements (eget: Norge, hjemmebane)

- **FFIR-1 Norsk forsvar & sikkerhetspolitikk** — regjerings-/stortingsvedtak, forsvars-
  budsjett, anskaffelser, Forsvaret, totalforsvar, beredskap, etterretningstjenestene.
  `PMESII: Military, Political` · `TESSOC: Espionage, Sabotage`
- **FFIR-2 Norsk politikk & samfunn** — saker av strategisk/nasjonal betydning
  (ikke kjendis/sport/livsstil).
  `PMESII: Political, Social` · `TESSOC: Subversion`
- **FFIR-3 Egen teknologikapabilitet** — *egen* plattform og spark-stack for
  lokal AI og analysearbeid:
  - **Mac-basert**: Qwen/MLX/Ollama, kvantisering, lokale Claude Code-arbeidsflyter,
    AI-agenter og skills, Rust-verktøy, homelab, DFIR/pentest.
  - **NVIDIA-stack**: **DGX Spark (GB10 Grace Blackwell)** plattformstatus og releaser;
    **GB10-brikke**-spesifikasjoner og supply; **CUDA-versjoner** og toolchain-endringer
    (`nvidia-smi`, driver-matrise, breaking changes mellom CUDA 12.x og 13.x); ytelse
    per token (tok/s) per CUDA-versjon.
  - **NB**: DGX Spark- og GB10-saker er FFIR-3 (relevant for *egen plattform*),
    ikke noen PIR — de er ikke ekstern trussel, men *hardware- og software-stack
    for lokal AI*. Bruk FFIR-3 også for konkurranse-sammenlikninger («Mac vs
    DGX Spark», «Apple Silicon vs Grace Blackwell») så lenge vinklingen er
    «hva kan *jeg* kjøre lokalt». Hvis vinklingen er geopolitisk (f.eks.
    Kinas chip-exports, USAs eksportkontroll), faller saken tilbake til PIR-5.
  `PMESII: Information` · `TESSOC: Espionage, Sabotage`
- **FFIR-4 Frontier AI & LLM-landskap** — det *eksterne* frontier-AI-landskapet:
  modellslipp og -nyheter (Kimi, GPT, Gemini, Claude, Qwen, Llama, DeepSeek,
  Mistral), open-source-modeller, benchmarks/leaderboards, agent-rammeverk og
  AI-lab-utvikling. **Skille mot FFIR-3**: FFIR-3 er *egen lokal kjøring* på
  egen maskin (oMLX, MLX, Ollama, LM Studio, vLLM, egen DGX Spark/GB10); FFIR-4
  er *hva frontier-labbene slipper* — også når modellen er open-source og *kan*
  kjøres lokalt: selve slippet/benchmarken er FFIR-4, det å kjøre den selv er
  FFIR-3.
  `PMESII: Information` · `TESSOC: Espionage`

## SIR — Specific Intelligence Requirements (tidsavgrenset, oppheves ved endt hendelse)

- **SIR-1 Midtøsten & US-Iran (IRGC, proliferasjon, atomprogram)** — eskalering
  USA/Israel ↔ Iran; IRGC-proxy-aktivitet (Hizbollah, Houthi, militser i Irak/Syria);
  atomprogram-status; sanksjonspress og effekten på europeisk energi/sikkerhet.
  Tidsavgrenset: aktiv så lenge den diplomatiske/militære spenningskurven er skarp.
  Kildegruppe: Crisis Group, Al-Monitor, FDD Long War Journal, US State Dept.
  `PMESII: Military, Political, Economic` · `TESSOC: Terror, Sabotage, Espionage`
- **SIR-2 Sport — VM 2026 (FIFA)** — sikkerhets- og geopolitisk dimensjon ved
  Fotball-VM 2026 (vertsnasjoner USA/Canada/Mexico): kritisk infrastruktur, protester
  /boikott, politisk ladede kamper (Iran, Saudi-Arabia), terrortrusler, store
  kontroverser. **Carve-out-intent**: VM 2026-hits med sikkerhets-/politisk
  signal (protester, boikott, terrortrussel, politisk kontrovers) eskaleres til
  SIR-2 (CAT II dagsbrief) eller CAT I ved konkret sikkerhetshendelse —
  sammenliknet med ren sportsdekning som forblir CNR-Routine. Carve-out er
  utført av `score/triage_score.py:score_item`-promptens disambigueringsguide
  "Sport vs SIR-2" og worked examples (jf. "FIFA bekrefter utvidet
  48-lagsformat" → SIR-2 score 5; "Trussel om masseprotester ved VM-arenaer"
  → SIR-2 score 7) — ikke av en hardkodet parser mot denne filen. Dersom
  SIR-2-seksjonen utvides eller carve-out-regelen endres, oppdater også
  scorer-promptens regel + eksempler i `triage_score.py:score_item`. Kildegruppe:
  BBC Sport Football, ESPN FC, Reuters Sports, Google News WC2026.
  `PMESII: Political, Social, Infrastructure` · `TESSOC: Terror, Organized Crime, Subversion`
- **SIR-3 NATO-toppmøtet i Ankara (Tyrkia)** — alt om toppmøtet: agenda, vedtak
  og kommunikeer; deltakelse/fravær av stats- og regjeringssjefer; Tyrkias
  vertskapsrolle og posisjonering (Sverige/Finland-relasjoner, S-400/F-35,
  Bosporos/Svartehavet); sikkerhetsopplegg, protester eller trusler rundt
  møtet; utfall som berører Norge, nordflanken eller Arktis. Overlapper PIR-3
  (alliansevedtak) — bruk SIR-3 for saker spesifikt om Ankara-toppmøtet,
  PIR-3 for generell NATO-utvikling. Tidsavgrenset: aktiv til toppmøtet er
  avsluttet og oppfølgingsvedtak er rapportert.
  Kildegruppe: NATO.int, Reuters, Anadolu/AA, Al-Monitor, Hurriyet Daily News.
  `PMESII: Political, Military` · `TESSOC: Terror, Subversion`

## CNR — Commander's Notification Requirements (varslingsterskler)

- **CAT I 🚩 — varsle straks**: direkte trussel eller markant eskalering som berører
  Norge, Norden eller Arktis; større militær eskalering i Russland/Ukraina eller
  mellom NATO og motpart; angrep/sabotasje mot norsk eller alliert infrastruktur;
  alvorlig cyberhendelse mot Norge. (Skal aldri drukne i bunken.)
- **CAT II 📋 — dagsbrief**: alt annet som svarer på en CCIR (PIR eller FFIR).
- **Routine — utelat**: svarer ikke på noen CCIR (reklame, kjendis, sport, livsstil,
  generisk PR, ren clickbait). **NB**: VM 2026-saker med sikkerhets-/politisk
  signal eskaleres per SIR-2-carve-out (se SIR-2 over) — men standard
  BBC Sport Football / ESPN FC / Reuters Sports-dekning uten slikt signal
  forblir CNR-Routine. Ikke alle saker fra disse kildene eskaleres; kun de
  med sikkerhets-/politisk vinkling.

## PMESII — operasjonelle domener (analytisk berikelse)

PMESII kategoriserer domener i det operasjonelle miljøet (operational
environment domains). Rammeverket er etablert i NATO fellesdoktrine:
**Political, Military, Economic, Social, Infrastructure, Information** (NATO
*Allied Joint Publication* 01, *Allied Joint Doctrine*; se også AJP-5, *Allied
Joint Doctrine for Planning*). Disse brukes som et analytisk berikelseslag på
toppen av CCIR — ikke som erstatning.

> 💡 **Vedlikeholdere:** Se
> [`.planning/research/pmesii-hybrid-definitions.md`](.planning/research/pmesii-hybrid-definitions.md)
> for bakgrunn om hvorfor definisjonene er *hybride* (NATO-doktrine + konkrete
> OSINT-eksempler) og hvordan de ble validert.

| Domene | Omfang | Eksempel-CCIR |
|---|---|---|
| **Political** 🏛️ | Maktstrukturer og diplomati; traktater, regjeringspolitikk, valg, sanksjoner som politisk verktøy | PIR-3, PIR-5, FFIR-2 |
| **Military** ⚔️ | Forsvarskapabiliteter og krigføring; forsvarsstyrke, troppbevegelser, våpensystemer, militære operasjoner | PIR-1, PIR-2, PIR-3, FFIR-1 |
| **Economic** 💰 | Ressursproduksjon og markeder; sanksjonseffekt, handelskrig, budsjetter, finansmarkeder, energimarkeder | PIR-1, PIR-5 |
| **Social** 👥 | Demografisk og kulturell sammensetning; protester, uro, opinion, kulturelle/sportslige arrangementer med politisk dimensjon | FFIR-2, SIR-2 |
| **Information** 📡 | Informasjonsflyt og -systemer; cyberoperasjoner, OSINT-etterforskning, propaganda, hybrid påvirkning, mediamanipulering | PIR-4, PIR-6, FFIR-3 |
| **Infrastructure** 🌉 | Essensielle fasiliteter; undersjøiske kabler, rørledninger, logistikknettverk, kraftnett, transport, maritime ruter | PIR-2, PIR-4, SIR-2 |

NB: En sak kan berøre flere domener, men scoreren velger det éne primære.
PMESII-taggene er LLM-assigned (ikke statisk mapping fra CCIR) fordi PIR-1 f.eks.
kan være Military (frontlinjer) eller Economic (sanksjoner) avhengig av saken.

## TESSOC — trusselaktører (analytisk berikelse)

TESSOC kategoriserer primære trusselaktører og deres metoder. Akronymet er
etablert i britisk/nato militær etterretningsdoktrine: **Terror, Espionage,
Subversion, Sabotage and Organized Crime** (UK *Joint Doctrine Publication*
2-00, *Intelligence, Counter-Intelligence and Security Support to Joint
Operations*; se også Davies & Steward, 2024, "The Trouble with TESSOC",
*Defence Studies*, for en kritisk gjennomgang). InfoTriage bruker TESSOC som
operativt analyserammeverk uavhengig av den akademiske debatten. Sammen med
PMESII gir det to uavhengige analytiske akser per sak.

| Kategori | Omfang | Eksempel-CCIR |
|---|---|---|
| **Terror** 💣 | Terrorisme, voldelig ekstremisme, angrep mot sivile eller symbolske mål. | SIR-1, SIR-2 |
| **Espionage** 🕵️ | Spionasje, etterretningsinnhenting, fordekt informasjonssamling (statlig/ikke-statlig). | PIR-1, PIR-2, PIR-4 |
| **Subversion** 🎭 | Undergraving, påvirkningsoperasjoner, destabilisering, femtekolonne-aktivitet. | PIR-4, PIR-5 |
| **Sabotage** ⚡ | Tilsiktet ødeleggelse eller forstyrrelse av infrastruktur, logistikk eller systemer. | PIR-4, FFIR-1 |
| **Organized Crime** 🏴‍☠️ | Kriminelle nettverk, smugling, hvitvasking, korrupsjon, sanksjonsomgåelse. | PIR-6, SIR-2 |

NB: En sak velger én primær TESSOC-kategori, LLM-assigned.
