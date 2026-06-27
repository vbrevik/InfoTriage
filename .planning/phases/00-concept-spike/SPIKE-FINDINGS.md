# Phase 0 Concept Spike — Consolidated Findings (SPIKE-FINDINGS.md)

**Phase:** 00-concept-spike
**Closed:** 2026-06-27 (plan 00-07)
**Purpose:** the durable record of the five architectural unknowns (R1–R5). This is the
only durable knowledge product of the spike — the throwaway `.spike/` code and containers
are deleted/torn down at teardown (D-06). Every verdict and raw number here must survive
that deletion.

**SPEC Constraint honoured:** a partial result is recorded **as a partial**, never silently
elevated to a pass (00-SPEC.md → Constraints + Acceptance Criteria). R2, R3, R4 are PARTIAL
and stay PARTIAL below; only R1 is a clean GO; R5 is a DROP-and-BUILD decision.

| Unknown | Topic | Verdict |
|---------|-------|---------|
| R1 | RabbitMQ topology | **GO** |
| R2 | Norwegian semantic dedup | **PARTIAL** (mechanism promising; threshold not yet calibrated) |
| R3 | Postgres entity resolution | **PARTIAL** (mechanism proven; single-language coverage) |
| R4 | Wiki-LLM feasibility | **PARTIAL** (synthesis GO; cross-language synthesis incomplete) |
| R5 | COP / World Monitor | **DROP** WM as engine; **BUILD** native SP-COP |

---

## R1 — RabbitMQ Topology — **GO**

**ADR:** ADR-007. Source: `findings/R1-VERDICT.md` (Plan 00-02).

The InfoTriage AMQP topology was proven end-to-end on the spike broker
(`rabbitmq:3.13-management`, localhost:22060, pika 1.4.1, Python 3.13.5). All three
acceptance legs passed.

**Topology (DLX-first declaration order is mandatory):**

| Order | Resource | Type | Notes |
|-------|----------|------|-------|
| 1 | `infotriage.dlx` | exchange (direct, durable) | Declared before any primary queue references it |
| 2 | `infotriage.dlq` | queue (durable) | Bound to `infotriage.dlx`, routing_key=`dead` |
| 3 | `infotriage.events` | exchange (topic, durable) | Main event bus |
| 4 | `q.triage` | queue (durable, DLX-wired) | rk=`item.ingested` |
| 4 | `q.brief` | queue (durable, DLX-wired) | rk=`verdict.ready` |
| 4 | `q.notify` | queue (durable, DLX-wired) | rk=`sab.published` |
| 4 | `q.ops` | queue (durable, DLX-wired) | rk=`feed.unhealthy` |

**Raw numbers / observed facts:**
- **Round-trip:** message published by service A on `item.ingested` was consumed by service B
  from `q.triage` with correct payload. PASS.
- **4-event-type confirms:** all four routing keys (`item.ingested`, `verdict.ready`,
  `sab.published`, `feed.unhealthy`) published with publisher confirms; all broker-acked with no
  `NackError`/`UnroutableError`. PASS.
- **Dead-letter:** poison message `{"id":"poison-001","__poison__":true,"source":"NRK"}` nacked
  with `requeue=False` → routed via `infotriage.dlx` (rk `dead`) → `infotriage.dlq`, **queue
  depth = 1** within the bounded 5-second poll window. PASS. (`requeue=False` is the correct
  no-requeue-loop mitigation, T-00-R1-01.)

**Caveats carried to ADR-007 / Phase 3:**
- **pika API surface:** publisher confirms use `confirm_delivery()` + exception-on-failure from
  `basic_publish()`. `wait_for_confirms()` seen in online examples does **not** exist in pika 1.4.1.
- **aio-pika for production:** pika `BlockingConnection` is single-threaded; Phase 3 should use
  `aio-pika` with `connect_robust()` (auto-reconnect) + async consumer callbacks.
- **M3 fan-out untested (A4):** multiple consumers per event require a separate queue per
  subscriber (not a shared queue); architecturally straightforward but not exercised in the spike.

---

## R2 — Norwegian Semantic Dedup — **PARTIAL**

**ADR:** feeds Phase 5 dedup infra. Source: `findings/R2-VERDICT.md` (Plan 00-03).

**Verdict: PARTIAL — mechanism promising, threshold not yet calibrated.** No single
(model, threshold) pair cleared **both** bars (`collapse_rate >= 0.8` AND `control_overmerge == 0`)
on the 2026-06-25 corpus. This is **not** rounded up to a pass.

**Chosen / closest operating point:**

| Field | Value |
|-------|-------|
| Model | **`mE5-large`** (chosen for ADR / Phase 5 embedding infra) |
| Threshold | **`0.84`** |
| collapse_rate | **`0.783`** (78.3%) — bar: ≥ 0.80 → **not met** |
| control_overmerge | **`1`** — bar: == 0 → **not met** |
| Verdict | **PARTIAL** |

- **`bge-m3` disqualified entirely:** max collapse_rate < 0.05 across all thresholds (0.75–0.98).
- **Root cause:** same-topic / different-event control pairs (e.g. three distinct Trump articles)
  have embedding similarity overlapping with same-event cross-language pairs, preventing a clean
  threshold cut. The corpus control set is too topically narrow to calibrate reliably.

**Calibration event set:** corpus 2026-06-25 (single day, NRK + BBC + TASS); 23 same-story "yes"
pairs from 13 labeled rows; 17 control "no" pairs from 11 labeled rows. Events: Venezuela
earthquake (cross-lang RU/EN/NO), Japan earthquake, FIFA WC qualifiers, Trump/Iran deal,
NATO-Ukraine European allies, Medvedev statement series, Norwegian school issues. Cross-date
generalization **unverified**.

**Implications for Phase 5:**
- Embedding model: **mE5-large** (locked); starting threshold `0.84`, re-tune on a larger /
  held-out corpus with genuinely off-topic controls.
- Input text: `title + summary[:512]` only (never full body).
- mE5-large prefixes: `passage: ` for corpus documents, `query: ` for queries.

---

## R3 — Postgres Entity Resolution — **PARTIAL**

**ADR:** ADR-006. Source: `findings/R3-VERDICT.md` (Plan 00-04).

**Verdict: PARTIAL.** pgvector cosine entity resolution works **mechanically**; the ≥2-language
coverage bar was not met due to corpus composition (not a mechanism failure). Recorded as a
partial, not a pass.

**Configuration:**

| Parameter | Value |
|-----------|-------|
| Embedding model | `BAAI/bge-m3` (R3 default — R3 ran before R2 decided; see Divergence Note below) |
| Embedding dim | 1024 (CLS pooling, L2-normalized) |
| LINK_THRESHOLD | **0.85** |
| Index | pgvector HNSW, `vector_cosine_ops`, `<=>` operator |
| DB | `pgvector/pgvector:pg16` on localhost:22062 |
| NER model | qwen36-ud-4bit via oMLX :8000/v1 (local, ADR-004) |

**Raw numbers / acceptance results:**

| Criterion | Result | Detail |
|-----------|--------|--------|
| NATO merges to 1 entity_id | PASS | entity_id=166 |
| NATO appears in ≥3 items | PASS | **5 items** (tass_021, tass_043, tass_051, tass_077, tass_084) |
| Items span ≥2 languages | **FAIL** | **only `lang=ru`** (all TASS); NRK/BBC items had no NATO mention |
| Control entities distinct | PASS | Trump (entity_id=6) ≠ Putin (entity_id=189); cosine ~0.72 ≪ 0.85 |
| NER uses local llm() (ADR-004) | PASS | qwen36 via oMLX; no cloud endpoint |

- 285 unique entities extracted from 144 corpus items; 599 entity_links recorded.
- Control spread: Trump entity_id=6 across 11 items (en/no/ru); Putin entity_id=189 (ru);
  Zelenskyj entity_id=53 (no/ru). Trump/Putin correctly kept distinct.
- **Why single-language:** the 2026-06-25 NRK/BBC feeds were dominated by Venezuela earthquake +
  domestic news with zero explicit NATO mentions; only TASS named NATO. A day with NATO-summit
  coverage would likely yield cross-source, cross-language merges.

**Schema validated (for Phase 8):** `entities (id, name, name_norm, lang, type, embedding vector(1024))`
+ `entity_links (entity_id FK, item_id, mention, lang)`. Use HNSW `vector_cosine_ops`,
`LINK_THRESHOLD=0.85`. Add corpus diversification (multi-day rolling window, multiple feeds per
language) to create cross-language merge opportunities.

### R3/R2 Embedding-Model Divergence Note (carried into ADR-006 as a Phase-8 risk)

R3 embedded entities with **`BAAI/bge-m3`** (source: fallback-bge-m3 — R3 ran before R2 decided;
the `similarity` string an R3 auto-parser captured was a misparse of R2-VERDICT.md, not the real
choice). R2-VERDICT.md records **`mE5-large` @ 0.84** as the chosen embedding model. These differ:
the R3 entity-link threshold (0.85) was validated on **bge-m3** vectors, **not** the chosen
**mE5-large**. **Phase 8 must re-validate entity linking on mE5-large vectors before production.**
This is recorded as a Consequence in ADR-006.

---

## R4 — Wiki-LLM Feasibility — **PARTIAL**

**ADR:** feeds Phase 10 Wiki-LLM. Source: `findings/R4-VERDICT.md` (Plan 00-05).

**Verdict: PARTIAL — synthesis mechanism GO; cross-language synthesis incomplete.** Local qwen36
(oMLX, `qwen36-ud-4bit`, ADR-004 — no cloud) produces a coherent, four-section, citation-grounded
intel-wiki page in both **standing** and **on-demand** modes. The core R4 question — *can a local
model synthesize a coherent cited wiki from the corpus?* — is **yes**. Marked PARTIAL (not elevated)
for two recorded limits.

**Raw numbers:**
- **Standing page (NATO):** 5 corpus items, 11 bracketed `[N]` occurrences over **5 distinct cited
  sources** (tass_021/043/051/077/084). Grounding check **PASS** — every `[N]` → real source id.
- **On-demand article (Venezuela):** gathered **17 items across en/no/ru** via the R3 `entity_links`
  join; synthesized with 24 `[N]` occurrences over **8 distinct cited sources** (bbc_001, bbc_021,
  nrk_001, nrk_007, nrk_008, nrk_011, nrk_014, nrk_016). Grounding **PASS**.
- **Model:** qwen36-ud-4bit on oMLX (127.0.0.1:8000/v1). `max_tokens` raised 800→1100 so all four
  prompted sections complete.
- **Human coherence judgment:** PARTIAL (operator, 2026-06-26).

**Caveats (carry-forward to Phase 10):**
1. **Cross-language synthesis incomplete — model dropped all Russian sources.** The Venezuela gather
   retrieved 17 items across en/no/ru, but synthesis cited **only** en (bbc) + no (nrk); all 7 TASS
   (ru) items [11]–[17] were in context yet went **uncited**. Cross-language *gather* works;
   cross-language *synthesis* silently omitted Russian. Phase 10 must verify non-no/en sources are
   actually represented (per-language coverage check, or pre-translate — ROADMAP backlog 999.1).
2. **Minor internal contradiction** in the Venezuela page (Norway "har ingen egen ambassade" then
   "ambassaden har kommet i kontakt med nordmenn" [7]) — a reader-level coherence nit, not a
   grounding failure. Phase 10 synthesis should flag/avoid intra-page contradictions.

**Implications:** Wiki-LLM (standing + on-demand) is feasible on **local qwen36 alone** (DGX Spark
was unavailable; R4 ran entirely on oMLX — confirms Assumption A2 fallback). The on-demand →
entity_links gather (R3 reuse) works end-to-end across languages. Citation grounding (every [N] →
real source id, hard-exit on violation) is a sound, cheap guardrail to carry into Phase 10.

### R4 Sample 1 — Standing page (NATO) — pasted inline (survives `.spike/` deletion)

```markdown
# Intel-wiki: NATO

_Syntetisert på lokal qwen36 (oMLX) fra 5 korpus-elementer · standing · 5 [N]-sitater_

## Bakgrunn

NATO (North Atlantic Treaty Organization) har lenge vært sentral i vestlig sikkerhetspolitikk, men alliansens indre dynamikk og eksterne relasjoner er under betydelig press. Historisk har Russland sett på NATO som en trussel, der tidligere sikkerhetsråd-medlem Dmitry Medvedev hevder at alliansen etter Sovjetunionens fall har brukt «marionettregimer» som batterirammeslag mot Russland [4]. Denne geopolitiske spenningen har eskalert, spesielt med tanke på naboland som Moldova og Armenia, som Medvedev advarer om nå står overfor samme scenario som Ukraina [4]. I tillegg har Medvedev uttrykt skepsis til alliansens sammenhold, påstått at NATO-enhet ikke har stor verdi i reelle krigssituasjoner, og hevdet at Washingtons allierte raskt kan snu ryggen til hverandre [5].

## Sentrale utviklingstrekk

Det er synlige sprekker i alliansens politiske enighet, spesielt knyttet til forsvarsutgifter og strategisk prioritering. Den amerikanske presidenten har uttrykt skuffelse over flere europeiske allierte, inkludert Storbritannia, Spania, Italia, Frankrike og Tyskland [1]. Spesielt har spanske myndigheter blitt kritisert for å «ikke ville betale noe» for forsvarsinnsatsen [1]. Til tross for disse spenningene har en gruppe ledende europeiske nasjoner – Storbritannia, Italia, Polen, Frankrike og Tyskland – fornyet sitt engasjement for å styrke det europeiske forsvaret [2]. Disse lederne har befestet sin forpliktelse til en «sterkere europeisk rolle innenfor NATO» [2].

En annen viktig utvikling er alliansens forhold til Ukraina. De samme fem nasjonene (E5) har annonsert intensjonen om å bringe Ukraina nærmere NATO [3]. I en felles uttalelse understreker lederne sin forpliktelse til å fordype NATOs partnerskap med Ukraina [3]. Dette indikerer en strategisk vilje blant nøkkelmedlemmer om å integrere Ukraina, selv om det ikke er enighet om tidspunkt eller betingelser på tvers av hele alliansen.

## Aktuell vurdering

Den nåværende situasjonen preges av en dualitet mellom politisk uenighet og strategisk tilnærming. På den ene siden er det en tydelig konflikt mellom USA og flere europeiske makter angående byrdefordelingen, noe som skaper usikkerhet om alliansens langsiktige stabilitet [1]. På den andre siden viser E5-landene en vilje til å ta ansvar gjennom dypere samarbeid og støtte til Ukraina [2][3].

Russland, representert ved Medvedev, tolker disse bevegelserne som en direkte trussel. Hans påstand om at NATO-enhet er illusorisk i krigstid [5], og hans analyse av alliansens bruk av proxy-regimer [4], reflekterer en dyp mistillit til vestlige intensjoner. Medvedev hevder at hendelser som angrepene på Iran og blokkeringen av Hormuz-stredet har demonstrert hvor raskt allierte kan svikte hverandre [5]. Dette skaper et paradoks: mens europeiske ledere forsøker å styrke sin egen rolle innenfor NATO for å sikre stabilitet [2], ser Russland dette som en del av en offensiv strategi rettet mot deres sikkerhetsinteresser [4].

## Åpne spørsmål

Det gjenstår flere uavklarte spørsmål knyttet til NATOs fremtidige struktur og effektivitet. Først og fremst er spørsmålet om forsvarsutgifter kritisk; hvor lenge kan USA tolerere skuffelsen over land som Storbritannia, Spania og Tyskland før det fører til konkrete politiske konsekvenser [1]? For det andre er spørsmålet om Ukrainas integrasjon sentralt; hvordan vil E5-landenes innsats for å bringe Ukraina nærmere alliansen påvirke den samlede NATO-strategien, og vil dette skape ytterligere splittelse med land som er mer tilbakeholdne [3]? For det tredje er spørsmålet om alliansens reelle handlekraft under press viktig; støtter Medvedevs påstand om at enhet er verdiløs i krig, eller er dette en russisk narrativ for å undergrave tilliten til vestlige allianser [5]? Til slutt er spørsmålet om hvordan naboland som Moldova og Armenia vil håndtere den økte spenningen og NATOs utvidelseshorisont, gitt Russlands advarsler om at de nå står overfor samme scenario som Ukraina [4].

---
## Kildekart (citation grounding)
- [1] `tass_021` — tass (ru) — US disappointed with UK, Spain, Italy, France, Germany as NATO allies — Trump  _✓ sitert_
- [2] `tass_043` — tass (ru) — UK, Italy, Poland, France, Germany agree to strengthen defense cooperation  _✓ sitert_
- [3] `tass_051` — tass (ru) — UK, Italy, Poland, France, Germany announce intention to bring Ukraine closer to NATO  _✓ sitert_
- [4] `tass_077` — tass (ru) — Moldova, Armenia now facing same scenario as Ukraine once adopted — Medvedev  _✓ sitert_
- [5] `tass_084` — tass (ru) — NATO unity not worth much in real war situations — Medvedev  _✓ sitert_

**Grounding check: PASS** — citations [1, 2, 3, 4, 5]; every [N] maps to a real source id: True
```

### R4 Sample 2 — On-demand article (Venezuela, cross-language gather) — pasted inline

```markdown
# Intel-wiki: Venezuela

_Syntetisert på lokal qwen36 (oMLX) fra 17 korpus-elementer · on-demand · 8 [N]-sitater_

## Bakgrunn
Venezuela har vært preget av en dyp økonomisk og politisk krise i over ti år, noe som har svekket landets institusjonelle kapasitet og infrastruktur [6]. Denne langvarige ustabiliteten skaper et sårbart grunnlag for håndtering av naturkatastrofer. Landet har ingen egen ambassade i Venezuela, noe som kompliserer direkte diplomatisk kontakt og evnen til å kartlegge situasjonen for utenlandske statsborgere [7].

## Sentrale utviklingstrekk
Natt til torsdag norsk tid ble Venezuela rammet av to kraftige jordskjelv som traff hovedstaden i løpet av sekunder. Det første skjelvet målte 7,2 på Richters skala, fulgt kort tid senere av et på 7,5 [1]. Videoopptak viser omfattende kollaps av bygninger og panikk blant beboere som evakuerer området [2].

Ifølge fungerende president Delcy Rodríguez er 32 personer bekreftet omkommet og 700 skadet [8]. Imidlertid er det usikkerhet knyttet til de endelige tallene, da myndighetene venter på rapporter fra La Guaira, som er den regionen som antas å være hardest rammet [8]. Hovedflyplassen Maiquetía er stengt på grunn av skader, og regjeringen har erklært unntakstilstand i landet [10].

Internasjonalt har USA raskt reagert. USAs president Donald Trump uttrykte på plattformen Truth Social at USA står klar, villig og i stand til å hjelpe, og hevdet at skjelvene har ført til "svært mange dødsfall" uten å referere til offisielle tall [8]. Utenriksminister Marco Rubio bekreftet at USA sender søketeam, medisinske ressurser og militær hjelp [3]. Viseutenriksminister Christopher Landau opplyste at USA er i kontakt med venezuelanske myndigheter og gjør klar bistand [9].

Norske myndigheter har uttrykt bekymring. Utenriksminister Espen Barth Eide beskrev nyhetene om ødeleggelser og dødsfall som "fryktelige" og påpekte at katastrofen forverrer situasjonen i et land som allerede er i krise [6]. Utenriksdepartementet (UD) opplyste at de ikke har full oversikt over antall nordmenn i landet, da registreringen er frivillig [7]. Likevel har ambassaden kommet i kontakt med nordmenn som befinner seg i landet, og disse oppgis å ha det bra [7].

## Aktuell vurdering
Situasjonen er prekær med tanke på den eksisterende økonomiske krisen, som gjør gjenoppbygging og nødhjelp ekstra utfordrende [6]. Det er fryktet omfattende ødeleggelser og svært høye dødstall utover de bekreftede tallene [9]. Den internasjonale hjelpen fra USA er raskt på plass, men det er uklart hvordan dette vil samspille med Venezuelas politiske ledelse. For norske borgere er situasjonen foreløpig stabil, men mangelen på offisiell oversikt over antall nordmenn i landet utgjør en risiko for kommunikasjon og evakuering hvis situasjonen forverres [7].

## Åpne spørsmål
Det er fortsatt usikkerhet knyttet til det endelige antallet drepte og skadede, spesielt med tanke på La Guaira-regionen [8]. Det er også uklart hvor mange nordmenn som oppholder seg i Venezuela, da UD ikke har oversikt over dette [7]. Videre er det spørsmål om hvordan den amerikanske bistanden vil bli koordinert med de venezuelanske myndighetene under unntakstilstand [10].

---
## Kildekart (citation grounding)
- [1] `bbc_001` — bbc (en) — 'I thought building would fall on top of me' - Venezuelans describe earthquake panic  _✓ sitert_
- [2] `bbc_021` — bbc (en) — Moment earthquake hits Venezuela and leaves buildings collapsed  _✓ sitert_
- [3] `nrk_001` — nrk (no) — Rubio: USA sender humanitær hjelp til Venezuela  _✓ sitert_
- [4] `nrk_004` — nrk (no) — Jordskjelv i Venezuela: – Akkurat nå er jeg i sjokk  _· ikke sitert_
- [5] `nrk_006` — nrk (no) — Eide til Aftenposten: – Fryktelige nyheter  _· ikke sitert_
- [6] `nrk_007` — nrk (no) — UD: Har ikke oversikt over norske borgere i Venezuela  _✓ sitert_
- [7] `nrk_008` — nrk (no) — 32 bekreftet døde i jordskjelv så langt  _✓ sitert_
- [8] `nrk_011` — nrk (no) — Trump: – USA står klare  _✓ sitert_
- [9] `nrk_014` — nrk (no) — USA vil hjelpe Venezuela etter jordskjelvene  _✓ sitert_
- [10] `nrk_016` — nrk (no) — Unntakstilstand og stengt hovedflyplass i Venezuela  _✓ sitert_
- [11] `tass_003` — tass (ru) — Earthquake causes heavy infrastructure damage in Venezuelan capital — radio  _· ikke sitert_
- [12] `tass_005` — tass (ru) — At least 32 people killed in Venezuelan earthquake — agency  _· ikke sitert_
- [13] `tass_007` — tass (ru) — Massive damage done by earthquake in Venezuela — radio  _· ikke sitert_
- [14] `tass_012` — tass (ru) — State of emergency declared in Venezuela after earthquake  _· ikke sitert_
- [15] `tass_014` — tass (ru) — USGS lowers estimate of potential damage from quake in Venezuela  _· ikke sitert_
- [16] `tass_019` — tass (ru) — USGS estimates potential losses from quake in Venezuela at from 2 to 20% of GDP  _· ikke sitert_
- [17] `tass_024` — tass (ru) — Powerful earthquake rocks Venezuela  _· ikke sitert_

**Grounding check: PASS** — citations [1, 2, 3, 6, 7, 8, 9, 10]; every [N] maps to a real source id: True
```

---

## R5 — COP / World Monitor — **DROP** WM as engine; **BUILD** native SP-COP

**ADR:** ADR-005. Source: `findings/R5-VERDICT.md` (Plan 00-06).

**Verdict: DROP** World Monitor as the product/engine; **ADOPT** its globe-COP *concept*; **BUILD**
an InfoTriage-native interactive-SAB canvas (**SP-COP**) on the open globe stack, fed by InfoTriage
data + CCIR/CNR. Grounded in a real test (D-05): WM was cloned, installed (1617 pkgs), built and
launched as a working desktop app (after a build-command correction), GUI judged hands-on, and LLM
wiring / provider chain / data architecture / render stack read directly from source.

**Key reasons to DROP WM as the engine:**
- **Cloud-coupled codebase** — large commercial monorepo; backend `remoteBase` defaults to
  `https://api.worldmonitor.app`; full product uses hosted Convex (DB), Clerk (auth), Vercel.
- **Own feeds / own region model** — ships its own ~hundreds of RSS feeds + `SOURCE_REGION_MAP` +
  per-region instability index; presenting InfoTriage's own store + doctrinal CCIR/CNR means
  fighting its design.
- **No CCIR doctrine** — WM has AOIs/topics + source-tier priority + instability scoring, but not
  the operator's interest-profile-scored CCIR/CNR model.
- **No entity graph** — only entity *location* markers; no R3-style entity network / KG.
- **High setup friction / build trap** — 1617 pkgs, Tauri/Rust/Convex/Vercel, 5 variants; the
  obvious `npm run tauri build` ships a BROKEN app ("asset not found: index.html") — the desktop
  build requires `npm run desktop:build:full` (`VITE_DESKTOP_RUNTIME=1`).
- **oMLX-compatible (positive)** — WM's `generic` OpenAI provider (`LLM_API_URL`/`LLM_API_KEY`/
  `LLM_MODEL`) points at oMLX with no Ollama; cloud providers self-skip when keys are unset and
  `providerOrder:['generic']` hard-excludes them. So the *local-LLM* requirement is satisfiable —
  but does not outweigh the cloud-coupling + own-feeds + no-CCIR + no-entity-graph reasons to build.

**Brief comparison:** InfoTriage's `write_bluf()` baseline (20 pre-scored items) produces a
CCIR-tiered, cited, CNR-elevated analyst brief. WM has **no equivalent native output** (its outputs
are an instability index + a market/forecasting brief). WM does not compete as an intelligence
engine; its value is the COP **display** concept — reproducible on open libraries.

**Open globe stack to BUILD on (all permissive licenses):** `globe.gl` / `three` / `three-globe`
(MIT) + `deck.gl` (Apache-2.0) + `maplibre-gl` + `@protomaps/basemaps` (BSD-3) — InfoTriage can build
the same view directly, local-LLM (oMLX, ADR-004), fed from the canonical store.

**Additional dropped reference — Aegis** (`github.com/FNBIP/aegis-osint-map`): a World-Monitor-lineage
OSINT platform. **Same drop-as-engine conclusion** — it is *more* cloud-locked than WM (intelligence
core = **Valyu API** cloud + optional OpenAI, **no local-LLM path** → conflicts with ADR-004; **Mapbox
GL** commercial/token-gated; Next.js 16/Vercel). Borrow concepts only (Intel Dossiers / deep-research
exports; OSINT geo-asset layers mapping to CCIR PIR-4/PIR-2; Command Palette + 7-day density timeline)
— still no entity network / KG and no CCIR doctrine, which remain InfoTriage's differentiators.

**SP-COP design direction (carried to ADR-005):** the SAB evolved from a static presentation into an
**interactive canvas** — topics/news/info explorable on a map + panels, organized by **CCIR-as-interests**
(standing topics) and **CNR-as-urgency** at personal scale. Two crossing axes (known↔unknown,
ambient↔focused) and three modes the user moves between freely:
- **LOOK** (ambient/lean-back): glance the operating picture; discovery comes to you.
- **HEADLINES** (digest): CCIR-tiered cited headlines, CNR-elevated; ties to `write_bluf()` (Phase 6);
  also the presentation mode (explore ⟷ present). **Validated via sketch 001.**
- **FOCUS** (lean-forward): neighborhood graph + topic timeline + source items + action launchpad
  (follow-up / dig-in via RAG/Wiki-LLM / spin-up-POC). The R3 entity-resolution graph is the discovery
  engine for the unknown/serendipity half. Split canvas = globe (geo half) + entity-link Graph Canvas
  (network half) + shared timeline scrubber, all cross-filtered, with floating pickers (from WM).

---

## Cross-phase consumers

The durable knowledge here feeds planning for: **P2** (storage), **P3** (RabbitMQ bus, R1/ADR-007),
**P5** (dedup, R2), **P8** (entity resolution, R3/ADR-006 — incl. the mE5-large re-validation),
**P10** (Wiki-LLM, R4), and **SP-COP** (R5/ADR-005).

No throwaway spike code was merged into `apps/` or `libs/`. The `.spike/` tree + spike containers
are disposed of at teardown (D-06) — this document and ADR-005..008 are the durable record.
