---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: In progress
stopped_at: "Phase 5 COMPLETE — 05-05 Task 3 parity gate MET (14/14), Fever cutover confirmed. Ready to plan Phase 6."
last_updated: "2026-07-02T06:38:50.000Z"
progress:
  total_phases: 13
  completed_phases: 5
  total_plans: 26
  completed_plans: 25
  percent: 38
---

# STATE — InfoTriage

> **Ephemeral.** Pick-up-next-session memory. Durable context lives in `docs/`, `PROJECT.md`,
> `REQUIREMENTS.md`, `ROADMAP.md`, `.planning/codebase/`. Trim aggressively.

## Session: 2026-07-02 — Phase 5 COMPLETE (05-05 Task 3 closed out)

### Just-completed

- **05-05-PLAN.md Task 3 (Shadow-run parity gate + Fever cutover, R6)**: Redeployed the
  05-03 `on_message` header fix (`89d6496`, committed but not yet deployed at session start —
  the prior session's HANDOFF.json/.continue-here.md were stale on this point). Found and fixed
  a second real bug: `docker-compose.yml`'s `LLM_BASE_URL` was silently reading the host `.env`'s
  `127.0.0.1:8000` value via Compose's automatic `.env` substitution instead of the intended
  `host.docker.internal` container default — every embed call failed with `Connection refused`.
  Hardcoded the container-only URL (commit `d9714fc`). Populated enrichment rows by republishing
  `item.ingested` via `rabbitmqadmin` for existing `infotriage.articles` rows (43 total, 0 DLQ
  failures). First `shadow_run.py` run showed 6/15 matching — diagnosed as a methodology bug, not
  a scoring bug: 9-29 of the rows were dedup short-circuits (D-01, `bucket=skip`, `why="duplicate
  of <id>"`, no LLM call) that a naive rescore always disagrees with. Fixed `shadow_run.py` to
  exclude dedup rows from the parity count (commit `f7430ef`). Corrected run: **14/14 genuinely-
  scored buckets matched (100%)** — parity verdict MET. Verified the host crontab fever entry was
  already absent (`crontab -l` → "no crontab for vidarbrevik") — R6's cutover end-state already
  satisfied, no removal action needed. **Phase 5 (Triage app) now 5/5 plans complete.**
  Commits: `d9714fc`, `f7430ef`, `1849f2a` (SUMMARY + ROADMAP + HANDOFF/continue-here cleanup).

### Decisions recorded

- **docker-compose.yml container env vars must never use `${VAR:-default}` for a var name that
  also exists in host `.env`** — Compose auto-loads the project `.env` for substitution, so a
  host-scoped value (e.g. `LLM_BASE_URL=127.0.0.1` for host scripts) silently overrides the
  container-appropriate default. Hardcode container-only values instead of relying on the
  fallback pattern when the var name collides with a host-side config need.
- **shadow_run.py / any future parity-style comparison must account for dedup short-circuits** —
  comparing a dedup-skip (no LLM call) against an independent rescore (which has no dedup
  awareness) measures dedup coverage, not scoring agreement. Exclude those rows from parity
  counts and report them separately.

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

## Session: 2026-06-30 — Phase 5 Wave 1 in progress (05-01 closed out)

### Just-completed

- **05-01-PLAN.md (Store extension)**: Commits (`0837fb0` test, `a98a5e0` migration, `eafc031`
  implement) landed in a prior session that ended before SUMMARY.md was written — execute-phase
  safe-resume gate caught the gap on resume. Verified green (12/12 tests, inmemory+db_live
  postgres; grep clean for forbidden `ADD CONSTRAINT IF NOT EXISTS`/f-string SQL) and closed out
  manually: wrote 05-01-SUMMARY.md, flipped ROADMAP.md checkbox via `roadmap.update-plan-progress`.
  006-enrichment.sql + put_enrichment/get_enrichment/put_embedding/find_near_duplicate now live on
  Protocol+Postgres+InMemory.

## Session: 2026-06-30 — Phase 5 Wave 1 complete (05-02 closed out)

### Just-completed

- **05-02-PLAN.md (Worker prerequisites)**: Added `RabbitMQBus.consume(routing_key, handler,
  prefetch_count=1)` — a persistent callback consumer (sibling to drain-only `subscribe()`,
  reuses `self._queues` keyed by routing_key and the existing topology; raises `ValueError` on
  an unknown routing key). Verified end-to-end against live RabbitMQ `:22001`
  (`tests/test_bus_consume.py -m rabbitmq`, 2/2 passed; existing `test_bus_rabbitmq.py` 5/5
  still green). Also applied D-02: `apps/triage/triage_score.py` no longer caches `ccir.md` at
  import time — `score_item()` now calls `load_ccir()` as its first statement and the prompt
  f-string reads the local `{ccir}`, so operator edits to `ccir.md` take effect on the very
  next scoring call (D-5). Regression test `tests/test_triage_score_hotread.py` proves this via
  monkeypatched `CCIR_PATH` + a prompt-capturing `llm` stub. TDD throughout (RED commits
  `e049a71`, `1d3b2db`; GREEN commits `a1e05e1`, `260d7b5`). 210+7 tests green project-wide, no
  regressions. Both Wave-1 worker prerequisites (05-03 depends on) now in place.

## Session: 2026-06-30 — Phase 5 Wave 2 complete (05-03 closed out)

### Just-completed

- **05-03-PLAN.md (Triage worker)**: Built `apps/triage/worker.py`, the D-01 event-driven
  entry point. `process_item(item_id, store, bus, *, embed, score)` is the async testable
  core: `get_item` → mE5-large embed + `find_near_duplicate` dedup check (LLM call skipped
  entirely on a hit, `bucket=skip`/`why="duplicate of <id>"`) → `score_item()` against
  `ccir.md` (non-dup path) → `clamp_score` to `[0,10]` → `put_enrichment` (raw vocabulary)
  → `put_embedding` (always, dup or not) → `VerdictReady` (mapped vocabulary via
  `map_cnr`/`map_bucket`) → `bus.publish("verdict.ready", ...)`. Enrichment write commits
  before publish in every path; a `put_enrichment` failure propagates so `on_message`'s
  `message.process()` nacks instead of acking (R2/R5 prohibition). Each blocking call runs
  via `asyncio.to_thread` individually (not the whole pipeline as one block) so
  `bus.publish` always executes on the consumer's own event loop — avoids an aio-pika
  cross-event-loop bug that a naive "wrap process_item in one to_thread" reading of the
  plan would have introduced. `_handle_health`/`run_health_server` (D-04) serve a
  liveness-only `/health` alongside the consumer under `asyncio.gather` (D-03). TDD
  throughout (RED commit `519ea87`; GREEN commit `30d1baa`; health test `db3d714`). 9/9 new
  tests green, 219 project-wide, no regressions.

## Session: 2026-07-01 — Phase 5 Wave 3 complete (05-04 closed out)

### Just-completed

- **05-04-PLAN.md (Triage container)**: Containerized `apps/triage/worker.py` as the
  `infotriage-triage` service on `127.0.0.1:22030`. `apps/triage/Dockerfile` mirrors
  `apps/ingest-imap`'s local-lib install pattern (`COPY libs/contracts`/`libs/store` →
  `pip install --no-deps` → app `requirements.txt` → app source → non-root `USER triage`
  → `CMD ["python", "worker.py"]`), no credential ARG/ENV baked in. `docker-compose.yml`
  triage stanza adds a python-urllib healthcheck (no curl in `python:3.12-slim`),
  `extra_hosts host.docker.internal:host-gateway` for the host oMLX endpoint (ADR-004 —
  local only), and `depends_on` postgres+rabbitmq with `condition: service_healthy`.
  Task 3's blocking live-verify checkpoint confirmed `/health` → 200, non-root user,
  no DSN leak in logs, and `connect_robust` auto-reconnect surviving a RabbitMQ
  stop/start (re-confirmed independently in this continuation session via
  `rabbitmqctl list_connections`/`list_queues` showing the worker's connection still
  `running` and `q.triage` with an active consumer, days after the original test).
  Operator approved. Commits `aff9373` (Dockerfile/requirements.txt), `9910278`
  (docker-compose.yml).
  - Deviation (Rule 3): `requirements.txt` needed `feedgen`/`pydantic`/`PyYAML` beyond
    the plan's literal `aio-pika`/`psycopg[binary]`/`pgvector` — `libs/store` and
    `libs/contracts` are installed `--no-deps` and import these at module level.
  - Known gap (non-blocking): `intfloat/multilingual-e5-large` is not yet registered
    on the host oMLX instance — `worker.py`'s `get_embedding()` will 404 on a real
    end-to-end run until that model is set up. Tracked as a Phase 5 follow-up.

## Session: 2026-07-01 — Phase 5 Wave 4 (05-05) BLOCKED on Task 3

### Just-completed

- **05-05-PLAN.md Tasks 1-2**: `scripts/shadow_run.py` built (reads `infotriage.enrichment`
  joined to `infotriage.articles`, re-runs `score_item()` standalone, prints side-by-side
  bucket parity table + `>= 10` verdict — commit `49f1822`). README.md updated to document
  the triage container (`docker compose up -d triage`, port 22030) as the scoring path;
  fever_triage.py run-commands/crontab line marked retired, file itself preserved for
  `digest.py` imports (commit `e846d94`).

### Blocked — Task 3 (shadow-run parity checkpoint + Fever cutover)

Two independent, pre-existing blockers, confirmed live (not guessed):

1. **Embedder gap (already known, from 05-04)**: `intfloat/multilingual-e5-large` is not
   registered on the host oMLX instance. Reproduced directly: `POST host.docker.internal:8000/v1/embeddings`
   from inside the `infotriage-triage` container → clean `404`. Docker networking itself is
   fine (`host.docker.internal` resolves and `/health` returns 200) — this is purely a
   missing-model-registration issue on the host, not a bug in 05-04's compose config.
2. **New finding — `infotriage.articles` has 0 rows.** This contradicts this STATE.md's
   earlier note about "111 existing articles" (stale — likely referred to the old `.spike/`
   corpus from Phase 0, torn down before Phase 5). `infotriage-postgres` has a persistent
   volume (`./data/postgres`) and has been up ~14h; `ingest-youtube`/`ingest-imap` have been
   up ~41-42h and `ingest-youtube` shows multiple successful `POST /run` (200 OK) calls from
   the scheduler in that window, yet zero rows landed in `infotriage.articles`. Root cause
   NOT diagnosed — could be no-new-content-found each run, a silent `persist_and_publish`
   failure, or a Postgres data reset independent of Phase 5. Needs separate investigation
   (not attempted this session — operator chose to defer and investigate later).

Even if the embedder were fixed today, Task 3 still can't proceed with zero source articles.
Both must be resolved before `/gsd-execute-phase 5` can complete Task 3 (or `--gaps-only`/manual
close-out once resolved). Task 3 is NOT committed, no SUMMARY.md was written, ROADMAP.md still
shows 05-05 incomplete — this is intentional, do not mark it done.

### Follow-up — embedder gap RESOLVED (host-only change, no repo commit)

Registered `intfloat/multilingual-e5-large` on the local oMLX instance (standard HF safetensors —
oMLX's `mlx-embeddings` backend natively supports the `XLMRobertaModel` architecture, no MLX
conversion needed). Steps: `hf download intfloat/multilingual-e5-large --local-dir
~/.omlx/models/multilingual-e5-large`, stripped the redundant `onnx/`/`openvino/`/`pytorch_model.bin`
export formats oMLX doesn't use (8.9GB → 2.1GB), killed the running server (PID tracked in
`~/.omlx/claude-mlx.serve.pid`; `omlx-cli restart` doesn't recognize servers it didn't launch
itself, so used the same kill+`omlx-ensure-server` path the Mac already relies on), let it come
back and rescan `~/.omlx/models`.

**Model-id resolution note:** the directory is named `multilingual-e5-large` (no `intfloat/`
prefix — oMLX's model-dir discovery uses the bare leaf directory name as the model_id). This
still works with `worker.py`'s literal `"model": "intfloat/multilingual-e5-large"` request
because oMLX's `resolve_model_id()` strips an `org/` prefix and matches the remainder against
registered entries (`engine_pool.py` line ~343) — confirmed working, not just directory-inferred.

Verified live: `POST /v1/embeddings` with the exact body `worker.py`'s `get_embedding()` sends
returns `200`, 1024-dim vector — reproduced both from the host (4.7s cold) and from inside
`infotriage-triage` via `host.docker.internal:8000` (0.5s warm). Existing models
(`qwen36-ud-4bit`, `gpt-oss-20b`, etc.) confirmed still registered post-restart — no regression.

**Remaining blocker for 05-05 Task 3:** `infotriage.articles` still has 0 rows (see above) —
untouched this session, still needs separate investigation.

## Session

**Last session:** 2026-07-01T12:18:09.444Z
**Stopped at:** Phase 5 Wave 4 — embedder gap fixed; 05-05 Task 3 still BLOCKED (empty infotriage.articles)
**Resume file:** .planning/phases/05-triage-app/05-05-PLAN.md

## Performance Metrics

| Phase | Plan | Duration | Notes |
|-------|------|----------|-------|
| Phase 02 P01 | 10 | 3 tasks | 10 files |
| Phase 02 P03 | 732 | 3 tasks | 4 files |
| Phase 03 P01 | 21 | 7 tasks | 5 files |
| Phase 05 P02 | 12min | 2 tasks | 4 files |
| Phase 05 P03 | 22min | 3 tasks | 3 files |
| Phase 05 P04 | continuation | 3 tasks | 3 files |

## Decisions

- [Phase ?]: register_vector in init_schema must run AFTER DDL
- [Phase ?]: postgres fixture requires TRUNCATE before each test for isolation
- [Phase ?]: DLX infotriage.dlx declared before primary queues (prevents 406 PRECONDITION_FAILED)
- [Phase ?]: x-dead-letter-routing-key=dead for all primary queues routes nacked messages to infotriage.dlq
- [Phase ?]: aio-pika async transport for RabbitMQ bus with connect_robust auto-reconnect and topology migration handler
- [Phase ?]: consume() added as a sibling method on RabbitMQBus only (not BusClient Protocol) per RESEARCH Open Q2; subscribe() untouched
- [Phase 05]: 05-03: process_item runs async with per-call asyncio.to_thread (not a sync function run as a whole via asyncio.to_thread) so bus.publish always executes on the consumer's event loop, avoiding aio-pika cross-event-loop bugs
- [Phase 05]: 05-04: requirements.txt needs feedgen/pydantic/PyYAML beyond aio-pika/psycopg/pgvector — libs/store and libs/contracts are installed --no-deps and import these at module level
- [Phase 05]: 05-04: intfloat/multilingual-e5-large not yet registered on host oMLX — worker.py's get_embedding() will 404 until set up; tracked as a Phase 5 follow-up, non-blocking for 05-04. **RESOLVED 2026-07-01**: registered at ~/.omlx/models/multilingual-e5-large (standard HF safetensors via mlx-embeddings' native XLMRobertaModel support), verified 200/1024-dim from host and from inside infotriage-triage.
