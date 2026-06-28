# Phase 2: Storage — Postgres + blobs - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-28
**Phase:** 2-storage-postgres-blobs
**Areas discussed:** Store package location & deps, articles mapping + FTS scope, Connection config & pooling, Atom-projection writer (R7)

---

## Store package location & deps

| Option | Description | Selected |
|--------|-------------|----------|
| libs/store installable package, depends on contracts | Own pyproject.toml, editable install, imports contracts.Item; mirrors Phase-1 D-01 | ✓ |
| apps-local store module (not packaged) | Shared module under apps/; less ceremony, breaks libs/ convention | |
| libs/store, no hard dep on contracts | Packaged but duck-typed Item; loses static typing | |

**User's choice:** libs/store installable package, depends on contracts
**Notes:** Fills the gap the design doc's repo layout left (lists libs/contracts/ but no libs/store/). Blob store folded into the same package/interface (D-01a).

---

## articles mapping + FTS scope

| Option | Description | Selected |
|--------|-------------|----------|
| Hybrid columns + payload JSONB; defer FTS | Core fields as columns + Item.payload JSONB; FTS to search/RAG phase | ✓ |
| Hybrid + JSONB, add FTS now | Adds tsvector+GIN now (design doc 'JSONB+FTS'); scope beyond SPEC | |
| All-JSONB; defer FTS | id PK + JSONB only; weak indexing on source_type/ts/lang | |

**User's choice:** Hybrid columns + payload JSONB; defer FTS to the search/RAG phase
**Notes:** Keeps Phase 2 within SPEC scope; FTS belongs with the phase that queries it.

---

## Connection config & pooling

| Option | Description | Selected |
|--------|-------------|----------|
| Single DSN env; one connection per store context, no pool | INFOTRIAGE_PG_DSN from .env; context-managed connection | ✓ |
| Single DSN env + psycopg_pool | Pool now; extra dep + lifecycle Phase 2 doesn't need yet | |
| Discrete PG_* env vars; no pool | More config surface; diverges from DATABASE_URL convention | |

**User's choice:** Single DSN env var; one connection per store context (open/close), no pool
**Notes:** Pool deferred to P3+ behind the same Protocol when concurrent services arrive.

---

## Atom-projection writer (R7)

| Option | Description | Selected |
|--------|-------------|----------|
| Pull-on-demand, RSS/YouTube-only, reuse feedgen | Stateless read projection; email excluded per design doc; feedgen per NF-8 | ✓ |
| Pull-on-demand, RSS/YouTube-only, hand-rolled XML | Manual XML + _util.escape; reimplements feedgen | |
| Write-on-ingest hook | Store emits Atom as items land; couples store to projection | |

**User's choice:** Pull-on-demand, RSS/YouTube-only filter, reuse feedgen
**Notes:** Resolves the SPEC R7 flag (pull-on-demand). Email excluded ("Email is NOT projected to FreshRSS").

---

## Claude's Discretion

- DD-1: realize "InfoTriage schema" as a real `CREATE SCHEMA infotriage`.
- DD-2: ordered versioned `.sql` files under `libs/store/sql/`, idempotent `CREATE … IF NOT EXISTS`.
- DD-3: enrichment/ccir stubs as bare tables (id PK, item_id FK, created_at) + later-phase comment.
- DD-4: integration test via pytest marker + socket pre-check; fake/PG parity via shared contract test.
- DD-5: audit table records store write events (op, table, item id, ts).

## Deferred Ideas

- Full-text search (tsvector + GIN) — search/RAG phase.
- Connection pooling (psycopg_pool) — P3+.
- Async store / aio-pika alignment — P3.
- PostGIS (PMESII geo) — later geo/COP phase.
- Bus transport conflict (design doc Redis Streams vs ROADMAP/ADR-007 RabbitMQ) — Phase 3 to reconcile.
