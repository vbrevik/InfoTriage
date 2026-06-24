# trimail CCIR — Commander's Critical Information Requirements

This file IS the triage brain. The scorer reads it and tags every item with the
CCIR it answers and a CNR notification level. Edit freely — add/remove/retune.

## PIR — Priority Intelligence Requirements (eksternt: verden, trussel, miljø)

- **PIR-1 Russland/Ukraina** — krigsutvikling, frontlinjer, eskalering/de-eskalering,
  vestlig våpenstøtte, sanksjoner, russisk mobilisering og økonomi.
  `PMESII: Military, Economic` · `TESSOC: Equipment, Skills, Time`
- **PIR-2 Nordområdene & Arktis** — militær aktivitet, russisk og alliert
  tilstedeværelse, Svalbard, ubåt-/maritim aktivitet, GIUK-gapet, nordlig sjørute.
  `PMESII: Military, Infrastructure` · `TESSOC: Space, Time`
- **PIR-3 NATO & europeisk sikkerhet** — alliansevedtak, toppmøter, styrkeoppbygging,
  forsvarsbudsjetter, Sverige/Finland, østflanken.
  `PMESII: Political, Military` · `TESSOC: Organization, Skills`
- **PIR-4 Hybrid- & cybertrusler** — sabotasje mot infrastruktur (sjøkabler, kraft,
  gass), påvirknings-/informasjonsoperasjoner, cyberangrep — særlig mot Norge/Norden.
  **Infrastrukturpostur:** også strategisk infrastrukturutvikling — nye kabeltraseer,
  energinettkapasitet, LNG-terminaler, nordlig sjørute-utvikling, arktisk logistikk,
  GIUK-gap-overvåking, havne- og forsyningsbasestatus. Både trusselbildet *og*
  den sivile/militære infrastrukturens sårbarhet og utvikling.
  `PMESII: Information, Infrastructure` · `TESSOC: Communications, Equipment, Space`
- **PIR-5 Stormaktsrivalisering** — Kina, USAs sikkerhetspolitikk og vendinger som
  påvirker europeisk/nordisk sikkerhet, Midtøsten når det har strategisk vekt.
  `PMESII: Political, Economic` · `TESSOC: Organization, Communications`

- **PIR-6 OSINT & etterforskning** — åpne kilder for
  krigsforbrytelsesdokumentasjon, sanksjonsomgåelse, identifisering av aktører
  (skip/tog/fly/enheter), kjemiske våpen-påstander, samt langvarige
  granskingssaker i sivil/politisk sfære. Primær kildegruppe: Bellingcat, OCCRP.
  Tett kobling til PIR-1 (Russland/Ukraina), PIR-4 (Hybrid/sabotasje) og
  PIR-5 (Stormakter); overlap er forventet og en sak kan trigge flere PIR-er.
  `PMESII: Information` · `TESSOC: Communications, Skills`

## FFIR — Friendly Force Information Requirements (eget: Norge, hjemmebane)

- **FFIR-1 Norsk forsvar & sikkerhetspolitikk** — regjerings-/stortingsvedtak, forsvars-
  budsjett, anskaffelser, Forsvaret, totalforsvar, beredskap, etterretningstjenestene.
  `PMESII: Military, Political` · `TESSOC: Organization, Skills, Equipment`
- **FFIR-2 Norsk politikk & samfunn** — saker av strategisk/nasjonal betydning
  (ikke kjendis/sport/livsstil).
  `PMESII: Political, Social` · `TESSOC: Organization, Communications`
- **FFIR-3 Egen teknologikapabilitet** — lokale LLM-er på Mac (Qwen/MLX/Ollama,
  kvantisering, tok/s), AI-agenter, Claude Code, skills/workflows, sikkerhet/pentest/
  DFIR, Rust, self-hosting/homelab.
  `PMESII: Information` · `TESSOC: Skills, Communications`

## SIR — Specific Intelligence Requirements (tidsavgrenset, oppheves ved endt hendelse)

- **SIR-1 Midtøsten & US-Iran (IRGC, proliferasjon, atomprogram)** — eskalering
  USA/Israel ↔ Iran; IRGC-proxy-aktivitet (Hizbollah, Houthi, militser i Irak/Syria);
  atomprogram-status; sanksjonspress og effekten på europeisk energi/sikkerhet.
  Tidsavgrenset: aktiv så lenge den diplomatiske/militære spenningskurven er skarp.
  Kildegruppe: Crisis Group, Al-Monitor, FDD Long War Journal, US State Dept.
  `PMESII: Military, Political, Economic` · `TESSOC: Equipment, Organization, Time`
- **SIR-2 Sport — VM 2026 (FIFA)** — sikkerhets- og geopolitisk dimensjon ved
  Fotball-VM 2026 (vertsnasjoner USA/Canada/Mexico): kritisk infrastruktur, protester
  /boikott, politisk ladede kamper (Iran, Saudi-Arabia), terrortrusler, store
  kontroverser. **CARVE-OUT**: standard sport er CNR-Routine; VM 2026 er sikkerhets-
  og politikkrelevant — alle saker her eskaleres til PIR (CAT II dagsbrief, eller
  CAT I ved sikkerhetshendelse). Kildegruppe: BBC Sport Football, ESPN FC, Reuters
  Sports, Google News WC2026.
  `PMESII: Political, Social, Infrastructure` · `TESSOC: Organization, Space, Communications`

## CNR — Commander's Notification Requirements (varslingsterskler)

- **CAT I 🚩 — varsle straks**: direkte trussel eller markant eskalering som berører
  Norge, Norden eller Arktis; større militær eskalering i Russland/Ukraina eller
  mellom NATO og motpart; angrep/sabotasje mot norsk eller alliert infrastruktur;
  alvorlig cyberhendelse mot Norge. (Skal aldri drukne i bunken.)
- **CAT II 📋 — dagsbrief**: alt annet som svarer på en CCIR (PIR eller FFIR).
- **Routine — utelat**: svarer ikke på noen CCIR (reklame, kjendis, sport, livsstil,
  generisk PR, ren clickbait). **NB**: `SIR-2 Fotball-VM 2026` er eksplisitt carve-out
  — alle saker fra den kilden eskaleres til PIR (aldri Routine), jf. SIR-seksjonen.

## PMESII — operasjonelle domener (analytisk berikelse)

Hvert saker kan tilordnes én primær PMESII-domene. Disse brukes som et
analytisk berikelseslag på toppen av CCIR — ikke som erstatning.

| Domene | Omfang | Eksempel-CCIR |
|---|---|---|
| **Political** 🏛️ | Diplomati, traktater, regjeringspolitikk, valg, sanksjoner som politisk verktøy | PIR-3, PIR-5, FFIR-2 |
| **Military** ⚔️ | Krig, forsvarsstyrke, troppbevegelser, våpensystemer, militære operasjoner | PIR-1, PIR-2, PIR-3, FFIR-1 |
| **Economic** 💰 | Sanksjonseffekt, handelskrig, budsjetter, finansmarkeder, energimarkeder | PIR-1, PIR-5 |
| **Social** 👥 | Protester, uro, opinion, demografi, kulturelle/sportslige arrangementer med politisk dimensjon | FFIR-2, SIR-2 |
| **Information** 📡 | Cyberoperasjoner, OSINT-etterforskning, propaganda, hybrid påvirkning, mediamanipulering | PIR-4, PIR-6, FFIR-3 |
| **Infrastructure** 🌉 | Undersjøiske kabler, rørledninger, logistikknettverk, kraftnett, transport, maritime ruter | PIR-2, PIR-4, SIR-2 |

NB: En sak kan berøre flere domener, men scoreren velger det éne primære.
PMESII-taggene er LLM-assigned (ikke statisk mapping fra CCIR) fordi PIR-1 f.eks.
kan være Military (frontlinjer) eller Economic (sanksjoner) avhengig av saken.

## TESSOC — operasjonelle variabler (analytisk berikelse)

TESSOC beskriver det operasjonelle miljøet. Sammen med PMESII gir det to
uavhengige analytiske akser per sak.

| Variabel | Omfang | Eksempel-CCIR |
|---|---|---|
| **Time** ⏳ | Tidsfaktorer — sesong, frister, eskaleringsvinduer, tidskritiske hendelser | PIR-1, PIR-2 |
| **Equipment** 🔧 | Våpensystemer, teknologiplattformer, materiell, maskinvare | PIR-1, PIR-4, SIR-1 |
| **Space** 🗺️ | Terrenge, geografi, fysisk miljø, havområder, luftrom, arktiske forhold | PIR-2, PIR-4, SIR-2 |
| **Skills** 🎓 | Evner, trening, beredskap, doktrine, taktikk | PIR-1, PIR-3, PIR-6 |
| **Organization** 🏢 | Kommandostruktur, enhetsoppsett, allianseformasjoner, institusjonelle ordninger | PIR-3, PIR-5, FFIR-1, FFIR-2, SIR-2 |
| **Communications** 📶 | C4ISR, informasjonsflyt, nettverk, mediekanaler, signaler | PIR-4, PIR-5, PIR-6, FFIR-2, SIR-2 |

NB: En sak velger én primær TESSOC-variabel, LLM-assigned.
