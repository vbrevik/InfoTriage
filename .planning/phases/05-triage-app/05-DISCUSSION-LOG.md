# Phase 5: triage-app - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-29
**Phase:** 05-triage-app
**Areas discussed:** Worker module layout, Embedding store access, Shadow-run delivery

---

## Worker module layout

| Option | Description | Selected |
|--------|-------------|----------|
| New worker.py (entry point) | apps/triage/worker.py = container entry point; triage_score.py gets ccir hot-read fix only; standalone CLI preserved | ✓ |
| Adapt triage_score.py directly | Add consumer loop + /health endpoint directly into triage_score.py; simpler file count but mixes CLI and service logic | |

**User's choice:** New worker.py

---

| Option | Description | Selected |
|--------|-------------|----------|
| asyncio.gather() | asyncio.run(main()) with asyncio.gather(run_consumer(), run_health_server()); pure asyncio | ✓ |
| FastAPI lifespan hook | FastAPI app with @asynccontextmanager lifespan starting consumer as background task; same pattern as ingest adapters | |

**User's choice:** asyncio.gather()

---

| Option | Description | Selected |
|--------|-------------|----------|
| stdlib asyncio.start_server() | Zero new deps; raw TCP handler returns 200 OK on GET /health | ✓ |
| aiohttp | Slightly cleaner handler syntax but adds new dep | |
| You decide | Claude picks minimal viable approach | |

**User's choice:** stdlib asyncio.start_server()

---

## Embedding store access

| Option | Description | Selected |
|--------|-------------|----------|
| Extend Store Protocol | Add put_embedding + find_near_duplicate to Store Protocol + PostgresStore + InMemoryStore; consistent with D-01 single-mediating-interface | ✓ |
| Direct psycopg in worker.py | Worker opens own cursor for embeddings table; avoids Protocol extension but two DB connections + logic scatter | |

**User's choice:** Extend Store Protocol

---

| Option | Description | Selected |
|--------|-------------|----------|
| bool | find_near_duplicate returns True/False — simple, matches SPEC dedup semantics | |
| Optional[str] — matched item_id | Returns None or item_id of nearest match; enables logging which article triggered dedup | ✓ |

**User's choice:** Optional[str] — matched item_id
**Notes:** Useful for debugging false-positive dedup cases.

---

## Shadow-run delivery

| Option | Description | Selected |
|--------|-------------|----------|
| Script: scripts/shadow_run.py | Queries Postgres enrichment rows, re-runs score_item() standalone, prints side-by-side bucket comparison table | ✓ |
| Manual procedure only | No script; operator compares buckets manually; documented checklist only | |

**User's choice:** Script

---

| Option | Description | Selected |
|--------|-------------|----------|
| infotriage.enrichment table (new scorer's output) | Compares event-driven enrichment bucket vs. standalone re-run; single source of truth | ✓ |
| fever_triage.py live re-run | Calls fever_triage.py against live FreshRSS; requires articles still unread | |

**User's choice:** infotriage.enrichment table (new event-driven scorer's output as baseline)

---

## Claude's Discretion

- Migration delivery: `006-enrichment.sql` with `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` pattern (follows 001–005 convention; extends stub table rather than drop+recreate)
- cnr/bucket field mappings: `"none"` → `"Routine"` for cnr; `"read"` → `"keep"` for bucket (locked by VerdictReady Pydantic types)
- oMLX embedding call: inline `get_embedding()` in worker.py using urllib.request (mirrors llm() pattern from triage_score.py; zero new deps)
- pgvector cosine query: `ORDER BY embedding <=> %s::vector LIMIT 1` with distance filter `< 1 - threshold`

## Deferred Ideas

None — discussion stayed within phase scope.
