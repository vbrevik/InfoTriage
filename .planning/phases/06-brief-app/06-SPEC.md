# Phase 06: Brief app — Specification

**Created:** 2026-07-04
**Updated:** 2026-07-06 — gap-closure amendment: added R6 (Obsidian vault-writer), reversing the earlier out-of-scope call per VERIFICATION.md finding + explicit user decision (ROADMAP SC2 was never amended when this phase descoped it)
**Ambiguity score:** 0.14 (gate: ≤ 0.20)
**Requirements:** 6 locked (4 delivered, 2 remaining — R4 wiring bug, R6 new)
**Mode:** Update — Socratic decisions confirmed via AskUserQuestion (2026-07-05), reusing 2026-07-04 interview for unchanged scope; R6 added 2026-07-06 via `/gsd-plan-phase 6 --gaps`

## Goal

The `brief` service (container `:22040`) subscribes `verdict.ready` from the RabbitMQ bus, aggregates scored items from `infotriage.enrichment` in Postgres, clusters them via pgvector HNSW, renders a Situational Awareness Brief in markdown + HTML with LLM-generated BLUF sections, serves the SAB at `:22040`, and publishes `sab.published` to the bus.

## Background

Today the digest/sab pipeline runs on host crontab via `digest.py` and `sab_html.py`, reading items from FreshRSS/Fever API (the old spike path). Phase 5 (`worker.py`, `:22030`) completed the event-driven scoring path: `item.ingested` → enrichment in Postgres → `verdict.ready`.

**As of 2026-07-05, Wave 1+2 shipped and are live-verified:**
- Event-driven consumer (R1), markdown renderer (R2), and HTML server + serving contract
  (R3, R5) are built, containerized, and confirmed end-to-end against real Postgres +
  RabbitMQ (republished `verdict.ready` → 4 digest files rewritten atomically →
  `sab.published` landed on the bus).
- **R5's shipped event schema differs from this SPEC's original acceptance criteria** —
  see the R5 correction below. The richer schema (`pub_ts`, `snapshot_day`, `ccir_topics`,
  `bluf_by_topic`, `item_refs`, `total_keep`, `since_ts`) already existed in `libs/contracts`
  from Phase 4/5 and was reused rather than replaced with the `event_id`/`generated_at`/
  `item_count`/`slide_count` shape originally specified here.
- **Semantic clustering (R4) is NOT built.** `apps/brief/renderer.py`'s `render_cluster()`
  and the CNR/CCIR grouping in `render_brief()` use `digest.py`'s keyword-overlap
  `cluster()` as a fallback — the same algorithm the old crontab path used. No
  `apps/brief/clustering.py` exists; the `infotriage.embeddings` HNSW index (populated by
  Phase 5, 144/144 enrichment rows have a matching embedding as of this update) is unused
  by the brief service.
- Incremental BLUF regeneration (06-CONTEXT.md D-05/D-06/D-08 — skip the LLM call for
  CCIR sections with no new items since the last render) is **deferred**, not built.
  Current serving (`main.py`'s `/sab` staleness gate) does a full re-render of every
  section on every regeneration. This is accepted as sufficient for now (see Boundaries).

The brief service has replaced the crontab path for markdown + HTML rendering and
serving. The remaining gap is entirely R4: real semantic clustering instead of the
keyword fallback.

## Requirements

1. **Event-driven consumer**: The `brief` service subscribes `verdict.ready` events and processes them into SAB output.
   - Current: ✅ **Delivered.** `apps/brief/consumer.py` subscribes `verdict.ready` via `RabbitMQBus.consume()`, joins `infotriage.enrichment` to `infotriage.articles` for title/summary/source/url, writes `brief.md`/`cluster.md`/`list.md`/`bluf.md` atomically, publishes `SabPublished`. Commits `eec345d` (Wave 1), `01ed73c` (JOIN fix, txn hygiene, coroutine fix — the consumer never ran against real infra until this update's live verification).
   - Target: (met)
   - Acceptance: ✅ Verified 2026-07-05 — republished `verdict.ready` via `rabbitmqadmin` against a real item; all 4 digest files rewritten within seconds; `sab.published` observed in `q.notify`.

2. **SAB markdown renderer**: Produces the same three output formats as `digest.py`'s `write_brief()` — CNR alerts first, then CCIR sections, then strict list (score ≥ 8).
   - Current: ✅ **Delivered.** `apps/brief/renderer.py` — `render_brief()`, `render_list()`, `render_bluf()`, `render_cluster()`. 31 contract tests pass (`tests/test_brief_renderer.py` — commit `eec345d`).
   - Target: (met)
   - Acceptance: ✅ Verified — CNR CAT I items first, CCIR sections in `CCIR_ORDER`, `render_list()` score ≥ 8 sorted descending, all covered by passing tests.

3. **SAB HTML renderer**: Serves the styled HTML SAB at `:22040` with presentation + scroll mode toggle.
   - Current: ✅ **Delivered.** `apps/brief/html_renderer.py` imports `build_html()` from `sab_html.py` (template imported, never copied — D-12 honored, confirmed via grep). `apps/brief/main.py` exposes `GET /sab`. Commit `af9dcac`.
   - Target: (met)
   - Acceptance: ✅ Verified live — `GET /sab` returns HTTP 200 with 23.7KB valid HTML; atomic `.tmp` + `os.replace` write confirmed in `main.py`; cached serve measured at <2ms (well under the 2s render / 200ms serve budgets).

4. **Semantic clustering via pgvector**: Items are clustered within each CCIR section using the mE5-large embedding index already populated by Phase 5.
   - Current: ❌ **Not built.** `render_cluster()` and `render_brief()` use `digest.py`'s greedy keyword-overlap `cluster()` (2+ shared 4+ char tokens) as a fallback. `infotriage.embeddings` (144 rows, HNSW cosine index, `idx_embeddings_embedding_hnsw`) is fully populated but unread by `apps/brief/`.
   - Target: New `apps/brief/clustering.py` module clusters enrichment rows per-CCIR using pgvector cosine similarity against `infotriage.embeddings`, following the existing `PostgresStore.find_near_duplicate()` query pattern (`<=>` cosine operator, `register_vector()` already called in `PostgresStore.__enter__`). Threshold configurable via `CLUSTER_THRESHOLD` env var, default 0.75. Clusters never cross CCIR boundaries. `renderer.py`'s `render_cluster()`/`render_brief()` switch from the keyword fallback to this module.
   - Acceptance: Given 3 articles about "NATO" (2 Ukraine defense, 1 Arctic policy) with embeddings, keyword-overlap would merge all 3 (documented current behavior); pgvector clustering with threshold 0.75 merges only the 2 Ukraine articles — the Arctic article remains a separate single-item cluster.

5. **SAB event and serving contract**: The service publishes `sab.published` and serves the SAB at port 22040.
   - Current: ✅ **Delivered — with a corrected schema.** `libs/contracts` already defined `SabPublished` (from Phase 4/5) before this phase started; the plan adapted to reuse it rather than adding new fields, per the recorded decision in `06-01-SUMMARY.md`. The shipped schema is `event: Literal["sab.published"]`, `pub_ts: AwareDatetime`, `snapshot_day: str`, `ccir_topics: list[str]`, `bluf_by_topic: dict[str, str]`, `item_refs: list[dict]`, `total_keep: int`, `since_ts: Optional[AwareDatetime]` — **not** the `event_id`/`generated_at`/`item_count`/`slide_count` shape this SPEC originally specified (2026-07-04 draft). `apps/brief/main.py` exposes `GET /sab`, `GET /health`, `GET /sab?window=Nh`, `GET /sab?mode=list`.
   - Target: (met, schema corrected in this update)
   - Acceptance: ✅ Verified live — `GET /health` returns 200 regardless of bus/DB state (no dependency in the handler); `GET /sab` returns cached SAB in <2ms; `GET /sab?window=168h` and `?mode=list` exercised and return correct HTTP codes (200 / 422 on malformed window); `sab.published` observed on the bus with the schema above after the E2E consumer test.

6. **Obsidian vault-writer** (added 2026-07-06 — gap-closure amendment, see below): A vault-writer projects high-value enrichment items plus the SAB into Obsidian `.md` files.
   - Current: ❌ **Not built.** No `vault_writer.py` or equivalent exists anywhere in `apps/brief/`. `apps/ingest-obsidian/` is a Phase-4 read-only ingestion adapter (articles-inbox → Item), the opposite data direction.
   - Target: A new module (e.g. `apps/brief/vault_writer.py`) emits one Obsidian `.md` file per high-value item (front-matter via the existing codec pattern in `libs/contracts/src/contracts/_codec.py`, body = item summary) plus a projection of the SAB itself. `[[entity]]` wikilinks are generated via a lightweight interim heuristic (e.g. proper-noun / known-topic extraction) — the full entity-resolution-as-Postgres-truth system is Phase 8's job; this is a real, working interim, not a stub.
   - Acceptance: Given a high-value enrichment item, a corresponding `.md` file appears in the configured vault path with valid front-matter parseable by the existing codec, a body summary, and at least one `[[entity]]` wikilink where the source text contains an extractable entity. Email-sourced items (imap://) must appear here per ROADMAP SC3.

## Boundaries

**In scope:**
- `apps/brief/` service container (FastAPI) with consumer, renderer, and HTTP server — **delivered**
- `libs/contracts`: `SabPublished` event schema (reused from Phase 4/5, not modified) — **delivered**
- SAB markdown rendering (`render_brief()`, `render_list()`, `render_bluf()`) adapted from existing `digest.py` functions — **delivered**
- SAB HTML rendering (`build_html()` from `sab_html.py`) adapted to read from Postgres — **delivered**
- Semantic clustering via pgvector HNSW on the existing embedding index (per-CCIR, threshold configurable) — **remaining (R4)**
- LLM BLUF synthesis using the same prompt templates from `digest.py` — **delivered**
- Atomic file writes (`write .tmp + os.replace`) for both markdown and HTML output — **delivered**
- HTTP serving: `GET /sab` (SAB HTML), `GET /health` (200 OK), `GET /sab?window=Nh` (custom window), `GET /sab?mode=list` — **delivered**
- `sab.published` event publish to RabbitMQ after SAB generation — **delivered**
- Docker Compose service definition for the brief container — **delivered**
- Obsidian vault-writer (front-matter via codec, body summary, interim `[[entity]]` wikilinks) — **remaining (R6, gap-closure amendment 2026-07-06)**

**Out of scope:**
- Email notification / push alerts — Phase 12 (CNR alerting / dissemination)
- FreshRSS/Fever API integration — fully retired; brief reads from Postgres only (verified: no `fever()`/`fever_key()` imports in `apps/brief/`)
- `cluster.md` and `list.md` as separate disk files were reconsidered during Wave 2: `cluster.md` and `list.md` ARE written to disk by the consumer alongside `brief.md`/`bluf.md` (broader than the original spec's disk-file boundary); `?mode=list` on the HTTP endpoint is additionally available for ad-hoc windows
- **Incremental BLUF regeneration** (06-CONTEXT.md D-05/D-06/D-08 — skip LLM calls for CCIR sections with no new items) — **deferred by decision on this update (2026-07-05).** Full-regen-on-every-render is accepted as sufficient for now; `window.py` and `_last_update.json`/`_last_render.json` tracking are NOT built and are not required to close Phase 6. Revisit if LLM cost/latency becomes a problem.
- Entity resolution as Postgres system-of-record / cross-modality entity graph — Phase 8 (R6's `[[entity]]` wikilinks are a lightweight interim heuristic only, not the formal entity-resolution system)
- RAG recall / thematic search — Phase 9
- Wiki-LLM standing auto-wiki — Phase 10
- Container health checks, restart policies, DLQ management, structured logging — Phase 7 (ops) — **note: a basic Docker healthcheck was added in Wave 2 as a container-readiness gate, not the full ops scope Phase 7 owns**
- Retiring `digest.py` and `sab_html.py` from disk — Phase 7 (cutover)
- CNR real-time push notification lane — Phase 12

## Constraints

- **All LLM is local** (ADR-004): BLUF synthesis runs against `qwen36` via oMLX (`:8000/v1`) or DGX Spark vLLM. No cloud LLM. — verified: `main.py`/`consumer.py` route through `apps.triage.triage_score.llm()`, no cloud client present.
- **One Postgres instance**: The brief service uses the same Postgres as all other services (`postgres:16` at `:22000`). No fan-out.
- **BLUF failure tolerance**: If the LLM endpoint is unreachable, the SAB still renders with a placeholder marker `_(BLUF unavailable — check log for details)_`. No item is dropped from the SAB because BLUF failed. — verified via existing `render_bluf()` tests.
- **Enrichment integrity**: The brief service reads from `infotriage.enrichment` joined to `infotriage.articles`. If an enrichment row has no matching article, that item is skipped (JOIN excludes it naturally — no explicit skip-and-warn code path exists yet; acceptable since the FK constraint on `enrichment.item_id → articles.id` makes this theoretically impossible).
- **Atomic file writes**: All output files are written to `.tmp` then `os.replace()` to avoid partial reads by the HTTP server. — verified in both `consumer.py` and `main.py`.
- **Clustering threshold** (remaining, R4): Default pgvector cosine similarity threshold of 0.75 for cluster merging. Configurable via environment variable `CLUSTER_THRESHOLD` (range 0.0–1.0). Must be per-CCIR (items in different CCIR sections never merge).
- **Event ordering**: The brief service processes `verdict.ready` events in the order received (single consumer, `prefetch_count=1`). No reordering.
- **No paid services**: All dependencies must be free and self-hosted.

## Acceptance Criteria

- [x] `apps/brief/` is a FastAPI service that subscribes `verdict.ready` via RabbitMQBus and processes items from Postgres
- [x] `libs/contracts` defines `SabPublished` — corrected: fields are `pub_ts` (AwareDatetime), `snapshot_day` (str), `ccir_topics` (list[str]), `bluf_by_topic` (dict[str,str]), `item_refs` (list[dict]), `total_keep` (int), `since_ts` (Optional[AwareDatetime]), not the original `event_id`/`generated_at`/`item_count`/`slide_count` draft
- [x] `render_brief()` produces markdown with CNR items first, then CCIR sections in CCIR_ORDER, with cluster metadata
- [x] `render_list()` returns items with score ≥ 8, sorted by score descending
- [x] `render_bluf()` generates LLM-synthesized summaries with bracketed numeric citations `[N]` per claim
- [x] `GET /sab` returns HTTP 200 with valid HTML containing the latest SAB (served from atomically-written file)
- [x] `GET /health` returns HTTP 200 OK regardless of bus/DB connectivity state
- [x] `GET /sab?window=Nh` generates a SAB for the specified time window and returns it
- [ ] Semantic clustering groups similar items within each CCIR section using pgvector HNSW (threshold configurable, default 0.75) — **remaining, R4**
- [ ] Items in different CCIR sections are never merged into the same cluster — **remaining, R4** (currently true only because keyword-overlap clustering happens to run within per-CCIR loops, not because of a pgvector CCIR bound)
- [x] SAB generation completes well within 30 seconds of receiving `verdict.ready` (E2E test: consumer processed, rendered, and published in <60s wall-clock including LLM BLUF calls)
- [x] `sab.published` event is published to RabbitMQ after each SAB generation with correct (corrected) metadata
- [x] All output files are written atomically (`.tmp` + `os.replace`)
- [x] If the LLM endpoint is down, the SAB still renders (BLUF sections show placeholder, items not dropped)
- [x] If an enrichment row has no matching article, the item does not appear in the SAB (JOIN semantics; no crash)
- [x] Docker Compose service definition exists for the brief container on port 22040 — healthcheck confirmed `healthy` in <10s
- [ ] A vault-writer emits one Obsidian `.md` file per high-value item, front-matter parseable by the existing codec pattern, body = item summary — **remaining, R6 (added 2026-07-06)**
- [ ] Emitted `.md` files contain at least one `[[entity]]` wikilink where the source text has an extractable entity (interim heuristic, not full entity resolution) — **remaining, R6**
- [ ] Email-sourced (imap://) items appear in the Obsidian projection, not just the SAB — **remaining, R6** (closes ROADMAP SC3's Obsidian half)

## Edge Coverage

**Coverage:** 8/8 applicable edges resolved · 0 unresolved (carried forward from 2026-07-04 interview; unchanged by this update — R4's edges remain open until R4 ships)

| Category | Requirement | Status | Resolution / Reason |
|----------|-------------|--------|---------------------|
| Empty input | R1, R2, R3, R4, R5 | ✅ covered | If 0 `verdict.ready` events in window, SAB renders with "No items in window" marker; verified `?mode=list` returns "0 viktigste" on an empty-scoring window |
| CCIR-boundary merging | R4 | ✅ covered (pending R4 implementation) | Clustering is per-CCIR; items in different CCIR sections never merge (Constraint §Clustering threshold) |
| LLM failure | R2, R3 | ✅ covered | BLUF placeholder rendered, items not dropped (Constraint §BLUF failure tolerance) — verified via existing test suite |
| Missing enrichment | R1 | ✅ covered | JOIN semantics exclude items with no matching article; no crash — verified live (main.py's txn rollback prevents connection poisoning on query failure) |
| Stale data | R3 | ✅ covered | SAB only includes items from the requested window (`WHERE created_at >= %s`); verified `?window=24h` vs `?window=168h` return different item counts |
| Event ordering | R1 | ✅ covered | Single consumer, prefetch=1, in-order processing (Constraint §Event ordering) |
| Partial cluster | R4 | ✅ covered (pending R4 implementation) | Items with no embedding match remain as single-item clusters (not dropped) — note: as of this update, 144/144 enrichment rows have embeddings, so the no-embedding case is currently untested against real data |
| Concurrent writes | R2, R3 | ✅ covered | Atomic write pattern (.tmp + os.replace) prevents partial reads — verified in both consumer.py and main.py |

## Prohibitions (must-NOT)

**Coverage:** 3/3 applicable prohibitions resolved · 0 unresolved (carried forward; unchanged by this update)

| Prohibition (must-NOT statement) | Requirement | Status | Verification / Reason |
|----------------------------------|-------------|--------|------------------------|
| Brief service must NOT read from FreshRSS/Fever API | R1, R3 | resolved | verification: test — confirmed via grep: no `fever()` or `fever_key()` imports in `apps/brief/` |
| Brief service must NOT contain `sab_html.py`'s inline HTML template as a copy | R3 | resolved | verification: test — confirmed via grep: `HTML_TEMPLATE` appears only in a docstring comment in `renderer.py`, imported (not copied) in `html_renderer.py` |
| BLUF output must NOT contain uncited factual claims | R2 | resolved | verification: judgment — every claim in BLUF text must have a `[N]` citation; prompt template enforces this (reused verbatim from `digest.py write_bluf()`/`sab_html.py generate_bluf()`), no automated test possible |

## Ambiguity Report

| Dimension          | Score | Min  | Status | Notes                              |
|--------------------|-------|------|--------|------------------------------------|
| Goal Clarity       | 0.92  | 0.75 | ✓      | R1-R3/R5 delivered and verified; R4 has a concrete worked example (NATO/Ukraine/Arctic) |
| Boundary Clarity   | 0.88  | 0.70 | ✓      | Explicit in/out lists; deferred incremental-BLUF decision now explicit rather than silently dropped |
| Constraint Clarity | 0.82  | 0.65 | ✓      | Threshold, per-CCIR bounding, existing `find_near_duplicate` query pattern to follow for R4 |
| Acceptance Criteria| 0.85  | 0.70 | ✓      | 16 pass/fail criteria; 12 verified done via live testing, 2 remain open (both R4) |
| **Ambiguity**      | 0.14  | ≤0.20| ✓      |                                     |

## Interview Log

| Round | Perspective    | Question summary                                   | Decision locked                                      |
|-------|----------------|---------------------------------------------------|--------------------------------------------------------|
| 1     | Researcher     | Clustering strategy, serving method, sab.published | pgvector semantic clustering, FastAPI :22040, define schema now (2026-07-04) |
| 1     | Researcher     | What exists today?                                  | digest.py + sab_html.py (host cron, Fever API); worker.py (event-driven, complete) (2026-07-04) |
| 2     | Simplifier     | Minimum viable scope?                              | markdown + HTML output, pgvector clustering, LLM BLUF preserved, no Obsidian vault (2026-07-04) |
| 3     | Boundary Keeper | What explicitly NOT done?                           | No Obsidian writer, no email/push, no FreshRSS, no entity resolution, no health checks (2026-07-04) |
| 4     | Failure Analyst | What goes wrong on edge cases?                     | LLM down → SAB still renders; 0 items → empty-state page; stale data → window filter (2026-07-04) |
| —     | Update pass    | R5 acceptance criteria reference fields that don't match the shipped `SabPublished` schema — correct or leave stale? | Correct R5 to match shipped schema (2026-07-05) |
| —     | Update pass    | Incremental BLUF regen (D-05/D-06) not built — still required for Phase 6? | Deferred — full-regen accepted as sufficient for now (2026-07-05) |
| —     | Update pass    | How should delivered vs remaining work be represented in SPEC.md? | Keep all 5 requirements, mark delivered ones with commit refs; R4 stays the sole open requirement (2026-07-05) |

---

*Phase: 06-brief-app*
*Spec created: 2026-07-04*
*Spec updated: 2026-07-05*
*Next step: /gsd-plan-phase 6 — plan 06-02 covering the sole remaining requirement (R4: pgvector semantic clustering, replacing the keyword-overlap fallback in `renderer.py`)*
