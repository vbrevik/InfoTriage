# Roadmap: InfoTriage

## Overview

**Combined re-architecture (2026-06-24).** Supersedes the prior "ingester-first, defer architecture"
roadmap. This is a **re-platform, not greenfield**: the spike (ingest → score → brief, incl.
PMESII/TESSOC) already runs and is tested (56 tests pass) on host Python — the phases below wrap and
containerize working code onto a **microservice architecture** (Postgres canonical store + RabbitMQ
bus + OAuth2/MCP ingestion + Obsidian/SAB outputs). Solo on one Mac now, **architected to grow into a
multi-user team server** (Milestone 3, deferred). Design source-of-truth:
`docs/superpowers/specs/2026-06-24-app-split-architecture-design.md`.

**Milestones:** **M1 Foundation** (Phases 0–7) re-platforms the spike onto the new architecture; ship
gate = parity with today. **M2 Fusion** (Phases 8–12) layers the north-star features. **M3** (future)
= multi-user/team server. **SP-COP** runs as a parallel, non-blocking gated spike.

## Phases

**Phase Numbering:** Integer phases (0–12) are planned milestone work. Decimal phases (e.g. 2.1) are
urgent insertions. The all-local-LLM rule (ADR-004) is never revisited by a phase.

- [x] **Phase 0: Concept spike** (M1) - throwaway spike gating the unproven bits before any build — COMPLETE (R1 GO, R2/R3/R4 PARTIAL, R5 drop-WM/build-SP-COP); ADR-005..008 written, .spike/ torn down
- [x] **Phase 1: Contracts + monorepo skeleton** (M1) - `libs/contracts` (Item, events, codec, bus interface) (completed 2026-06-27)
- [x] **Phase 2: Storage — Postgres + blobs** (M1) - canonical store behind a store interface (completed 2026-06-28)
- [x] **Phase 3: Bus — RabbitMQ** (M1) - AMQP transport + bus client (completed 2026-06-29)
- [ ] **Phase 4: Ingest adapters + Gmail MCP** (M1) - containerize bridges + self-hosted Gmail MCP (OAuth2)
- [ ] **Phase 5: Triage app** (M1) - event-driven scorer + pgvector dedup
- [ ] **Phase 6: Brief app** (M1) - SAB renderer + Obsidian vault-writer
- [ ] **Phase 7: Ops + cutover** (M1) - health, DLQ, replay, retire host path
- [ ] **Phase 8: Entity resolution** (M2) - Postgres + pgvector → Obsidian projection
- [ ] **Phase 9: RAG recall** (M2) - CCIR pre-filter + thematic recall over corpus
- [ ] **Phase 10: Wiki-LLM** (M2) - standing auto-wiki + on-demand synthesis → Obsidian
- [ ] **Phase 11: SOCMINT + Arctic collection** (M2) - Telegram/AIS adapters via MCP pattern
- [ ] **Phase 12: CNR alerting / dissemination** (M2) - real-time notification lane

Parallel, non-blocking: **SP-COP** — COP/map UI gated spike (World Monitor adopt-vs-build; ADR-005).
Deferred: **Milestone 3** — multi-user / team server (auth, tenancy, sharing).

## Phase Details

### Phase 0: Concept spike

**Goal**: A throwaway spike that resolves the unproven architectural unknowns with go/no-go answers
before any production build. Does NOT re-spike the already-working ingest→score→brief pipeline.
**Depends on**: Nothing (first phase)
**Requirements**: ADR-006 (architecture), ADR-007 (RabbitMQ), spec §Final decisions
**Success Criteria** (what must be TRUE):

  1. A go/no-go + one-line ADR note exists for: RabbitMQ topology (exchanges/routing for the 4 events).
  2. Norwegian semantic dedup quality measured (bge-m3 vs mE5-large on NRK/BBC/TASS same-story triples) with a chosen model.
  3. Postgres entity-resolution feasibility demonstrated on a sample (entities + links).
  4. Wiki-LLM feasibility shown (standing + on-demand) on qwen36/DGX with a sample output.
  5. COP need + World Monitor outcome recorded (cross-ref SP-COP).

**Plans**: 7 plans

- [x] 00-01-PLAN.md — Ephemeral spike infra (RabbitMQ + pgvector on 22060-22062) + shared NRK/BBC/TASS corpus fetch (W1)
- [x] 00-02-PLAN.md — R1: RabbitMQ topology publish→consume round-trip + poison→DLQ (W2) — GO
- [x] 00-03-PLAN.md — R2: Norwegian semantic dedup bake-off (bge-m3 vs mE5-large, threshold sweep) (W2) — PARTIAL: mE5-large chosen @0.84, threshold uncalibrated (corpus too narrow)
- [x] 00-04-PLAN.md — R3: Postgres entity resolution (pgvector cosine link, NATO merge + control split) (W2) — PARTIAL: mechanism GO, 1-lang coverage (corpus date)
- [x] 00-05-PLAN.md — R4: Wiki-LLM feasibility (cited standing page + on-demand article on qwen36) (W3) — PARTIAL: synthesis GO; cross-lang synthesis drops ru sources
- [x] 00-06-PLAN.md — R5: COP/World Monitor adopt/build/drop vs InfoTriage CCIR brief (W2) — DROP WM; BUILD own interactive-SAB canvas/COP (SP-COP) on open globe stack w/ InfoTriage data+CCIR
- [x] 00-07-PLAN.md — Closeout: SPIKE-FINDINGS.md + ADR-005..008 written; .spike/ deleted + containers down (379bb7a) (W4)

### Phase 1: Contracts + monorepo skeleton

**Goal**: One shared contract package all apps depend on; no app imports another. No behavior change
to the running pipeline.
**Depends on**: Phase 0
**Requirements**: ADR-006, spec §The glue
**Success Criteria** (what must be TRUE):

  1. `libs/contracts` defines the canonical `Item` schema (core + summary + body_ref + payload JSON + attachments[]).
  2. Event schemas exist for `item.ingested`, `verdict.ready`, `sab.published`, `feed.unhealthy`.
  3. A frontmatter⇆JSONB codec and a transport-swappable bus-client interface exist.
  4. Repo restructured into `apps/` + `libs/`; existing scripts import from contracts; 56 tests still pass.
  5. Three stale doc claims fixed (imap/yt not "scaffolded"; PMESII/TESSOC done; `.env.example` exists).

**Plans**: 2/3 plans executed
**Wave 1**

- [x] 01-01-PLAN.md — libs/contracts package: Item, 4 event schemas, PyYAML codec, Protocol bus + in-memory impl, contracts tests (W1) — R1-R4

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 01-02-PLAN.md — Monorepo re-root into apps/+libs/: re-home scripts with exhaustive path-depth fixes, root pytest config, Item import wiring, migrate 6 tests to pytest (W2) — R5

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 01-03-PLAN.md — Fix 3 stale doc claims (REQUIREMENTS C-9/C-13/A-5) + README apps/ path hygiene (W3) — R6

### Phase 2: Storage — Postgres + blobs

**Goal**: Postgres is the single canonical store; SQLite is rejected (concurrent writers).
**Depends on**: Phase 1
**Requirements**: ADR-001
**Success Criteria** (what must be TRUE):

  1. Postgres (`postgres:16` + `pgvector/pgvector:pg16`) runs on :22000 with `InfoTriage` schema: articles, enrichment, ccir, embeddings(vector(1024)), audit, entities, entity_links.
  2. On-disk content-addressed blob store (`data/blobs/<hash>`) holds MIME/PDF/transcripts/raw HTML.
  3. A single `store` interface mediates all reads/writes; existing scripts go through it.
  4. Atom-projection writer for FreshRSS lives behind the same interface.

**Plans**: 4/4 plans complete

**Wave 1**

- [x] 02-01-PLAN.md — Scaffold libs/store package + versioned SQL DDL (7 tables, pgvector HNSW) + docker postgres :22000 (W1) — ADR-001

**Wave 2** *(blocked on Wave 1)*

- [x] 02-02-PLAN.md — Pure-Python store core: blob store, Store Protocol, InMemoryStore, Atom projection + unit tests (W2) — ADR-001

**Wave 3** *(blocked on Wave 2)*

- [x] 02-03-PLAN.md — PostgresStore (psycopg3+pgvector) + [BLOCKING] live schema apply + integration tests (cosine threshold, 1024-dim) (W3) — ADR-001

**Wave 4** *(blocked on Wave 3)*

- [x] 02-04-PLAN.md — Retrofit digest.py persistence onto the store (no backfill) + full-suite green (W4) — ADR-001

### Phase 3: Bus — RabbitMQ

**Goal**: AMQP broker that also models team information-sharing (fan-out, per-consumer queues) for the M3 growth path.
**Depends on**: Phase 1
**Requirements**: ADR-007
**Success Criteria** (what must be TRUE):

  1. RabbitMQ runs on :22001 (AMQP) / :22002 (management UI).
  2. The `libs/contracts` bus client implements the interface over AMQP (exchanges + routing keys for the 4 events, acks, durable queues, DLQ).
  3. A publish/consume round-trip is smoke-tested green.

**Plans**: 1/1 plans complete

### Phase 4: Ingest adapters + Gmail MCP

**Goal**: Containerize the working bridges and solve Gmail (app passwords hard-blocked: 2SV on).
**Depends on**: Phase 2, Phase 3
**Requirements**: ADR-003, ADR-004 (read-only), ADR-008 (MCP/OAuth2)
**Success Criteria** (what must be TRUE):

  1. `ingest-imap`/`ingest-youtube`/`ingest-web` containers normalize sources to `Item`, persist to Postgres+blobs, publish `item.ingested`.
  2. `ingest-obsidian` reads `Vault/articles-inbox/` clips into the same path.
  3. `ingest-gmail` is a thin MCP client → self-hosted Gmail MCP server (:22025, own OAuth2 token, headless-safe); legacy IMAP `gmail_to_atom.py` retired.
  4. Email is triage-only (no FreshRSS projection); RSS/YouTube get an Atom projection → FreshRSS (:22010).

**Plans**: 6 plans

**Wave 1**

- [ ] 04-01-PLAN.md — libs/ingest_common foundation: idempotent persist_and_publish (get_item pre-check), FastAPI POST /run single-instance-lock app factory, env-driven store/bus construction + idempotency (R6) & lock (D-01) tests (W1) — ADR-003, ADR-004

**Wave 2** *(blocked on Wave 1; parallel — no file overlap)*

- [ ] 04-02-PLAN.md — ingest-imap container: containerize imap fetch → Item → Postgres+bus (no Atom), read-only; R1 + empty-mailbox backstop (W2) — ADR-003, ADR-004
- [ ] 04-03-PLAN.md — ingest-youtube container: yt-dlp → Item+blob+bus AND Atom dual output, stub transcription only; R2 + blob-dedup + empty-channel backstops (W2) — ADR-003, ADR-004
- [ ] 04-04-PLAN.md — ingest-obsidian container: articles-inbox/*.md → Item via codec (D-09 mapping), read-only vault; R4 + missing-field fallback (W2) — ADR-003, ADR-004
- [ ] 04-05-PLAN.md — ingest-gmail: @shinzolabs/gmail-mcp@1.7.4 server + OAuth2 provision script (readonly+metadata) + httpx JSON-RPC client adapter → Item; retire gmail_to_atom.py; R3 + R7 (W2) — ADR-003, ADR-004, ADR-008

**Wave 3** *(blocked on Wave 2)*

- [ ] 04-06-PLAN.md — scheduler container (APScheduler 3.x, 409=skip) + docker-compose 6 services (D-03 ports, localhost-only Gmail :22025, env_file, :ro vault) + .env.example; R5 (W3) — ADR-003, ADR-008

### Phase 5: Triage app

**Goal**: Decouple scoring from the FreshRSS Fever poll; move proven scoring logic behind events + Postgres.
**Depends on**: Phase 2, Phase 3, Phase 4
**Requirements**: ADR-004, ccir.md
**Success Criteria** (what must be TRUE):

  1. `triage` (:22030) subscribes `item.ingested`, reads payload from Postgres, scores with qwen36 against ccir.md, writes enrichment rows, publishes `verdict.ready`.
  2. PMESII/TESSOC enrichment is formalized as an enrichment stage.
  3. Semantic dedup uses pgvector + the dedicated embedding model, replacing keyword overlap.
  4. Shadow-run vs the old path matches, then cut over; the Fever poll is removed.

**Plans**: TBD

### Phase 6: Brief app

**Goal**: SAB/digest become an event-driven product plus an Obsidian projection.
**Depends on**: Phase 5
**Requirements**: spec §Reading-surface routing
**Success Criteria** (what must be TRUE):

  1. `brief` (:22031) subscribes `verdict.ready`, clusters via pgvector, renders the SAB served at :22040, publishes `sab.published`.
  2. A vault-writer emits high-value items + the SAB as Obsidian `.md` (front-matter via codec; body summary; `[[entity]]` wikilinks).
  3. Email surfaces here (SAB + Obsidian), not in FreshRSS.

**Plans**: TBD

### Phase 7: Ops + cutover

**Goal**: Make the stack operable and retire the old host path. M1 ship gate.
**Depends on**: Phase 4, Phase 5, Phase 6
**Requirements**: spec §Management layer
**Success Criteria** (what must be TRUE):

  1. `opml-health` (:22032) is a scheduled worker emitting `feed.unhealthy`.
  2. Compose has per-container healthchecks + restart; structured logging; RabbitMQ DLQ + retention; `ops/Makefile` (up/logs/replay/backfill).
  3. Host-run scripts + legacy Gmail IMAP bridge deleted.
  4. The full pipeline runs on the new architecture at parity with today's spike (M1 ship gate).

**Plans**: TBD

### Phase 8: Entity resolution

**Goal**: Cross-modality entity tracking as Postgres truth; Obsidian graph as a projection.
**Depends on**: Phase 5
**Requirements**: ADR-003
**Success Criteria** (what must be TRUE):

  1. `entities` + `entity_links` populated via extraction + pgvector linking (cross-modality, cross-language).
  2. The Obsidian graph is generated as a projection of this truth, not the system of record.

**Plans**: TBD

### Phase 9: RAG recall

**Goal**: Cut LLM caller volume via a CCIR pre-filter and enable thematic recall over the durable corpus.
**Depends on**: Phase 8
**Requirements**: ADR-001
**Success Criteria** (what must be TRUE):

  1. Clearly off-topic items skip the LLM (`cosine(article, ccir.vector) < τ`), logged in `audit`.
  2. A thematic recall (`recall.py --topic … --since …`) cites `articles.id`/`url` per claim; heavy synthesis may run on DGX.

**Plans**: TBD

### Phase 10: Wiki-LLM

**Goal**: An auto-maintained intel wiki synthesized from the corpus, plus on-demand synthesized articles.
**Depends on**: Phase 9
**Requirements**: ADR-006, spec §Obsidian
**Success Criteria** (what must be TRUE):

  1. A standing, auto-updated per-entity/per-topic wiki is written as cross-linked Obsidian `.md`.
  2. On-demand synthesized articles answer ad-hoc queries from the corpus; DGX used for heavy synthesis.

**Plans**: TBD

### Phase 11: SOCMINT + Arctic collection

**Goal**: Round out the picture with SOCMINT + authoritative Arctic data via the MCP adapter pattern.
**Depends on**: Phase 4
**Requirements**: ADR-003
**Success Criteria** (what must be TRUE):

  1. `ingest-telegram` (Telethon), advanced YouTube/transcription, and `ingest-barentswatch` (AIS) land as MCP-pattern adapters with `discipline` tags + Admiralty reliability ratings.
  2. SOCMINT legal/ToS posture documented; ACLED only with a paid license (never fed to the local LLM without one).

**Plans**: TBD

### Phase 12: CNR alerting / dissemination

**Goal**: A CNR CAT I alert should not require manually refreshing the SAB.
**Depends on**: Phase 6
**Requirements**: ADR-003
**Success Criteria** (what must be TRUE):

  1. A CNR CAT I 🚩 post-write publishes a push (ntfy local-server preferred; ADR-004-friendly) with SAB excerpt + dedupe ID.
  2. The SAB remains the canonical artifact.

**Plans**: TBD

## Backlog

### Phase 999.1: On-demand per-item translation (ru/de/es → no/en) (BACKLOG)

**Goal:** On-demand, per-item translation of source items into Norwegian/English so the
operator (no/en only) can read and **verify** non-no/en sources. Primary driver is citation
verification — the wiki/SAB trust model (R4) requires spot-checking that each `[N]` supports
its claim, but ru/de/es sources are unreadable to the operator without translation. Secondary:
reading the original item in the reading surface (Obsidian/FreshRSS). Reuses local `llm()`/qwen36
(ADR-004, no cloud). NOT needed for triage scoring, dedup, or synthesis (qwen36 is natively
multilingual and already emits no/en). Scope: on-demand per-item, never eager whole-corpus.
Likely home: enrichment stage in **Phase 5** (store translated field) or render-time action in
**Phase 6** (brief/Obsidian). Surfaced during R4 (00-05) Wiki-LLM spike, 2026-06-26.
**Requirements:** TBD
**Plans:** 1/1 plans complete

Plans:

- [x] 03-PLAN.md

- [ ] TBD (promote with /gsd-review-backlog when ready)
