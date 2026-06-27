---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: Ready to plan
stopped_at: Phase 1 PLANNED — 3 plans (01-01..01-03) across 3 waves, verified, ready to execute
last_updated: "2026-06-27T21:06:14.353Z"
progress:
  total_phases: 13
  completed_phases: 1
  total_plans: 10
  completed_plans: 9
  percent: 8
---

# STATE — InfoTriage

> **Ephemeral.** Pick-up-next-session memory. Durable context lives in `docs/`, `PROJECT.md`,
> `REQUIREMENTS.md`, `ROADMAP.md`, `.planning/codebase/`. Trim aggressively.

## Session: 2026-06-27 — Phase 1 COMPLETE (01-03 stale doc fixes, SPEC R6)

### Just-completed

- **01-03-PLAN.md (Stale doc fixes, SPEC R6)**: Corrected three stale claims in REQUIREMENTS.md (C-9 yt_to_atom: "scaffolded" → "implemented" + apps/ingest/ path; C-13 imap_to_atom: same; A-5 PMESII: [PLANNED] → [LIVE] with Phase 1.5 archive ref) and updated README.md run-commands + Bridges section to use apps/triage/, apps/ingest/, apps/opml/ paths from plan 01-02 restructure. Commits b9a1606 (REQUIREMENTS.md), 70e5a25 (README.md).
  - Decision: A-5 set to [LIVE] — PMESII/TESSOC enrichment confirmed shipped in Phase 1.5
  - Decision: C-9/C-13 kept [SPIKE] — runtime blockers (yt-dlp + transcribe; IMAP creds) still pending
  - Planner-script bug noted: `grep 'opml/feeds.opml'` matches apps/opml/feeds.opml substring; spirit of check confirmed satisfied

## Session: 2026-06-27 — Phase 1 01-02 COMPLETE (monorepo restructure)

### Just-completed

- **01-02-PLAN.md (Monorepo restructure + test migration)**: Re-homed bridge/score/opml into apps/{ingest,triage,opml}. Applied exhaustive 7-expression path-depth fix table (3 expressions RESEARCH/PATTERNS missed: sab_html.py ROOT, gmail_to_atom.py OUT + .env). D-08 wiring: digest.py imports Item from contracts. Root pyproject.toml pytest config (pythonpath replaces all sys.path.insert). Migrated 6 unittest files to pytest functions. **83 tests green** (27 contracts + 56 migrated). Commits c22d10c (pyproject), 9035fe5 (re-home), 8d9ca9d (test migration).
  - Q1 resolved: sab_html.py in apps/triage/ (sibling import forces co-location)
  - Q2 resolved: working.opml moved (git-tracked)
  - Q3 resolved: pyproject.toml chosen over pytest.ini / conftest.py

## Session: 2026-06-27 — Phase 0 COMPLETE (00-07 closeout + teardown)

### Just-completed

- **00-07-PLAN.md (Spike closeout)**: SPIKE-FINDINGS.md consolidated (R1-R5 per-unknown verdicts +
  raw numbers, R4 samples pasted inline, R3/R2 divergence note) + ADR-005..008 written. Then full
  D-06 teardown: `.spike/` deleted (3.1G incl. World Monitor clone/build), pgvector + rabbitmq
  containers/volumes removed. **Phase 0 done** (1/13 phases). Commits 5b5ab32 (artifacts), 379bb7a (teardown).

  - ADR-005: DROP World Monitor (+ Aegis) as engine; BUILD native SP-COP interactive-SAB canvas.
  - ADR-006: entity resolution (pgvector HNSW cosine, threshold 0.85); Phase-8 risk = re-validate on mE5-large.
  - ADR-007: RabbitMQ topology (infotriage.events + 4 keys + DLX/DLQ); Phase 3 use aio-pika.
  - ADR-008: self-hosted Gmail MCP/OAuth2 ingestion.
- **SP-COP design work** (parallel, captured): R5-VERDICT holds the full vision (LOOK/HEADLINES/FOCUS
  modes, known↔unknown + ambient↔focused axes, prior-art incl. Palantir/i2/InfraNodus/Aegis). Sketch
  001 built (winner = HEADLINES: BLUF-first, delta-default, time-aware; LOOK geo half has OSINT layers

  + heatmap wired to timeline). Wrapped into skill `sketch-findings-infotriage`.

### Just-completed (prior — Phase 0 R1-R5)

- **00-06-PLAN.md (R5 COP / World Monitor)**: cloned + built + launched the real WM desktop app
  (oMLX-pinned, cloud keys blank). Operator judged the globe hands-on. **Verdict: DROP WM as
  product/engine; BUILD own interactive-SAB canvas/COP (SP-COP).** WM is an online aggregator with a
  local shell (api.worldmonitor.app backend, own RSS feeds, Convex/Clerk/Vercel); its globe is 100%
  open libs (globe.gl/three-globe MIT, maplibre BSD). WM HAS a CCIR-like concept (SOURCE_REGION_MAP
  AOIs→feeds + source tiers + instability score) — at personal scale InfoTriage's CCIR/CNR = "what I'm
  interested in" + "how urgent," scored vs own ccir.md. **Product vision:** SAB → interactive canvas
  (topics/news/info, globe + panels), NOT a static brief. SP-COP feature wishlist: keep floating
  pickers; add timeline/time-scrubber; add views beyond geo (timeline/topic/entity/list). Build trap
  found: `tauri build` ships broken app — must use `desktop:build:full`. Commit da77120 (Task 1) + verdict.

### Just-completed

- **00-05-PLAN.md (R4 Wiki-LLM)**: local qwen36 (oMLX, DGX Spark unavailable) synthesizes coherent
  4-section citation-grounded intel-wiki pages. Standing NATO page (5 items, 5 grounded cites) +
  on-demand Venezuela article (17 items gathered across en/no/ru via R3 entity_links, 8 cited).
  Grounding PASS both (hard-exit on ungrounded ref). **Verdict PARTIAL** — synthesis mechanism GO,
  but cross-language synthesis **drops Russian sources** (all 7 TASS items gathered, none cited).
  This directly motivates backlog 999.1 (on-demand translation). Commit 232929e + verdict.
  Deviation: max_tokens 800→1100 (800 truncated section 4).

### Just-completed (R2, this session)

- **00-03-PLAN.md (R2 Norwegian Dedup Bake-off)**: mE5-large vs bge-m3 threshold sweep on 24-row
  hand-labeled corpus (13 yes / 11 no). bge-m3 disqualified (collapse_rate < 0.05 all thresholds).
  **mE5-large chosen @ threshold 0.84** (collapse_rate 0.783, control_overmerge 1). No pair cleared
  both bars — control set too topically narrow. Verdict: PARTIAL — mechanism + model GO; threshold
  needs held-out corpus in Phase 5. Commit: d5aacee. Input `title + summary[:512]`; `passage:`/`query:` prefixes.

### Just-completed (prior session)

- **00-04-PLAN.md (R3 Entity Resolution)**: pgvector cosine entity resolution proven via bge-m3
  1024-dim embeddings + HNSW index. 285 entities, 599 entity_links from 144-item corpus.
  NATO → 1 entity_id across 5 TASS items (all lang=ru). Control test PASS (Trump≠Putin).
  Verdict: PARTIAL — mechanism GO, cross-language coverage limited by corpus date (no NATO
  in NRK/BBC on 2026-06-25). Commit: 5c17666 (R3-VERDICT.md).

- **00-02-PLAN.md (R1 RabbitMQ Topology)**: InfoTriage AMQP topology proven on RabbitMQ 3.13 /
  pika 1.4.1. DLX-first declaration (infotriage.dlx → infotriage.dlq → infotriage.events → 4 primary
  queues). Publish→consume round-trip passed. All 4 event-type publisher confirms passed. Poison
  nack (requeue=False) dead-lettered to infotriage.dlq (depth=1). Verdict: GO.
  Commit: 39711a0 (R1-VERDICT.md).

- **00-01-PLAN.md (Spike Infra + Corpus)**: Ephemeral RabbitMQ (22060/22061) + pgvector (22062)
  containers running and healthy. 144-item NRK/BBC/TASS corpus fetched via defusedxml into
  `.spike/items.json`. `.spike/` gitignored. All infra prerequisites for R1-R5 now in place.
  Commits: 14ead5e (infra), f317cd4 (fetcher).

### Decisions recorded

- **R2 → mE5-large @ 0.84**: bge-m3 disqualified for Norwegian dedup (collapse_rate < 0.05).
  mE5-large locked as Q5 embedding model for ADR / Phase 5. Threshold 0.84 is a starting point —
  PARTIAL because no (model,threshold) cleared both bars on this narrow single-day corpus; Phase 5
  must recalibrate on a held-out corpus with genuinely off-topic controls.

- **R3 PARTIAL**: pgvector HNSW cosine entity resolution mechanism GO; cross-language NATO coverage
  limited by corpus date. Schema (entities+entity_links+HNSW), threshold 0.85, bge-m3 1024-dim
  validated for ADR-006 / Phase 8.

- **HNSW over IVFFlat**: No minimum rows needed; correct for small corpora and incremental inserts.

- **LINK_THRESHOLD=0.85**: Separates distinct persons (Trump/Putin sim ~0.72) while merging entity
  variants (NATO/НАТО sim ~0.92). Confirmed empirically on R3 corpus.

- **bge-m3 1024-dim CLS-pool vectors**: Validated for multilingual entity resolution; primary
  candidate for Phase 5/8. R2-VERDICT.md needed to confirm bake-off result.

- **torchvision nightly incompatibility (0.24.0.dev vs torch 2.11.0)**: Phase 5 env must resolve
  torch/torchvision version mismatch; spike used XLMRobertaModel direct import with mock.

- **R1 GO**: InfoTriage AMQP topology (topic exchange infotriage.events, 4 routing keys, DLX
  infotriage.dlx, DLQ infotriage.dlq) proven on RabbitMQ 3.13 — proceed to ADR-007.

- **pika 1.4.1 confirm API**: `channel.confirm_delivery()` method call; `basic_publish()` raises
  `NackError`/`UnroutableError` on rejection (no `wait_for_confirms()` method). Phase 3 must use
  `aio-pika` with `connect_robust()`.

- `defusedxml.ElementTree` exclusively for any network-sourced RSS/XML (stdlib parser forbidden — XXE, T-00-01-XXE).
- Spike port band: 22060 (RabbitMQ AMQP), 22061 (RabbitMQ mgmt), 22062 (pgvector Postgres); credentials `spike`/`spike`.
- `.spike/` gitignored wholesale; spike config files committed via `git add -f`; ephemeral data (items.json) not committed.

### Pending — Phase 00 plans

- 00-07-PLAN.md: Spike closeout (ADRs + SPIKE-FINDINGS.md + teardown) — all of R1-R5 now done; ready to run

### Infrastructure corrections (2026-06-25)

- **No Ollama** — removed from all docs and configs. Stack is oMLX (Mac) + vLLM (Spark) only.
- **DGX Spark now active** — vLLM serving qwen 80B at `http://192.168.10.2:8000/v1`, key=EMPTY. Spark has no internet; models must be transferred from Mac.
- **Embedder**:
  - Mac: `intfloat/multilingual-e5-large` (1024-dim) via oMLX
  - Spark: `Alibaba-NLP/gte-Qwen2-7B-instruct` (7B) via vLLM
- **New source — The Telegraph (UK)**: Added for Ukraine coverage. RSS blocked (bot detection). Recommended path: subscribe to Telegraph Ukraine newsletter → ingest via IMAP bridge (`bridge/imap_to_atom.py`). No new code needed until Phase 4.

### Carried-over open questions

- Q1 World Monitor CCIR/SAB coverage → **R5 spike** (still open).
- Q5 embedding model (bge-m3 vs mE5-large) → **DECIDED: mE5-large @ 0.84** (R2, PARTIAL — recalibrate Phase 5).

## Session

**Last session:** 2026-06-27T20:34:45.762Z
**Stopped at:** Phase 1 PLANNED — 3 plans (01-01..01-03) across 3 waves, verified, ready to execute
**Resume file:** None
