# trimail CCIR — Commander's Critical Information Requirements

This file IS the triage brain. The scorer reads it and tags every item with the
CCIR it answers and a CNR notification level. Edit freely — add/remove/retune.

## PIR — Priority Intelligence Requirements (eksternt: verden, trussel, miljø)

- **PIR-1 Russland/Ukraina** — krigsutvikling, frontlinjer, eskalering/de-eskalering,
  vestlig våpenstøtte, sanksjoner, russisk mobilisering og økonomi.
- **PIR-2 Nordområdene & Arktis** — militær aktivitet, russisk og alliert
  tilstedeværelse, Svalbard, ubåt-/maritim aktivitet, GIUK-gapet, nordlig sjørute.
- **PIR-3 NATO & europeisk sikkerhet** — alliansevedtak, toppmøter, styrkeoppbygging,
  forsvarsbudsjetter, Sverige/Finland, østflanken.
- **PIR-4 Hybrid- & cybertrusler** — sabotasje mot infrastruktur (sjøkabler, kraft,
  gass), påvirknings-/informasjonsoperasjoner, cyberangrep — særlig mot Norge/Norden.
- **PIR-5 Stormaktsrivalisering** — Kina, USAs sikkerhetspolitikk og vendinger som
  påvirker europeisk/nordisk sikkerhet, Midtøsten når det har strategisk vekt.

- **PIR-6 OSINT & etterforskning** — åpne kilder for
  krigsforbrytelsesdokumentasjon, sanksjonsomgåelse, identifisering av aktører
  (skip/tog/fly/enheter), kjemiske våpen-påstander, samt langvarige
  granskingssaker i sivil/politisk sfære. Primær kildegruppe: Bellingcat, OCCRP.
  Tett kobling til PIR-1 (Russland/Ukraina), PIR-4 (Hybrid/sabotasje) og
  PIR-5 (Stormakter); overlap er forventet og en sak kan trigge flere PIR-er.

## FFIR — Friendly Force Information Requirements (eget: Norge, hjemmebane)

- **FFIR-1 Norsk forsvar & sikkerhetspolitikk** — regjerings-/stortingsvedtak, forsvars-
  budsjett, anskaffelser, Forsvaret, totalforsvar, beredskap, etterretningstjenestene.
- **FFIR-2 Norsk politikk & samfunn** — saker av strategisk/nasjonal betydning
  (ikke kjendis/sport/livsstil).
- **FFIR-3 Egen teknologikapabilitet** — lokale LLM-er på Mac (Qwen/MLX/Ollama,
  kvantisering, tok/s), AI-agenter, Claude Code, skills/workflows, sikkerhet/pentest/
  DFIR, Rust, self-hosting/homelab.

## SIR — Specific Intelligence Requirements (tidsavgrenset, oppheves ved endt hendelse)

- **SIR-1 Midtøsten & US-Iran (IRGC, proliferasjon, atomprogram)** — eskalering
  USA/Israel ↔ Iran; IRGC-proxy-aktivitet (Hizbollah, Houthi, militser i Irak/Syria);
  atomprogram-status; sanksjonspress og effekten på europeisk energi/sikkerhet.
  Tidsavgrenset: aktiv så lenge den diplomatiske/militære spenningskurven er skarp.
  Kildegruppe: Crisis Group, Al-Monitor, FDD Long War Journal, US State Dept.
- **SIR-2 Sport — VM 2026 (FIFA)** — sikkerhets- og geopolitisk dimensjon ved
  Fotball-VM 2026 (vertsnasjoner USA/Canada/Mexico): kritisk infrastruktur, protester
  /boikott, politisk ladede kamper (Iran, Saudi-Arabia), terrortrusler, store
  kontroverser. **CARVE-OUT**: standard sport er CNR-Routine; VM 2026 er sikkerhets-
  og politikkrelevant — alle saker her eskaleres til PIR (CAT II dagsbrief, eller
  CAT I ved sikkerhetshendelse). Kildegruppe: BBC Sport Football, ESPN FC, Reuters
  Sports, Google News WC2026.

## CNR — Commander's Notification Requirements (varslingsterskler)

- **CAT I 🚩 — varsle straks**: direkte trussel eller markant eskalering som berører
  Norge, Norden eller Arktis; større militær eskalering i Russland/Ukraina eller
  mellom NATO og motpart; angrep/sabotasje mot norsk eller alliert infrastruktur;
  alvorlig cyberhendelse mot Norge. (Skal aldri drukne i bunken.)
- **CAT II 📋 — dagsbrief**: alt annet som svarer på en CCIR (PIR eller FFIR).
- **Routine — utelat**: svarer ikke på noen CCIR (reklame, kjendis, sport, livsstil,
  generisk PR, ren clickbait). **NB**: `SIR-2 Fotball-VM 2026` er eksplisitt carve-out
  — alle saker fra den kilden eskaleres til PIR (aldri Routine), jf. SIR-seksjonen.
