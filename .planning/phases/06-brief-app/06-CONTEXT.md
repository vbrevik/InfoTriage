# Phase 6: Brief app - Context

**Gathered:** 2026-07-04
**Status:** Ready for planning

<domain>
## Phase Boundary

Event-driven `brief` container (`:22040`) that subscribes `verdict.ready` from the RabbitMQ bus, aggregates scored items from `infotriage.enrichment` in Postgres, clusters them via pgvector HNSW, renders a Situational Awareness Brief in markdown + HTML with LLM-generated BLUF sections, serves the SAB at `:22040`, and publishes `sab.published` to the bus. Replaces the host crontab path (`digest.py` + `sab_html.py` reading from FreshRSS/Fever API).

</domain>

<spec_lock>
## Requirements (locked via SPEC.md)

**5 requirements are locked.** See `06-SPEC.md` for full requirements, boundaries, and acceptance criteria.

Downstream agents MUST read `06-SPEC.md` before planning or implementing. Requirements are not duplicated here.

**In scope (from SPEC.md):**
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

**Out of scope (from SPEC.md):**
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

</spec_lock>

<decisions>
## Implementation Decisions

### Serving approach

- **D-01:** Render SAB on `GET /sab` request OR if the previous render file is ≥24h old. Check last-modified timestamp on `data/digests/sab.html`; if older than 24h, regenerate. If <24h, serve cached version via `FileResponse` with `max_age=86400`. No background scheduler needed — rendering is purely request-driven.
- **D-02:** FastAPI serves SAB HTML via `FileResponse` (same pattern as ingest adapters). The `data/digests/` directory is served directly — no static file server container needed. Docker volume mount: `./data/digests:/app/data/digests`.

### Output file strategy

- **D-03:** All four files written to `data/digests/`: `cluster.md`, `brief.md`, `list.md`, `bluf.md`. Same file set as today's `digest.py`. The SAB HTML (`sab.html`) is the fifth file, served by the HTTP endpoint.
- **D-04:** Each SAB render regenerates all four markdown files and the HTML file atomically (`.tmp` + `os.replace`). The rendering pipeline is: fetch enrichment items → cluster → render_brief → render_bluf → render_list → write all files.

### BLUF synthesis strategy

- **D-05:** BLUF generated only for CCIR/CNR sections that have new items since the last SAB render. Previous BLUFs are preserved from the prior render. No full-regen of all sections required.
- **D-06:** The brief service tracks a "last render timestamp" in a simple JSON file `data/digests/_last_render.json` with fields `generated_at` (ISO 8601) and `item_count`. When `verdict.ready` arrives:
  1. Check if new items exist since `last_render.json.generated_at`
  2. If yes: regenerate BLUF only for CCIR sections with new items, preserve existing BLUFs for sections without changes
  3. If no: skip regeneration, serve cached SAB (subject to 24h staleness gate)
- **D-07:** BLUF prompt templates are reused from `digest.py` `write_bluf()` / `sab_html.py` `generate_bluf()` — same frame template, same citation rules (`[N]` per claim), same contradiction handling. No new templates.

### Window selection

- **D-08:** Time window rendered incrementally. Each `verdict.ready` updates a "last update" timestamp (`data/digests/_last_update.json`). The SAB includes all enrichment items since this timestamp.
- **D-09:** On first SAB render after container start (no `_last_update.json` exists), fall back to "since yesterday 16:00 Oslo" — same default as today's `digest.py` `default_cutoff()`. This ensures the first SAB after restart is comprehensive, not empty.
- **D-10:** The `GET /sab?window=24h` endpoint is supported as a manual override — generates a SAB for the specified window and serves it without updating the incremental timestamp. Used for ad-hoc re-renders.

### Module structure

- **D-11:** `apps/brief/` follows the same FastAPI structure as ingest adapters (Phase 4 pattern):
  - `apps/brief/main.py` — FastAPI app factory, route definitions
  - `apps/brief/consumer.py` — `RabbitMQBus.consume("verdict.ready", handler)`
  - `apps/brief/renderer.py` — `render_brief()`, `render_list()`, `render_bluf()` (adapted from `digest.py`)
  - `apps/brief/html_renderer.py` — `build_html()` (adapted from `sab_html.py`, imports HTML template)
  - `apps/brief/clustering.py` — pgvector HNSW clustering per-CCIR
  - `apps/brief/window.py` — incremental window management (`_last_update.json`), time window defaults
- **D-12:** `sab_html.py` HTML template is **imported, not copied** (SPEC prohibition). `apps/brief/html_renderer.py` imports the `HTML_TEMPLATE` constant from `sab_html.py` via `from apps.triage.sab_html import HTML_TEMPLATE`. No duplication.

### Docker packaging

- **D-13:** Same `python:3.12-slim` + `COPY + pip install` pattern as Phase 4/D-10. Base image: `python:3.12-slim`.
  ```dockerfile
  COPY libs/contracts /build/contracts
  COPY libs/store /build/store
  RUN pip install --no-deps /build/contracts /build/store
  ```
- **D-14:** Port band: `127.0.0.1:22040` (following 22010-22030 band convention). Bound to `127.0.0.1` only (not `0.0.0.0`).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & boundaries
- `.planning/phases/06-brief-app/06-SPEC.md` — Locked requirements (R1–R5), constraints, acceptance criteria, prohibitions, edge coverage. MUST read before planning.

### Architecture decisions
- `docs/ARCHITECTURE.md` — ADR-004 (no cloud LLM; all LLM calls use local qwen36), ADR-006 (pgvector HNSW cosine index, mE5-large threshold 0.84), ADR-007 (RabbitMQ topology; aio-pika connect_robust)
- `.planning/ROADMAP.md` §Phase 6 — Goal, depends-on (Phase 5), success criteria

### Phase dependencies (read interfaces, not full docs)
- `.planning/phases/05-triage-app/05-CONTEXT.md` — `worker.py` publishes `verdict.ready`, enrichment schema (006-enrichment.sql), Store Protocol `put_enrichment`/`get_enrichment`, `infotriage.embeddings` table with HNSW index, port 22030 convention
- `.planning/phases/04-ingest-adapters-gmail-mcp/04-CONTEXT.md` — FastAPI trigger pattern, Dockerfile COPY+pip install pattern, port band 22010-22030, env_file docker-compose convention
- `.planning/phases/03-bus-rabbitmq/03-CONTEXT.md` — aio-pika BusClient, connect_robust(), publisher confirms, DLX topology, exchange `infotriage.events`, routing key `verdict.ready` → queue `q.brief`

### Existing code (to adapt, not rewrite)
- `apps/triage/digest.py` — `write_brief()`, `write_cluster()`, `write_list()`, `write_bluf()`, `CCIR_ORDER`, `kept()`, `cluster()` (keyword-overlap), `line()`, `_est_tokens()`. Markdown renderers adapt these to read from Postgres.
- `apps/triage/sab_html.py` — `build_html()`, `HTML_TEMPLATE` (1064-line inline CSS/JS/HTML). HTML renderer imports the template.
- `apps/triage/triage_score.py` — `score_item()`, `llm()`, `load_dotenv()`. LLM call pattern for embedding and BLUF synthesis.
- `apps/triage/worker.py` — `process_item()`, `RabbitMQBus` consume pattern, `asyncio.gather()` consumer+health pattern, stdlib `/health` server.
- `libs/contracts/src/contracts/_events.py` — Add `SabPublished` event schema here. Existing events: `ItemIngested`, `VerdictReady`.
- `libs/store/src/store/_postgres.py` — `PostgresStore` pattern for querying enrichment data.

### Infrastructure reference
- `docker-compose.yml` — Existing services, port band (22010–22030), network `infotriage`; brief container goes on 22040

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `apps/triage/digest.py` `write_brief()`, `write_list()`, `write_bluf()` — Proven renderers. `CCIR_ORDER` constant (11 CCIR entries with display titles) is shared between digest.py and sab_html.py — must remain in sync.
- `apps/triage/sab_html.py` `HTML_TEMPLATE` — 1064-line inline HTML template with CSS, JS, scroll-presentation mode toggle. Imported, not copied.
- `apps/triage/sab_html.py` `generate_bluf(cid, title, items, top_n)` — LLM prompt template for BLUF synthesis, with citation rules and contradiction handling. Reused in event-driven path.
- `libs/contracts._bus_rabbitmq.RabbitMQBus` — aio-pika BusClient; consumer uses `await bus.consume("verdict.ready", handler, prefetch_count=1)`.
- `libs/store._postgres.PostgresStore` — `get_enrichment(item_id)` returns enrichment row; `find_near_duplicate()` for pgvector semantic clustering.
- `apps/triage/worker.py` `run_health_server()` — stdlib `asyncio.start_server()` liveness-only `/health`. Same pattern for brief's `/health`.

### Established Patterns
- `python:3.12-slim` + `COPY libs/contracts /build/contracts; COPY libs/store /build/store; RUN pip install --no-deps /build/contracts /build/store` Dockerfile pattern (Phase 4).
- All SQL uses `%s` bind params — never f-strings (V5/T-02-01).
- `psycopg.types.json.Jsonb()` wrapper for JSONB columns; `register_vector()` before vector queries (Pitfall 1).
- Autocommit connection for DDL (Pitfall 4) — `init_schema()` opens separate autocommit conn.
- Port band 22000+: postgres=22000, rabbitmq=22001/22002, adapter triggers=22010-22014, triage=22030, brief=22040. All bound to `127.0.0.1`.
- `restart: unless-stopped` on long-running containers.
- Credentials via `.env` + `env_file:` in docker-compose.
- Atomic writes: `write .tmp + os.replace()` (digest.py lines 393-396, sab_html.py lines 1198-1201).

### cnr / bucket field mapping (SPEC-locked, inherited from Phase 5)
- `triage_score.py` returns `cnr: "I" | "II" | "none"` and `bucket: "read" | "maybe" | "skip"`
- `VerdictReady.cnr` is `Literal["I", "II", "Routine"]` — map `"none"` → `"Routine"`
- `VerdictReady.bucket` is `Literal["keep", "maybe", "skip"]` — map `"read"` → `"keep"`
- Enrichment rows store RAW vocabulary (cnr none|I|II, bucket read|maybe|skip)

### Integration Points
- `infotriage.enrichment` — Read enrichment rows for SAB rendering. Query: `SELECT item_id, ccir, cnr, score, bucket, why, pmesii, tessoc FROM infotriage.enrichment WHERE created_at >= :since ORDER BY created_at DESC`.
- `infotriage.embeddings` — HNSW cosine index for pgvector semantic clustering. Reused from Phase 5.
- RabbitMQ queue `q.brief` — bound to `verdict.ready` routing key. Brief service subscribes here.
- `data/digests/` — Output directory for `brief.md`, `cluster.md`, `list.md`, `bluf.md`, `sab.html`. Docker volume mount.
- `_last_update.json` — New file tracking incremental window state (D-08).
- `_last_render.json` — New file tracking last render metadata (D-06).

</code_context>

<specifics>
## Specific Ideas

- **Incremental BLUF**: Instead of regenerating all 11 CCIR BLUFs on each `verdict.ready`, track which CCIR sections have new items since `_last_update.json`. Only call LLM for those sections. Preserve existing BLUFs for unchanged sections. This reduces BLUF cost from ~33s (all sections) to ~3-15s (1-5 affected sections).
- **Window default**: On first run (no `_last_update.json`), use `digest.py:default_cutoff()` — yesterday 16:00 Oslo — same as today's `digest.py` default. This ensures the first SAB after restart is comprehensive.
- **Staleness gate**: `GET /sab` checks `os.path.getmtime("data/digests/sab.html")` against `now() - timedelta(hours=24)`. If stale, regenerate; if fresh, serve cached. This is a simple file-mtime check — no database query.
- **BLUF citation enforcement**: The `write_bluf()` prompt already includes "Cite every claim with bracketed numeric refs" and "A claim with no citation is wrong." This prompt is reused verbatim in the event-driven path (D-07).

</specifics>

<deferred>
## Deferred Ideas

- Obsidian vault-writer (SAB + Obsidian projection) — belongs in a separate phase (noted in SPEC.md out of scope)
- CNR real-time push notification lane — Phase 12 (CNR alerting / dissemination)
- `ingest-web` (direct HTTP scraper) — Phase 4 already deferred this; remains deferred

</deferred>

---

*Phase: 06-brief-app*
*Context gathered: 2026-07-04*
