# Phase 5: triage-app - Context

**Gathered:** 2026-06-29
**Status:** Ready for planning

<domain>
## Phase Boundary

Event-driven `triage` container that subscribes `item.ingested` from RabbitMQ, computes mE5-large embeddings for semantic dedup, scores each non-duplicate article against `ccir.md` using qwen36, writes enrichment rows to Postgres, and publishes `verdict.ready`. Retires the FreshRSS Fever poll path (`fever_triage.py`).

</domain>

<spec_lock>
## Requirements (locked via SPEC.md)

**7 requirements are locked.** See `05-SPEC.md` for full requirements, boundaries, and acceptance criteria.

Downstream agents MUST read `05-SPEC.md` before planning or implementing. Requirements are not duplicated here.

**In scope (from SPEC.md):**
- `infotriage.enrichment` schema migration (7 new columns)
- Store protocol: `put_enrichment` / `get_enrichment`
- `triage` Docker container (port 22030, GET /health)
- RabbitMQ `item.ingested` consumer
- LLM scoring (qwen36, ccir.md, PMESII/TESSOC enrichment)
- mE5-large embedding dedup (oMLX, 7-day window, cosine ≥ 0.84)
- `infotriage.embeddings` writes (production path)
- `verdict.ready` publication
- Shadow-run parity check + `fever_triage.py` retirement from production

**Out of scope (from SPEC.md):**
- SAB/digest generation — Phase 6
- CNR alerting / push notifications — Phase 12
- Entity resolution — Phase 8
- CCIR pre-filter cosine similarity (A-1) — Phase 9
- RAG recall — Phase 9
- `infotriage.ccir` table — not used in Phase 5
- Admiralty reliability scoring (A-4) — post-M1 backlog
- FreshRSS subscription management — remains as-is
- Multiple concurrent triage worker scaling — single worker for M1

</spec_lock>

<decisions>
## Implementation Decisions

### Worker module structure

- **D-01:** New `apps/triage/worker.py` is the container entry point. The aio-pika consumer loop and the `/health` HTTP server both live here. `triage_score.py` is preserved as a pure scoring helper (standalone `--sample` CLI keeps working).
- **D-02:** `triage_score.py` gets one targeted fix: `score_item()` calls `load_ccir()` internally on each call instead of using the module-level `CCIR` cache. The module-level `CCIR = load_ccir()` line is removed. This satisfies D-5 (hot edits take effect on next scoring run) without breaking the CLI.
- **D-03:** `worker.py` uses `asyncio.gather(run_consumer(), run_health_server())` inside `asyncio.run(main())`. Pure asyncio — no extra framework beyond what's already present.
- **D-04:** `/health` HTTP server implemented with Python stdlib `asyncio.start_server()`. Zero new deps. Returns `200 OK` on `GET /health`. Liveness only — bus disconnect does NOT cause health to return 5xx (handled by `connect_robust` reconnect).

### Embedding store access

- **D-05:** Embedding operations go through the **Store Protocol** (extends D-01 single-mediating-interface principle). Two new methods added to `Store` Protocol + `PostgresStore` + `InMemoryStore`:
  - `put_embedding(item_id: str, vector: list[float]) -> None` — writes to `infotriage.embeddings`; ON CONFLICT DO UPDATE (upsert, same idempotency pattern as `put_enrichment`)
  - `find_near_duplicate(vector: list[float], window_days: int = 7, threshold: float = 0.84) -> Optional[str]` — returns `item_id` of nearest match within cosine distance or `None` if no duplicate found
- **D-06:** `find_near_duplicate` returns `Optional[str]` (the matched `item_id`) rather than `bool`. Worker logs which article triggered the dedup skip — useful for debugging false-positive dedup. SQL: `ORDER BY vector <=> %s LIMIT 1` with `WHERE created_at >= NOW() - INTERVAL '%s days'` and distance filter.
- **D-07:** `InMemoryStore` implements `find_near_duplicate` with a Python cosine similarity loop over stored `(item_id, vector)` tuples. Tests work without a real pgvector instance.

### Shadow-run delivery

- **D-08:** Phase 5 includes `scripts/shadow_run.py`. After the new triage worker has processed ≥10 articles (enrichment rows written), the script queries `infotriage.articles` + `infotriage.enrichment` and re-runs `score_item()` standalone on each article's title/summary, then prints a side-by-side table comparing the enrichment-stored bucket vs. the standalone re-run bucket.
- **D-09:** "Old bucket" source = `infotriage.enrichment.bucket` (the new event-driven scorer's output). The comparison is: does re-running `triage_score.py` standalone produce the same bucket as the event-driven worker? Parity = matching bucket on ≥10 articles. Operator confirms parity, then removes fever_triage.py from production (scheduler has no fever entries; new triage container has no fever invocation).

### Migration delivery

- **D-10:** Enrichment schema migration delivered as `libs/store/sql/006-enrichment.sql` with `ALTER TABLE infotriage.enrichment ADD COLUMN IF NOT EXISTS ...` for all 7 columns. Runs via `init_schema()` idempotently. The existing stub table (from `005-stubs.sql`) is preserved and extended — not dropped/recreated.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & boundaries
- `.planning/phases/05-triage-app/05-SPEC.md` — Locked requirements (R1–R7), constraints, acceptance criteria, prohibitions, edge coverage. MUST read before planning.

### Architecture decisions
- `docs/ARCHITECTURE.md` — ADR-004 (no cloud LLM; all LLM calls use local qwen36 only via LLM_BASE_URL), ADR-006 (mE5-large threshold 0.84; HNSW cosine index), ADR-007 (RabbitMQ topology; aio-pika connect_robust)
- `.planning/ROADMAP.md` §Phase 5 — Goal, depends-on, success criteria

### Phase dependencies (read interfaces, not full docs)
- `.planning/phases/03-bus-rabbitmq/03-CONTEXT.md` — aio-pika BusClient, connect_robust(), publisher confirms, DLX topology
- `.planning/phases/02-storage-postgres-blobs/02-CONTEXT.md` — Store Protocol decisions, psycopg3 patterns (pgvector pitfalls, JSONB, autocommit for DDL)

### Existing scorer (to port, not rewrite)
- `apps/triage/triage_score.py` — Proven scoring function `score_item(it: dict) -> dict`. Returns `ccir/cnr/pmesii/tessoc/score/why/bucket`. Gets one fix: `load_ccir()` moved inside `score_item()` (hot-read).
- `apps/triage/fever_triage.py` — Being retired from production. Do not adapt; preserve file but remove from scheduler/docker invocation.

### Store Protocol (to extend)
- `libs/store/src/store/_protocol.py` — Add `put_embedding` and `find_near_duplicate` here
- `libs/store/src/store/_postgres.py` — PostgresStore implementation; follow existing psycopg3 + pgvector patterns (Pitfall 1: register_vector; Pitfall 4: autocommit for DDL; bind params only)
- `libs/store/src/store/_inmemory.py` — InMemoryStore: add cosine similarity loop for `find_near_duplicate`
- `libs/store/sql/005-stubs.sql` — Current enrichment table schema (bare stub: id, item_id, created_at)

### Contracts (bus events)
- `libs/contracts/src/contracts/_events.py` — `ItemIngested` (consumed) and `VerdictReady` (published); note VerdictReady.cnr is `Literal["I", "II", "Routine"]` and VerdictReady.bucket is `Literal["keep", "maybe", "skip"]`
- `libs/contracts/src/contracts/_bus_rabbitmq.py` — RabbitMQBus; call `await bus.subscribe("item.ingested", handler)` with prefetch_count=1

### Infrastructure reference
- `docker-compose.yml` — Existing services, port band (22010–22014 adapters), network `infotriage`; triage container goes on 22030

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `apps/triage/triage_score.py` `score_item(it: dict)` — Proven scorer, returns all 7 enrichment fields. Accepts `dict` with `title`, `source`, `summary`. Direct import in `worker.py`.
- `apps/triage/triage_score.py` `llm(messages, max_tokens)` — LLM call via urllib.request; reads `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` env vars. Same env pattern for oMLX embedding call in worker.
- `libs/contracts._bus_rabbitmq.RabbitMQBus` — Phase 3 BusClient; `connect_robust()` + topic exchange `infotriage.events`. Worker calls `await bus.consume("item.ingested", handler, prefetch_count=1)`.
- `libs/store._postgres.PostgresStore` — Phase 2 store; `with PostgresStore(dsn, blob_root) as store:` pattern. Worker uses the same context manager; adds `put_enrichment`, `get_enrichment`, `put_embedding`, `find_near_duplicate`.

### Established Patterns
- `python:3.12-slim` + `COPY libs/contracts /build/contracts; COPY libs/store /build/store; RUN pip install --no-deps /build/contracts /build/store` Dockerfile pattern (Phase 4 D-10/D-11)
- All SQL uses `%s` bind params — never f-strings or string concatenation (V5/T-02-01)
- `psycopg.types.json.Jsonb()` wrapper for JSONB columns; `register_vector()` before any vector query (Pitfall 1)
- Autocommit connection for DDL (Pitfall 4) — init_schema() opens a separate autocommit conn
- Credentials via `.env` + `env_file:` in docker-compose (Phase 4 D-07)
- Port 22030 for triage container (SPEC R7); bound to `127.0.0.1:22030`
- `restart: unless-stopped` on long-running containers

### cnr / bucket field mapping (SPEC-locked)
- `triage_score.py` returns `cnr: "I" | "II" | "none"` and `bucket: "read" | "maybe" | "skip"`
- `VerdictReady.cnr` is `Literal["I", "II", "Routine"]` — map `"none"` → `"Routine"`
- `VerdictReady.bucket` is `Literal["keep", "maybe", "skip"]` — map `"read"` → `"keep"`
- Worker performs these mappings before constructing VerdictReady

### Integration Points
- `infotriage.enrichment` — Add 7 columns via `006-enrichment.sql`; `put_enrichment(item_id, fields)` upsert via ON CONFLICT DO UPDATE
- `infotriage.embeddings` — Existing HNSW cosine index (`vector(1024)`, `vector_cosine_ops`); Phase 5 writes production vectors into it; do NOT drop or recreate the index
- RabbitMQ queue `q.triage` — bound to `item.ingested` routing key (Phase 3 topology); triage worker subscribes to this queue
- RabbitMQ publish `verdict.ready` → `q.brief` — publish AFTER `store.put_enrichment()` returns (must-NOT: no event before enrichment commit)

</code_context>

<specifics>
## Specific Ideas

- **shadow_run.py output format**: Side-by-side table — columns: `item_id (short)`, `title (truncated)`, `enrichment_bucket`, `rescore_bucket`, `match`. Rows where `match=False` highlighted. Operator reviews, confirms ≥10 items with match=True, then proceeds with fever retirement.
- **ccir.md hot-read fix**: Remove `CCIR = load_ccir()` at module level in `triage_score.py`. Add `ccir = load_ccir()` as the first line inside `score_item()`. No interface change — `score_item(it)` signature unchanged.
- **oMLX embedding call**: Mirror `llm()` pattern in `triage_score.py` — a `get_embedding(text: str) -> list[float]` function in `worker.py` using `urllib.request` to call `{LLM_BASE_URL}/embeddings` with `model=intfloat/multilingual-e5-large`, input = `title + " " + summary[:512]`. No new dep for the HTTP call.
- **pgvector cosine query**: `SELECT item_id FROM infotriage.embeddings WHERE created_at >= NOW() - INTERVAL %s ORDER BY embedding <=> %s::vector LIMIT 1` with `%s` = `f'{window_days} days'` and `%s` = `str(vector)`. Filter by distance: if `embedding <=> query_vector < 1 - threshold` (cosine distance ≤ 1-0.84 = 0.16), return `item_id`; else return `None`.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 05-triage-app*
*Context gathered: 2026-06-29*
