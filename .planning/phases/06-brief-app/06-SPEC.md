# Phase 06: Brief app — Specification

**Created:** 2026-07-04
**Ambiguity score:** 0.15 (gate: ≤ 0.20)
**Requirements:** 5 locked
**Mode:** --auto (all decisions auto-selected from codebase scoping and Socratic interview)

## Goal

The `brief` service (container `:22040`) subscribes `verdict.ready` from the RabbitMQ bus, aggregates scored items from `infotriage.enrichment` in Postgres, clusters them via pgvector HNSW, renders a Situational Awareness Brief in markdown + HTML with LLM-generated BLUF sections, serves the SAB at `:22040`, and publishes `sab.published` to the bus.

## Background

Today the digest/sab pipeline runs on host crontab via `digest.py` and `sab_html.py`, reading items from FreshRSS/Fever API (the old spike path). Phase 5 (`worker.py`, `:22030`) completed the event-driven scoring path: `item.ingested` → enrichment in Postgres → `verdict.ready`. The `digest.py` still pulls from Fever for its `fetch_window()` — a legacy dependency that will be fully retired in Phase 7.

No event-driven brief app exists. No `sab.published` event schema is defined in contracts. The HTML SAB (`sab_html.py`, 1206 lines) and markdown brief (`digest.py` `write_brief()`) are proven and tested but not integrated into the new microservice architecture. The brief service must replace the crontab path, not duplicate it.

The operator's reading surface is SAB + Obsidian; FreshRSS is now an optional projection only. Phase 6 establishes the SAB as a service, not a cron script.

## Requirements

1. **Event-driven consumer**: The `brief` service subscribes `verdict.ready` events and processes them into SAB output.
   - Current: No brief consumer exists; SAB generation is driven by host crontab calling `digest.py` and `sab_html.py` against FreshRSS/Fever
   - Target: `apps/brief/` FastAPI service subscribes `verdict.ready` via `RabbitMQBus.consume()`, processes items from `infotriage.enrichment` in Postgres, generates SAB markdown + HTML, writes files atomically, publishes `sab.published`
   - Acceptance: After a `verdict.ready` is published by the triage worker, the brief service produces SAB files within 30 seconds and `sab.published` appears on the bus

2. **SAB markdown renderer**: Produces the same three output formats as `digest.py`'s `write_brief()` — CNR alerts first, then CCIR sections, then strict list (score ≥ 8).
   - Current: `digest.py` has `write_brief()`, `write_cluster()`, `write_list()` — all reading from Fever API verdict dicts
   - Target: `apps/brief/renderer.py` with `render_brief()`, `render_list()`, `render_bluf()` adapted to read enrichment rows from Postgres instead of Fever dicts; same CCIR_ORDER, same clustering logic (replaced with pgvector semantic clustering), same BLUF prompt templates
   - Acceptance: Given 5 enrichment rows with known scores/CCIR/cnr values, `render_brief()` produces markdown with CNR items first, then CCIR sections in CCIR_ORDER, with cluster metadata; `render_list()` produces items with score ≥ 8 sorted by score descending

3. **SAB HTML renderer**: Serves the styled HTML SAB at `:22040` with presentation + scroll mode toggle.
   - Current: `sab_html.py` is a CLI tool that reads `data/verdicts.jsonl` and writes `data/digests/sab.html` — contains a 760-line inline HTML template with CSS + JS
   - Target: `apps/brief/html_renderer.py` that imports the existing HTML template from `sab_html.py`, adapts `build_html()` to read from Postgres enrichment rows instead of `verdicts.jsonl`, writes the file atomically, and exposes `GET /sab` serving the latest file
   - Acceptance: `GET /sab` returns HTTP 200 with valid HTML; file is updated via write-to-tmp + `os.replace` pattern; rendering a SAB with 10 CCIR sections takes < 2 seconds

4. **Semantic clustering via pgvector**: Items are clustered within each CCIR section using the mE5-large embedding index already populated by Phase 5.
   - Current: `digest.py` uses greedy keyword-overlap clustering (`keywords()` function, 2+ shared 4+ char tokens)
   - Target: Clustering uses the existing `infotriage.embeddings` table (cosine similarity, HNSW index) with a similarity threshold; clusters are per-CCIR (CCIR-bounded to avoid cross-domain merges); the threshold and merge strategy are configurable
   - Acceptance: Given 3 articles about "NATO" (2 Ukraine defense, 1 Arctic policy), keyword-overlap would merge all 3; pgvector clustering with threshold 0.75 merges only the 2 Ukraine articles; the Arctic article remains separate

5. **SAB event and serving contract**: The service publishes `sab.published` and serves the SAB at port 22040.
   - Current: No `sab.published` event schema; no service port 22040
   - Target: `libs/contracts` defines the `SabPublished` event with `event_id`, `generated_at` (ISO 8601 UTC), `item_count` (int), `slide_count` (int). The FastAPI app exposes `GET /sab` (SAB HTML), `GET /health` (200 OK, liveness-only), `GET /sab?window=24h` (regenerate with custom window)
   - Acceptance: `GET /health` returns 200 OK regardless of bus/DB state; `GET /sab` returns the latest SAB HTML within 200ms; `sab.published` event published with correct metadata after each SAB generation

## Boundaries

**In scope:**
- `apps/brief/` service container (FastAPI) with consumer, renderer, and HTTP server
- `libs/contracts`: `SabPublished` event schema + publish helper
- SAB markdown rendering (`render_brief()`, `render_list()`, `render_bluf()`) adapted from existing `digest.py` functions
- SAB HTML rendering (`build_html()` from `sab_html.py`) adapted to read from Postgres
- Semantic clustering via pgvector HNSW on the existing embedding index (per-CCIR, threshold configurable)
- LLM BLUF synthesis using the same prompt templates from `digest.py`
- Atomic file writes (`write .tmp + os.replace`) for both markdown and HTML output
- HTTP serving: `GET /sab` (SAB HTML), `GET /health` (200 OK), `GET /sab?window=24h` (custom window)
- `sab.published` event publish to RabbitMQ after SAB generation
- Docker Compose service definition for the brief container

**Out of scope:**
- Obsidian vault-writer — a separate plan item; this phase only writes to `data/digests/` (same as today)
- Email notification / push alerts — Phase 12 (CNR alerting / dissemination)
- FreshRSS/Fever API integration — fully retired; brief reads from Postgres only
- `cluster.md` and `list.md` as separate disk files — only `brief.md` and `bluf.md` are written to disk; `list.md` is available via the `?mode=list` query parameter on the HTML endpoint (no separate file)
- Entity resolution / wikilinks (`[[entity]]` notation) — Phase 8
- RAG recall / thematic search — Phase 9
- Wiki-LLM standing auto-wiki — Phase 10
- Container health checks, restart policies, DLQ management, structured logging — Phase 7 (ops)
- Retiring `digest.py` and `sab_html.py` from disk — Phase 7 (cutover)
- CNR real-time push notification lane — Phase 12

## Constraints

- **All LLM is local** (ADR-004): BLUF synthesis runs against `qwen36` via oMLX (`:8000/v1`) or DGX Spark vLLM (`192.168.10.2:8000/v1`). No cloud LLM.
- **One Postgres instance**: The brief service uses the same Postgres as all other services (`postgres:16` at `:22000`). No fan-out.
- **BLUF failure tolerance**: If the LLM endpoint is unreachable, the SAB still renders with a placeholder marker `_(BLUF unavailable — check log for details)_`. No item is dropped from the SAB because BLUF failed.
- **Enrichment integrity**: The brief service reads from `infotriage.enrichment` which was written by the triage worker. If an enrichment row is missing for an ingested item, that item is skipped (log warning, continue processing other items). The enrichment write in the worker happens *before* `verdict.ready` publish, so this race is theoretically impossible — but the brief service must not crash on it.
- **Atomic file writes**: All output files are written to `.tmp` then `os.replace()` to avoid partial reads by the HTTP server.
- **Clustering threshold**: Default pgvector cosine similarity threshold of 0.75 for cluster merging. Configurable via environment variable `CLUSTER_THRESHOLD` (range 0.0–1.0). Must be per-CCIR (items in different CCIR sections never merge).
- **Event ordering**: The brief service processes `verdict.ready` events in the order received (single consumer, `prefetch_count=1`). No reordering.
- **No paid services**: All dependencies must be free and self-hosted.

## Acceptance Criteria

- [ ] `apps/brief/` is a FastAPI service that subscribes `verdict.ready` via RabbitMQBus and processes items from Postgres
- [ ] `libs/contracts` defines `SabPublished` event with fields: `event_id` (UUID), `generated_at` (ISO 8601), `item_count` (int), `slide_count` (int)
- [ ] `render_brief()` produces markdown with CNR items first, then CCIR sections in CCIR_ORDER, with cluster metadata
- [ ] `render_list()` returns items with score ≥ 8, sorted by score descending
- [ ] `render_bluf()` generates LLM-synthesized summaries with bracketed numeric citations `[N]` per claim
- [ ] `GET /sab` returns HTTP 200 with valid HTML containing the latest SAB (served from atomically-written file)
- [ ] `GET /health` returns HTTP 200 OK regardless of bus/DB connectivity state
- [ ] `GET /sab?window=24h` generates a SAB for the specified time window and returns it
- [ ] Semantic clustering groups similar items within each CCIR section using pgvector HNSW (threshold configurable, default 0.75)
- [ ] Items in different CCIR sections are never merged into the same cluster
- [ ] SAB generation completes within 30 seconds of receiving `verdict.ready` (including LLM calls)
- [ ] `sab.published` event is published to RabbitMQ after each SAB generation with correct metadata
- [ ] All output files are written atomically (`.tmp` + `os.replace`)
- [ ] If the LLM endpoint is down, the SAB still renders (BLUF sections show placeholder, items not dropped)
- [ ] If an enrichment row is missing, the item is skipped with a warning (no crash)
- [ ] Docker Compose service definition exists for the brief container on port 22040

## Edge Coverage

**Coverage:** 8/8 applicable edges resolved · 0 unresolved

| Category | Requirement | Status | Resolution / Reason |
|----------|-------------|--------|---------------------|
| Empty input | R1, R2, R3, R4, R5 | ✅ covered | If 0 `verdict.ready` events in window, SAB renders with "No items in window" marker (Acceptance R6/R10) |
| CCIR-boundary merging | R4 | ✅ covered | Clustering is per-CCIR; items in different CCIR sections never merge (Constraint §Clustering threshold) |
| LLM failure | R2, R3 | ✅ covered | BLUF placeholder rendered, items not dropped (Constraint §BLUF failure tolerance) |
| Missing enrichment | R1 | ✅ covered | Item skipped with warning, no crash (Acceptance R13) |
| Stale data | R3 | ✅ covered | SAB only includes items from configured window, no stale items (Acceptance R11) |
| Event ordering | R1 | ✅ covered | Single consumer, prefetch=1, in-order processing (Constraint §Event ordering) |
| Partial cluster | R4 | ✅ covered | Items with no embedding match remain as single-item clusters (not dropped) |
| Concurrent writes | R2, R3 | ✅ covered | Atomic write pattern (.tmp + os.replace) prevents partial reads (Constraint §Atomic file writes) |

## Prohibitions (must-NOT)

**Coverage:** 3/3 applicable prohibitions resolved · 0 unresolved

| Prohibition (must-NOT statement) | Requirement | Status | Verification / Reason |
|----------------------------------|-------------|--------|------------------------|
| Brief service must NOT read from FreshRSS/Fever API | R1, R3 | resolved | verification: test — no `fever()` or `fever_key()` imports in `apps/brief/` |
| Brief service must NOT contain `sab_html.py`'s inline HTML template as a copy | R3 | resolved | verification: judgment — `sab_html.py` template must be imported, not duplicated; review for code reuse compliance |
| BLUF output must NOT contain uncited factual claims | R2 | resolved | verification: judgment — every claim in BLUF text must have a `[N]` citation; no automated test possible, requires human review |

## Ambiguity Report

| Dimension          | Score | Min  | Status | Notes                              |
|--------------------|-------|------|--------|------------------------------------|
| Goal Clarity       | 0.90  | 0.75 | ✓      | MVP core defined, all decisions logged |
| Boundary Clarity   | 0.87  | 0.70 | ✓      | Explicit in/out lists with reasoning |
| Constraint Clarity | 0.80  | 0.65 | ✓      | LLM failure, enrichment race, CCIR bounding |
| Acceptance Criteria| 0.82  | 0.70 | ✓      | 16 pass/fail criteria              |
| **Ambiguity**      | 0.15  | ≤0.20| ✓      |                                |

## Interview Log

| Round | Perspective    | Question summary                                   | Decision locked                                      |
|-------|----------------|---------------------------------------------------|------------------------------------------------------|
| 1     | Researcher     | Clustering strategy, serving method, sab.published | pgvector semantic clustering, FastAPI :22040, define schema now |
| 1     | Researcher     | What exists today?                                  | digest.py + sab_html.py (host cron, Fever API); worker.py (event-driven, complete) |
| 2     | Simplifier     | Minimum viable scope?                              | markdown + HTML output, pgvector clustering, LLM BLUF preserved, no Obsidian vault |
| 2     | Simplifier     | If cut 50%, what's irreducible?                     | Event consumer + SAB rendering + serving at :22040 |
| 3     | Boundary Keeper | What explicitly NOT done?                           | No Obsidian writer, no email/push, no FreshRSS, no entity resolution, no health checks |
| 3     | Boundary Keeper | What does done look like?                           | SAB served at :22040, sab.published on bus, atomic file writes |
| 4     | Failure Analyst | What causes verifier rejection?                    | SAB not served at :22040, enrichment missing, event not published, uncited BLUF claims |
| 4     | Failure Analyst | What goes wrong on edge cases?                     | LLM down → SAB still renders; 0 items → empty-state page; stale data → window filter |
| 5     | Seed Closer    | Tighten acceptance criteria                         | 16 pass/fail criteria defined covering all requirements |
| 5     | Seed Closer    | Any regret not specified?                          | Clustering threshold default (0.75), per-CCIR bounding, atomic writes — all covered |

---

*Phase: 06-brief-app*
*Spec created: 2026-07-04*
*Next step: /gsd-discuss-phase 6 — implementation decisions (FastAPI structure, container wiring, exact file layout, etc.)*
