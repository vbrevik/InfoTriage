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
- [x] **Phase 4: Ingest adapters + Gmail MCP** (M1) - containerize bridges + self-hosted Gmail MCP (OAuth2) (completed 2026-06-29)
- [x] **Phase 5: Triage app** (M1) - event-driven scorer + pgvector dedup (completed 2026-07-02)
- [x] **Phase 6: Brief app** (M1) - SAB renderer + Obsidian vault-writer
- [x] 06-01-PLAN.md — Renderer library + FastAPI serving layer (Wave 1+2) — 38 tests pass
- [x] 06-02-PLAN.md — pgvector semantic clustering (replaced keyword-overlap) — 38/38 tests pass
- [x] **Phase 7: Ops + cutover** (M1) - health, DLQ, replay, retire host path (completed 2026-07-12; **M1 ship-gate met**)
- [ ] **Phase 8: Entity resolution** (M2) - Postgres + pgvector → Obsidian projection
- [ ] **Phase 9: RAG recall** (M2) - CCIR pre-filter + thematic recall over corpus
- [ ] **Phase 10: Wiki-LLM** (M2) - standing auto-wiki + on-demand synthesis → Obsidian
- [ ] **Phase 11: SOCMINT + Arctic collection** (M2) - Telegram/AIS adapters via MCP pattern
- [ ] **Phase 12: CNR alerting / dissemination** (M2) - real-time notification lane
- [x] **Phase 99.1: M1 closure** (urgent decimal insertion, before M2) — retroactive closure of 4 procedural gaps surfaced by `.planning/v1.0-MILESTONE-AUDIT.md` §8: (RT-1) Phase 7 missing `07-VERIFICATION.md`; (RT-2) Phase 6 + Phase 7 missing `*-VALIDATION.md`; (RT-3) Phases 00/02/04 `*-VALIDATION.md` `nyquist_compliant: false` → `true`; (RT-4) `apps/opml_health/service.py:52` inline `FeedUnhealthy` class shadow. Drives M1 audit `gaps_found → passed` before M2 begins.

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

**Plans**: 6/6 plans complete

**Wave 1**

- [x] 04-01-PLAN.md — libs/ingest_common foundation: idempotent persist_and_publish (get_item pre-check), FastAPI POST /run single-instance-lock app factory, env-driven store/bus construction + idempotency (R6) & lock (D-01) tests (W1) — ADR-003, ADR-004

**Wave 2** *(blocked on Wave 1; parallel — no file overlap)*

- [x] 04-02-PLAN.md — ingest-imap container: containerize imap fetch → Item → Postgres+bus (no Atom), read-only; R1 + empty-mailbox backstop (W2) — ADR-003, ADR-004
- [x] 04-03-PLAN.md — ingest-youtube container: yt-dlp → Item+blob+bus AND Atom dual output, stub transcription only; R2 + blob-dedup + empty-channel backstops (W2) — ADR-003, ADR-004
- [x] 04-04-PLAN.md — ingest-obsidian container: articles-inbox/*.md → Item via codec (D-09 mapping), read-only vault; R4 + missing-field fallback (W2) — ADR-003, ADR-004
- [x] 04-05-PLAN.md — ingest-gmail: @shinzolabs/gmail-mcp@1.7.4 server + OAuth2 provision script (readonly+metadata) + httpx JSON-RPC client adapter → Item; retire gmail_to_atom.py; R3 + R7 (W2) — ADR-003, ADR-004, ADR-008

**Wave 3** *(blocked on Wave 2)*

- [x] 04-06-PLAN.md — scheduler container (APScheduler 3.x, 409=skip) + docker-compose 6 services (D-03 ports, localhost-only Gmail :22025, env_file, :ro vault) + .env.example; R5 (W3) — ADR-003, ADR-008

### Phase 5: Triage app

**Goal**: Decouple scoring from the FreshRSS Fever poll; move proven scoring logic behind events + Postgres.
**Depends on**: Phase 2, Phase 3, Phase 4
**Requirements**: ADR-004, ccir.md
**Success Criteria** (what must be TRUE):

  1. `triage` (:22030) subscribes `item.ingested`, reads payload from Postgres, scores with qwen36 against ccir.md, writes enrichment rows, publishes `verdict.ready`.
  2. PMESII/TESSOC enrichment is formalized as an enrichment stage.
  3. Semantic dedup uses pgvector + the dedicated embedding model, replacing keyword overlap.
  4. Shadow-run vs the old path matches, then cut over; the Fever poll is removed.

**Plans**: 5/5 plans complete

**Wave 1** *(parallel — no file overlap)*

- [x] 05-01-PLAN.md — Store extension: 006-enrichment.sql (unique indexes + 7 columns), put_enrichment/get_enrichment/put_embedding/find_near_duplicate on Protocol+Postgres+InMemory (W1) — R1, R4
- [x] 05-02-PLAN.md — Worker prerequisites: RabbitMQBus.consume() persistent consumer + triage_score.py ccir.md hot-read fix (D-02) (W1) — R2, R3, ccir.md

**Wave 2** *(blocked on Wave 1)*

- [x] 05-03-PLAN.md — Triage worker.py: item.ingested consumer, mE5-large dedup, qwen36 scoring, enrichment write, verdict.ready publish, stdlib /health (W2) — R2, R3, R4, R5, R7, ADR-004, ccir.md

**Wave 3** *(blocked on Wave 2)*

- [x] 05-04-PLAN.md — Triage container: Dockerfile + requirements.txt + docker-compose triage service (:22030) + [BLOCKING] live /health + reconnect verify (W3) — R7

**Wave 4** *(blocked on Wave 3)*

- [x] 05-05-PLAN.md — Shadow-run parity (scripts/shadow_run.py) + [BLOCKING] Fever cutover gate (>=10 matching buckets) + README retire (W4) — R6

### Phase 6: Brief app

**Goal**: SAB/digest become an event-driven product plus an Obsidian projection.
**Depends on**: Phase 5
**Requirements**: spec §Reading-surface routing
**Success Criteria** (what must be TRUE):

  1. `brief` (:22031) subscribes `verdict.ready`, clusters via pgvector, renders the SAB served at :22040, publishes `sab.published`.
  2. A vault-writer emits high-value items + the SAB as Obsidian `.md` (front-matter via codec; body summary; `[[entity]]` wikilinks).
  3. Email surfaces here (SAB + Obsidian), not in FreshRSS.

**Plans**: 7/7 plans complete

- [x] 06-05-PLAN.md — db_live test DSN safety: require INFOTRIAGE_TEST_DSN, no prod fallback, regression guard + throwaway test DB (W1)
- [x] 06-06-PLAN.md — PostgresStore read-path txn hygiene: end read txn (rollback) + idle-in-transaction backstop + regression test (W2)
- [x] 06-UAT prep — SAB UI polish (source status card, hide empty CCIR slides), FreshRSS OPML import, NewsAPI 3h TTL, TTL docs + test (W3)
- [x] 06-07-PLAN.md — gap closure (UAT Test 6, SC3): fix VAULT_INCLUDE_EMAIL=0 exclusion to match production email rows by url scheme (imap:// + gmail://) + regression test (W1)

### Phase 7: Ops + cutover

**Goal**: Make the stack operable and retire the old host path. M1 ship gate.
**Depends on**: Phase 4, Phase 5, Phase 6
**Requirements**: spec §Management layer
**Success Criteria** (what must be TRUE):

  1. `opml-health` (:22032) is a scheduled worker emitting `feed.unhealthy`.
  2. Compose has per-container healthchecks + restart; structured logging; RabbitMQ DLQ + retention; `ops/Makefile` (up/logs/replay/backfill).
  3. Host-run scripts + legacy Gmail IMAP bridge deleted.
  4. The full pipeline runs on the new architecture at parity with today's spike (M1 ship gate).

**Plans**

- [x] 07-01-FreshRSS-rss-bridge-ops — done (commit 316a20f + 06-05): FreshRSS OPML imported, NewsAPI feeds throttled to 3h TTL, `apps/ingest/RSS_BRIDGE_NOTES.md` + `tests/test_set_newsapi_ttl.py` added.
- [x] 07-01-PLAN.md — M1 ship-gate ops: structured logging, DLQ consumer, ops/Makefile, retire host scripts (rolled-up 07-02/07-03/07-04). See `.planning/phases/07-ops-cutover/07-01-PLAN.md`. Implemented 2026-07-11; full pytest suite green (302 passed, 34 skipped).
- [x] 07-02 (committed `591034d`) — close 3 M1 known gaps: uvicorn JSON access logs via shared `LOGGING_CONFIG` (`libs/contracts/src/contracts/uvicorn-log-config.json` + Python wrapper); live RabbitMQ-mgmt DLQ depth probe (`apps/dlq_consumer/worker.py`, periodic GET, `feed.unhealthy` on `messages >= DLQ_DEPTH_CRITICAL_N`); `INFOTRIAGE_TEST_DSN` shell-smoke (`scripts/check_test_dsn.sh` + `make test-safe`). Pytest 319/0/34 baseline. See `.planning/phases/07-ops-cutover/07-02-SUMMARY.md`.
- [x] 07-03 (committed `3da4932` + docs `428f8a9`) — live-stack follow-up. After 07-02 made every service `from contracts import setup_logging` actively run at module-init, 3 services crashed on missing transitive contracts deps. Closed via per-`requirements.txt` hand-listing + `libs/contracts/pyproject.toml` `aio-pika` addition + TOML-grammar fix + `apps/dlq_consumer/worker.py` vhost URL-encoding (the `///` → `%2F` mgmt-API fix). Pytest 0 failures; 2-pass review PASS. See `.planning/phases/07-ops-cutover/07-03-SUMMARY.md`.
- [x] `b4ee46a` — Makefile `-f` forwarding fix (post-07-03 smoke-test catch). Captured `OPS_MAKEFILE := $(abspath $(lastword $(MAKEFILE_LIST)))` at parse time so `make test-safe`'s sub-make forwards `-f`. Full `make -f ops/Makefile test-safe` now exits 0.
- [x] 07-04 (committed `f17e644`) — `tests/test_dep_list_superset.py` cross-check. Asserts every `[project].dependencies` entry in `libs/contracts/pyproject.toml` is re-listed in every `apps/*/requirements.txt` that consumes contracts. Detection = union of direct Python import ∪ Dockerfile `libs/contracts`-install ∪ transitive sibling-lib walk. Caught `apps/opml_health/requirements.txt` missing `pydantic>=2.0` on first run — fix landed in the same commit. Pytest 328/0/34. See `.planning/phases/07-ops-cutover/07-04-SUMMARY.md`.

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
**Plans:** 7/7 plans complete

Plans:

- [x] 06-03-PLAN.md
- [x] 06-04-PLAN.md

- [x] 03-PLAN.md

- [ ] TBD (promote with /gsd-review-backlog when ready)

### Phase 999.2: Dedup threshold calibration on larger corpus (BACKLOG)

**Goal:** Calibrate the semantic dedup threshold on a larger, held-out corpus with genuinely off-topic controls so that both acceptance bars are cleared (`collapse_rate >= 0.8` AND `control_overmerge == 0`).

**Context:** Phase 00 concept spike (R2) found PARTIAL: mE5-large @ 0.84 threshold got 78.3% collapse rate with 1 control overmerge on a single-day (2026-06-25) corpus from NRK + BBC + TASS. Root cause: same-topic/different-event control pairs (e.g. three distinct Trump articles) have embedding similarity overlapping with same-event cross-language pairs. The control set was too topically narrow. Cross-date generalization was never verified.

**Carry-forward from spike:**

- Model: mE5-large (locked)
- Starting threshold: 0.84 (must re-tune)
- Input: `title + summary[:512]` only (never full body)
- mE5-large prefixes: `passage: ` for corpus docs, `query: ` for queries
- Phase 5 must use stricter evaluation protocol with genuinely off-topic controls

**Source:** SPIKE-FINDINGS.md §R2, R2-VERDICT.md, Phase 00 VERIFICATION.md

**Requirements:** TBD
**Plans:** 0 plans

Plans:

- [ ] TBD (promote with /gsd-review-backlog when ready)

### Phase 999.3: Entity resolution cross-language coverage and mE5-large re-validation (BACKLOG)

**Goal:** Ensure Phase 8 entity resolution meets the cross-language bar (entities merged across >=2 languages) and validates entity linking on the chosen embedding model (mE5-large).

**Context:** Phase 00 concept spike (R3) found PARTIAL: pgvector cosine linking mechanism proven (NATO merged across 5 items, HNSW index validated at threshold 0.85), but the cross-language bar was not met because the test date's NRK/BBC feeds had zero NATO mentions — all 5 NATO extractions came from TASS (single language). This is a corpus coverage limitation, not a mechanism failure.

**Additional risk — embedding model mismatch:** R3 used `BAAI/bge-m3` (its default). R2 chose `mE5-large`. Entity linking threshold 0.85 was validated on bge-m3 vectors, NOT the chosen mE5-large. Phase 8 must re-validate entity linking on mE5-large vectors before production.

**Carry-forward from spike:**

- Schema validated: `entities (id, name, name_norm, lang, type, embedding vector(1024))` + `entity_links (entity_id FK, item_id, mention, lang)`
- HNSW with `vector_cosine_ops`, LINK_THRESHOLD=0.85
- Phase 8 must add multi-day rolling window with multiple feeds per language to create cross-language merge opportunities
- Phase 8 must re-validate entity linking on mE5-large vectors (not bge-m3)

**Source:** SPIKE-FINDINGS.md §R3, R3-VERDICT.md, ADR-006, Phase 00 VERIFICATION.md

**Requirements:** TBD
**Plans:** 0 plans

Plans:

- [ ] TBD (promote with /gsd-review-backlog when ready)

### Phase 999.4: Cross-language synthesis verification for Wiki-LLM (BACKLOG)

**Goal:** Add per-language coverage verification to Wiki-LLM synthesis so that cross-language corpus items are not silently omitted from synthesized articles.

**Context:** Phase 00 concept spike (R4) found PARTIAL: local qwen36 synthesis mechanism works (NATO standing page + Venezuela on-demand article both coherent with citation grounding PASS). However, the Venezuela on-demand article retrieved 17 items across 3 languages (en/no/ru) via R3 entity_links, but the synthesis cited only en (bbc) and no (nrk) — all 7 TASS (ru) items [11]–[17] were gathered into context yet went uncited. The cross-language gather works; the cross-language synthesis silently dropped Russian.

**Additional nit:** Minor internal contradiction in Venezuela page (Norway "har ingen egen ambassade" then "ambassaden har kommet i kontakt med nordmenn" [7]) — a reader-level coherence issue.

**Carry-forward from spike:**

- Synthesis mechanism is viable on local qwen36
- Citation grounding (every [N] → real source id, hard-exit on violation) is a sound guardrail
- Phase 10 must add per-language coverage check before synthesis to catch silent omissions
- Phase 10 should flag/avoid intra-page contradictions

**Source:** SPIKE-FINDINGS.md §R4, R4-VERDICT.md, Phase 00 VERIFICATION.md

**Requirements:** TBD
**Plans:** 0 plans

Plans:

- [ ] TBD (promote with /gsd-review-backlog when ready)
