# InfoTriage — Architecture & Build Plan

Status: **agreed direction**, 2026-06-23. Supersedes the ad-hoc spike scripts as the
target; spike stays runnable while we build toward this.

---

## ADR index

| ADR | Title | Status |
|---|---|---|
| [ADR-001](#adr-001--postgres--pgvector-freshrss-centric) | Postgres + pgvector, FreshRSS-centric | Accepted |
| [ADR-002](#adr-002--prior-art-evaluate-taranis-ai-before-building) | Prior art: evaluate Taranis AI before building | Accepted |
| [ADR-003](#adr-003--reframe-this-is-an-osintall-source-intelligence-system-not-a-reader) | Reframe: this is an OSINT/all-source intelligence system, not a reader | Accepted |
| [ADR-004](#adr-004--all-llm-work-runs-on-local-qwen36-hard-constraint) | All LLM work runs on local qwen3.6 (hard constraint) | Accepted |
| [ADR-005](adr/ADR-005-cop-world-monitor.md) | COP / World Monitor: drop as engine, build native SP-COP | Accepted |
| [ADR-006](adr/ADR-006-microservice-architecture-entity-resolution.md) | Microservice architecture + Postgres/pgvector entity resolution | Accepted |
| [ADR-007](adr/ADR-007-rabbitmq-bus.md) | RabbitMQ event bus topology | Accepted |
| [ADR-008](adr/ADR-008-self-hosted-mcp-oauth2-ingestion.md) | Self-hosted MCP / OAuth2 ingestion | Accepted |
| [ADR-009](adr/ADR-009-pmesii-hybrid-definitions.md) | PMESII hybrid definitions | Accepted |
| [ADR-010](adr/ADR-010-tessoc-taxonomy-correction.md) | TESSOC taxonomy correction | Accepted |
| [ADR-011](adr/ADR-011-pmesii-ajp01-ajp5-citation.md) | PMESII AJP-01 / AJP-5 citation | Accepted |
| [ADR-012](adr/ADR-012-dimefil-cop-cip-evaluation.md) | DIMEFIL / COP / CIP / CRP evaluation | Accepted |
| [ADR-013](adr/ADR-013-recognized-picture-doctrine.md) | Recognized Picture doctrine | Accepted |

---

## ADR-001 — Postgres + pgvector, FreshRSS-centric

**Context.** The spike works (44 feeds, FreshRSS + local qwen36 CCIR triage, SAB
digests), but storage is SQLite + a `verdicts.jsonl`, and dedup is keyword overlap
which fails across languages (NRK "Nato-toppmøte" ≠ BBC "NATO summit" ≠ TASS). We want
durable storage, semantic dedup, a CCIR pre-filter, and RAG-backed situational
awareness over time — all local and free.

**Decision.** One **PostgreSQL** instance as the system of record:
- FreshRSS runs on it (its own schema) for ingestion + reader UI.
- `InfoTriage` schema holds our **article copy + CCIR/CNR enrichment + pgvector embeddings**.
- Embeddings from a **local multilingual model** (bge-m3 via Ollama; verify in Phase 2).
- Scoring stays **qwen36** via oMLX. No cloud, no second DB service.

**Rejected.**
- *MongoDB* — data is relational/queryable; Mongo splits the store, adds nothing.
- *Separate vector DB (Qdrant/Weaviate/Milvus)* — premature; pgvector handles our scale.
  Revisit only if article volume or query latency demands it.
- *Full custom ingestion* — FreshRSS already gives feeds+email-bridge+reader for free.

**Consequences.** One backup target, one query surface (SQL + vector + full-text).
Slightly heavier than SQLite. We own an article copy decoupled from FreshRSS retention,
so RAG/history survive feed purges.

---

## Target architecture

```
 feeds / email / rss-bridge ─▶ FreshRSS (ingest + reader)  ─┐
                                                            │ Fever API (read new)
                                                            ▼
   qwen36  (score + tag CCIR/CNR) ───▶  ┌──────────────  PostgreSQL  ──────────────┐
   bge-m3  (embed, multilingual)  ───▶  │ InfoTriage.articles    (our copy)           │
                                        │ InfoTriage.enrichment  (ccir,cnr,score,why) │
                                        │ InfoTriage.embeddings  (pgvector)           │
                                        │ InfoTriage.ccir        (defs + embeddings)  │
                                        │ freshrss.*          (FreshRSS own)       │
                                        └──────────────────────────────────────────┘
                                                            │
                       SAB generator ◀───────────── semantic dedup · CCIR pre-filter · RAG recall
                       (CCIR sections, CNR 🚩, since-cutoff window)
```

## Data model (InfoTriage schema)

- **articles** — `id, guid (unique), url, source, title, body, published_at, ingested_at`.
  Keyed by stable GUID/link so it's independent of FreshRSS internal ids.
- **enrichment** — `article_id FK, ccir, cnr, score, why, model, scored_at`.
- **embeddings** — `article_id FK, vector vector(1024), model`. pgvector ivfflat index.
- **ccir** — `code (PIR-1…), title, body, vector(1024)` — the CCIR defs, embedded once.

Dedup = cosine threshold over `embeddings`. CCIR pre-filter = article↔ccir cosine.
RAG = top-k retrieve by vector + filter, feed to qwen36 for the brief.

## Tech choices (all local, free)
| Concern | Choice | Note |
|---|---|---|
| Store | PostgreSQL 16 + pgvector | Docker, one instance |
| Ingest + reader | FreshRSS (Postgres backend) | already running |
| Scoring LLM | qwen36-ud-4bit via oMLX | already wired |
| Embeddings | bge-m3 (multilingual) via Ollama | verify pull in Phase 2; fallback e5/nomic |
| Glue | Python stdlib + psycopg | scripts already in `score/` |

---

## Phased build plan

**Phase 0 — Postgres foundation.** Add Postgres+pgvector to compose. Point FreshRSS at
it (migrate/re-provision). Create `InfoTriage` schema + tables. *Done when:* FreshRSS runs
on Postgres and the schema exists.

**Phase 1 — Enrichment in DB.** Scorer upserts articles + writes enrichment to Postgres
(replaces `verdicts.jsonl`). SAB reads from Postgres. *Done when:* a SAB builds purely
from SQL, no jsonl.

**Phase 2 — Embeddings + semantic dedup.** Stand up bge-m3; embed each article; replace
keyword clustering with cosine clustering in cluster/SAB views. *Done when:* NRK+BBC+TASS
on one event collapse to one cluster.

**Phase 3 — CCIR pre-filter.** Embed CCIR defs; cosine-rank articles before LLM scoring
to cut LLM calls and sharpen tagging. *Done when:* clearly-off-topic items skip the LLM.

**Phase 4 — RAG SAB / recall.** "What do we know about X since date" → vector retrieve +
qwen36 synthesis. Situational awareness over time, not just today. *Done when:* a themed
recall brief cites stored articles.

## Brief app / SAB endpoints

The `apps/brief` container serves the Situation Awareness Brief (SAB) and writes the
digest files consumed by the vault and downstream readers.

### HTTP endpoints

| Endpoint | Description |
|---|---|
| `GET /health` | Liveness probe (no DB dependency) |
| `GET /sab` | Cached SAB HTML; regenerates when `sab.html` is ≥24 h old |
| `GET /sab?window=24h` | Ad-hoc HTML render for the last N hours; bypasses cache |
| `GET /sab?mode=list` | Markdown list (`score >= 8`) for the window |
| `GET /vault` | Obsidian vault SAB projection as markdown |
| `GET /vault?view=cop` | Vault SAB filtered through the requested picture view |

### View filters (`?view=`)

The SAB can be rendered through three picture lenses (ADR-012, ADR-013). Views are
applied **after** fetching rows from Postgres; they do not change the LLM scorer.

| View | Query param | What it shows |
|---|---|---|
| **COP** | `?view=cop` | Common Operational Picture — friendly/operational items: `FFIR-1/2/3`, `PIR-3`, `SIR-2/3` × `Political/Military/Infrastructure` |
| **CIP** | `?view=cip` | Common Intelligence Picture — adversary/threat items: `PIR-*` with a TESSOC tag × `Information/Military/Economic` |
| **CRP** | `?view=crp&ccir=PIR-1,PIR-2&pmesii=Military&Economic&tessoc=Sabotage&min_score=8` | Common Relevant Picture — user-configurable AND-ed filters |

CRP parameters:
- `ccir` — comma-separated CCIR codes (case-insensitive)
- `pmesii` — comma-separated PMESII domains
- `tessoc` — comma-separated TESSOC categories
- `min_score` — minimum enrichment score (inclusive)

View-filtered requests bypass the shared `sab.html` cache and are never written to it.

**Ad-hoc vs. persisted views.**
- **COP and CIP** are first-class picture views. The background consumer renders them to disk on every `verdict.ready` event (see [Digest outputs](#digest-outputs)) and writes matching vault projections.
- **CRP** is intentionally ad-hoc: it is available on demand through `GET /sab?view=crp&...` and `GET /vault?view=crp&...`, but the consumer does not persist CRP-specific files. This keeps the commander's custom filter ephemeral and avoids an open-ended multiplication of output files.

The `/vault` endpoint returns the same Obsidian SAB projection that the consumer writes to `obsidian-sab.md`, but rendered on demand and filtered by the requested view. It supports the same `view` / `ccir` / `pmesii` / `tessoc` / `min_score` parameters as `/sab`.

### Digest outputs

The background consumer renders the following files under `INFOTRIAGE_DIGESTS_DIR`
(default `data/digests`):

```
brief.md      cluster.md      list.md      bluf.md
brief-cop.md  cluster-cop.md  list-cop.md  bluf-cop.md
brief-cip.md  cluster-cip.md  list-cip.md  bluf-cip.md
```

Vault projections are written to `INFOTRIAGE_VAULT_PATH` (default `data/obsidian`):

```
obsidian-sab.md     obsidian-sab-cop.md     obsidian-sab-cip.md
<item_id>.md
```

Individual item files are written once; view projections reuse the same item pool.

## Open questions
- FreshRSS migration: re-provision fresh on Postgres (simplest) vs migrate SQLite data?
- Embedding dim/model: bge-m3 (1024) vs e5-large — confirm availability + Norwegian quality.
- Retention: how long to keep article bodies for RAG (disk vs history depth)?
- Notifications: does CNR CAT I 🚩 just surface in the SAB, or also push (Signal/ntfy)?

## Out of scope (for now)
X/Twitter ingestion · separate vector service · cloud · multi-user.

---

## ADR-004 — All LLM work runs on local qwen3.6 (hard constraint)

Every LLM stage uses the **local qwen3.6** (`qwen36-ud-4bit` via oMLX `:8000/v1`, key
`omlx`; DGX Spark (vLLM) primary). **No cloud LLM, ever**, in the runtime. This is a
requirement, not a default.

| Stage | qwen3.6 role |
|---|---|
| Collection pre-filter | cheap relevance gate before deeper processing |
| Scoring + CCIR/CNR tag | already live (`score/triage_score.py`) |
| Fusion / clustering aid | summarize/relate event clusters |
| Production (SAB) | write the brief (`score/digest.py`) |
| RAG / NL-query | answer "what do we know about X" over the corpus |

Embeddings use a **local** multilingual model (bge-m3, separate from qwen3.6 but also
local) — Phase 2. When adopting any third-party tool (World Monitor, Taranis), the
**accept/reject test includes "can it be pointed at local qwen3.6?"** — World Monitor's
"run everything with Ollama" passes; a cloud-only LLM path is disqualifying.

*Scope note:* cloud models are used only for **my** (assistant) orchestration/judgment
during design — never in InfoTriage's running pipeline. Bulk/IO assist is delegated to
qwen3.6 too (ask-omlx / omlx-agent) to conserve cloud tokens.

---

## ADR-002 — Prior art: evaluate Taranis AI before building

Before committing to the Phase 0–4 build, we surveyed GitHub (2026-06-23). The space
is mature; building from scratch may be wasteful.

**Strongest match — Taranis AI** (`taranis-ai/taranis-ai`, EUPL-1.2). A real OSINT
**situational-analysis** platform: ingests web/RSS/atom/email/twitter/slack → NLP/AI
enrichment → analysts turn unstructured news into **structured report items** → generate
briefings/PDFs. Stack: Python, **PostgreSQL**, Redis, RQ workers, Flask/HTMX. Descends
from SK-CERT's Taranis NG; built for exactly the CCIR→SAB workflow we're hand-rolling.
*Gap:* local-LLM support unconfirmed (uses NLP/AI; may assume cloud) — but it's Python +
self-hosted, so wiring qwen36/oMLX is plausible. *Risk:* heavier stack, learning curve.

**Closest to the daily-brief idea — Meridian** (`iliane5/meridian`, MIT). "Presidential
daily brief": hundreds of sources → embeddings + UMAP + HDBSCAN clustering → Postgres →
AI brief. **But cloud-locked** (Gemini + Cloudflare Workers), semi-manual. *Not adoptable
under free+local+on-Mac* — use as design reference for clustering + brief structure.

**Local-LLM friendly aggregators** — `finaldie/auto-news` (RSS/YouTube/Reddit/X + Ollama
via LangChain, dedup, ranking) and `Thysrael/Horizon` (fetch→dedupe→score→brief). Good
references / possible bases for the triage layer.

**OSINT dashboards** (World Monitor, ShadowBroker, OSINT-MONITOR) — source tiering,
LLM threat classification, Telegram/Discord briefs. Aligned with CNR alerting + source
tiering; map/dashboard-oriented rather than reader+brief.

**Decision:** before Phase 0, **spike Taranis AI** (stand up, test local-LLM feasibility,
judge fit to CCIR/CNR + Norwegian sources). If it fits → adopt and extend, skip most of
the custom build. If too heavy or cloud-LLM-locked → fall back to the lean
FreshRSS + Postgres + pgvector plan above, borrowing Meridian's clustering and
auto-news's local-LLM patterns. Either way, keep ccir.md as the taxonomy.

---

## ADR-003 — Reframe: this is an OSINT/all-source intelligence system, not a reader

User reframing (2026-06-23): RSS is **one collection discipline, not the driver**; add
SOCMINT (YouTube, Instagram, Facebook, Telegram); the work is the **intelligence cycle**
with the SAB as the *commander's extract*; and a **map is the navigation frame (COP)**.

### The intelligence cycle → InfoTriage stages → existing tooling

| Stage | What it means here | Existing OSS to use/learn from |
|---|---|---|
| **Direction** | CCIR/CNR = the commander's requirements driving collection | `ccir.md` (ours) |
| **Collection / source handling** | Many disciplines, not just RSS: news feeds, **event DBs** (ACLED, UCDP, GDELT, Liveuamap), **SOCMINT** (Telegram, YouTube, Instagram), email, web scrape. Register sources + rate reliability (NATO/Admiralty A–F / 1–6). | Taranis collectors; ACLED/GDELT/UCDP APIs; Telethon, yt-dlp, instagram_monitor; awesome-osint |
| **Processing** | Transcribe video/audio (YouTube), translate (NO/EN/RU), geolocate, entity-extract, dedup (semantic + geo/Haversine) | whisper (local), local embed model, World Monitor's Haversine dedup |
| **Analysis / fusion** | Correlate to CCIR, cluster events, build entity/relationship picture, assess | OpenCTI / MISP (STIX2 knowledge graph), Taranis report items |
| **Production** | Structured report items → **SAB** (commander's extract) | Taranis report→PDF; our SAB generator |
| **Dissemination** | CNR 🚩 alerts, brief, **map markers (CoT)** | TAK (CoT), ntfy/Signal |
| **Navigation frame** | **Map/COP** as primary UI; SAB is the textual extract | TAK ecosystem; World Monitor; War Monitor |

### Three archetypes (no single OSS does it all for our local-LLM case)
- **Map-COP dashboard** — **World Monitor** (`koala73/worldmonitor`, 58k★, AGPL-3.0):
  3D globe (globe.gl) + deck.gl, 56 layers, **65+ providers / 500+ feeds**, and crucially
  **"run everything with Ollama, no API keys"** — local-LLM native. Docker/Tauri self-host.
  *Gap:* social media (YT/Telegram/IG) not built in. **Strongest map+aggregation+local base.**
- **Intelligence workflow / briefing** — **Taranis AI**: collection→analysis→structured
  report→briefing. Best CCIR→SAB process fit. Postgres. Local-LLM TBD.
- **Fusion knowledge graph** — **OpenCTI / MISP**: STIX2 entities/relationships. Heavy,
  cyber-CTI flavoured, but the right model if analysis grows into link/entity analysis.
- **True military COP** — **TAK** (ATAK-CIV is DoD open-source; TAK Server, CloudTAK,
  iTAK/WinTAK). The actual mil situational-awareness standard; feed intel as CoT markers.
  Option if the map *is* the product and you want the doctrinal COP.

### Revised build-vs-adopt
Likely **not one tool** but a small stack:
1. **World Monitor** as the map-COP + multi-source aggregation + local-LLM shell (it already
   solves the hardest parts: map, 500+ feeds, Ollama-native, offline).
2. **Add SOCMINT collectors** it lacks (Telegram via Telethon, YouTube via yt-dlp+whisper,
   Instagram via instagram_monitor) feeding the same store.
3. **Overlay CCIR/CNR + SAB** (`ccir.md` + our generator) as the direction+production layer.
4. Borrow **Taranis** report-workflow ideas; consider **TAK** if the COP must be doctrinal.

The FreshRSS spike stays a working daily driver while we evaluate World Monitor + Taranis.

### Verify next
- World Monitor: does the Ollama path cover *scoring/briefing* or just classification?
  Can we inject custom CCIR taxonomy + Norwegian sources? Run it on the Mac.
- Source-handling model: adopt Admiralty reliability rating per source.
- SOCMINT legality/ToS + which platforms are realistically collectable (FB is hostile).

### Commercial north-stars (reference only — closed, $$$, cloud; NOT adoptable)
These define "what good looks like"; InfoTriage is the free/local/personal-scale shadow.
- **Palantir Gotham / Maven Smart System (MSS)** — the apex. Fuses 179+ heterogeneous
  sources (satellite, drone, SIGINT, geoloc) onto a **single fused map/globe**, LLM-assisted
  decision support, **stable entity IDs tracked across modalities**, CCIR-style tasking,
  sensor-to-shooter compression. NATO-procured. *Lesson:* the **map/globe is the fusion
  surface** (validates the COP-first frame), entities persist across sources, LLM does
  analytical decision support — our north star for the fusion+COP layers.
- **Semantic AI — Semantica Pro + Cortex EIP** — graph-based link/entity/network analysis;
  fuses disparate data into one schema to query relationships/patterns. *Lesson:* the
  **analysis stage is an entity-relationship graph** → OSS analog = OpenCTI / MISP.
  (Name collision: unrelated OSS `Hawksight-AI/semantica` is a KG context layer — different.)
- **Babel Street / Recorded Future / Dataminr** — multilingual (150–200+ langs), social +
  dark web, **agentic natural-language investigation interface** (Babel Insights
  Investigator), hyper-speed alerting (Dataminr ≈ CNR at scale). *Lessons for us:*
  multilingual embeddings (NO/EN/RU), an **NL/RAG query interface over the corpus**
  (our Phase 4), and CNR-style real-time alerting.

**Net:** InfoTriage's target feature set = fused map COP (Maven) + entity graph (Cortex) +
NL/RAG investigation (Babel) + CNR alerting (Dataminr), at personal scale, free & local.

### Norwegian Arctic/maritime collection — BarentsWatch (strong add, free API)
**BarentsWatch** (Kystverket, Tromsø; since 2012) — authoritative Norwegian maritime/Arctic
situational awareness with **open APIs** at developer.barentswatch.no:
- **Live AIS API** — real-time vessel tracking in the Norwegian economic zone, Svalbard
  fishery-protection zone, Jan Mayen. Feed straight onto InfoTriage's map COP as ship tracks.
- **ArcticInfo** — map service: AIS + sea-ice maps + weather across Barents/North Sea,
  Svalbard, Greenland, Russia, Canada.
Directly serves **PIR-2 (Nordområdene & Arktis)**. Free, official, geocoded → a real
structured collector (not RSS) and a domain COP reference. **Add in the collection layer.**

### RAYVN — Norwegian crisis-management standard (dissemination / hand-off reference)
**RAYVN** (rayvn.global; Norwegian, via Total Safety AS) — critical-event / crisis-management
platform: real-time situational awareness during an incident, logging, alerting/notification,
reporting, mobile app, collaboration (samvirke). **DSB chose RAYVN in 2023** as the preferred
public-sector crisis solution — nationwide: 10 regions, 356 municipalities, Sivilforsvaret,
state agencies. Commercial/closed → reference, not adoptable.

*Relevance:* RAYVN is the **dissemination / incident-response** end. InfoTriage does continuous
early-warning intelligence (SAB + CNR); RAYVN is what spins up when a **CAT I event becomes an
actual crisis**. Complementary: InfoTriage's CNR 🚩 is the trigger that, in a real org, hands off
to a RAYVN-style response tool. Validates the SA + alerting framing in a Norwegian-official
context. *(Not the OSINT tools "Graylark Raven"/GeoSpy image-geoloc or RavenEye — different.)*
