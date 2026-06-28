# Phase 2: Storage — Postgres + blobs — Specification

**Created:** 2026-06-28
**Ambiguity score:** 0.15 (gate: ≤ 0.20)
**Requirements:** 8 locked

## Goal

Postgres becomes the single canonical store: a `postgres:16` + `pgvector/pgvector:pg16` instance on `:22000` holds the `InfoTriage` schema, an on-disk content-addressed blob store holds large bodies, and a single synchronous `store` interface mediates all reads/writes — with no change to pipeline behavior.

## Background

No storage layer exists today. Persistence is ad-hoc: ingest bridges write Atom XML to `data/feeds/*.xml`, `digest.py` appends score history to `data/verdicts.jsonl` (PR-4), and nothing uses a database. The Phase 1 `contracts` package defines the canonical `Item` (sha256 `id`, aware-datetime `ts`, JSONB `payload`, `body_ref`) and a `BusClient` Protocol + `InMemoryBus` pattern — Phase 2 mirrors that pattern for storage. The Phase 0 spike (R3 / ADR-006) validated the pgvector entity schema: `entities`/`entity_links` + `embeddings vector(1024)`, HNSW `vector_cosine_ops`, link threshold 0.85 (Trump/Putin ~0.72 stay split; NATO variants ~0.92 merge). ADR-001 rejects SQLite (concurrent writers). This phase builds the schema, the blob store, the `store` interface, and the FreshRSS Atom-projection writer, and retrofits existing scripts onto the store.

## Requirements

1. **Canonical Postgres + idempotent schema bootstrap**: `store.init_schema()` applies plain-SQL DDL idempotently against Postgres 16 + pgvector on `:22000`, creating the `InfoTriage` schema and the `vector` extension.
   - Current: No database, no schema, no bootstrap; persistence is files only
   - Target: `store.init_schema()` runs `CREATE EXTENSION IF NOT EXISTS vector` + `CREATE TABLE IF NOT EXISTS …` from versioned `.sql`; no migration framework (stdlib-first, NF-8)
   - Acceptance: On a fresh DB, `init_schema()` creates all objects; a second call is a no-op (no error, identical schema)

2. **All seven tables exist**: `articles`, `audit`, `embeddings`, `entities`, `entity_links` are fully defined; `enrichment` and `ccir` are forward-declared minimal stubs whose columns are owned by later phases.
   - Current: No tables exist
   - Target: All 7 tables present after `init_schema()`; `articles` maps to `contracts.Item` (id, source, source_type, url, title, ts, lang, summary, body_ref, payload JSONB)
   - Acceptance: Query `information_schema.tables` for the `InfoTriage` schema returns all 7 names; `articles` columns round-trip a `contracts.Item`

3. **pgvector entity/embedding schema**: `embeddings`/`entities` use `vector(1024)` with an HNSW `vector_cosine_ops` index; entity linking merges at cosine similarity **≥ 0.85 (inclusive)**.
   - Current: No vector columns or index
   - Target: `entities(id, name, name_norm, lang, type, embedding vector(1024))` + `entity_links(entity_id FK, item_id, mention, lang)`; HNSW index with `vector_cosine_ops`; `LINK_THRESHOLD = 0.85`
   - Acceptance: A cosine `<=>` query returns nearest neighbors; similarity ≥ 0.85 links to same `entity_id`, < 0.85 stays distinct (spike control: Trump ≠ Putin)

4. **Content-addressed blob store**: keys objects by `sha256` of their bytes under `data/blobs/ab/cd/<hash>` (prefix-sharded), write-once with dedup, atomic writes.
   - Current: Raw bodies/PDFs/transcripts are not stored; only feed XML on disk
   - Target: `put_blob(bytes) -> hash` / `get_blob(hash) -> bytes`; path = `data/blobs/<h[:2]>/<h[2:4]>/<h>`; holds MIME/PDF/transcripts/raw HTML; write via temp-file + `os.replace` (atomic); re-putting an existing hash is a no-op
   - Acceptance: `put_blob(b)` then `get_blob(hash) == b`; putting the same bytes twice yields one file, no error; partial-write failure leaves no file at the final path

5. **Single synchronous `store` interface**: a Protocol with a psycopg3 Postgres implementation and an in-memory fake, mediating all reads/writes and persisting/loading `contracts.Item`.
   - Current: No store abstraction; each script persists its own way
   - Target: `Store` Protocol (`@runtime_checkable`) + `PostgresStore` (psycopg3, sync) + `InMemoryStore` fake; `put_item` is an **idempotent upsert** on `Item.id` (`ON CONFLICT DO UPDATE`, last-write-wins); `get_item(id)` returns `None` on miss; list queries return `[]` on no match, ordered by `(ts, id)`
   - Acceptance: `InMemoryStore` and `PostgresStore` both satisfy the Protocol; two `put_item` of the same id → one row with latest content; `get_item("absent")` → `None`

6. **Existing scripts retrofitted (no backfill)**: ingest/triage/digest read and write through the store going forward, with no migration of historical data.
   - Current: Scripts write `data/verdicts.jsonl` and feed XML directly
   - Target: Affected scripts route persistence through `store`; no backfill of prior `verdicts.jsonl` / feed state (fresh-forward)
   - Acceptance: After retrofit, running a script persists via the store (rows appear in Postgres / fake); old `data/verdicts.jsonl` is neither read nor migrated; 87-test suite still green

7. **FreshRSS Atom-projection writer**: a writer behind the store interface renders stored articles to Atom XML on demand for FreshRSS.
   - Current: Atom XML is produced directly by the ingest bridges, not from a store
   - Target: A pull-on-demand projection reads articles from the store and renders Atom XML for FreshRSS *(default: pull-on-demand vs write-on-ingest is flagged for discuss-phase to confirm)*
   - Acceptance: Given known articles in the store, the writer emits valid Atom XML containing those entries; output is deterministic for the same store state

8. **Testing + provisioning**: unit tests run against the in-memory fake; one live integration test runs real DDL + a pgvector cosine round-trip against `:22000`, auto-skipping when the DB is unreachable; `docker-compose` ships `postgres:16` + `pgvector/pgvector:pg16`.
   - Current: No storage tests, no DB service definition
   - Target: Fast unit tests on `InMemoryStore`; a marked integration test (init_schema + put/get round-trip + `<=>` cosine query) against `:22000`, skipped if connection fails within a short timeout; `docker-compose.yml` defines the pgvector service on `:22000`
   - Acceptance: `pytest` passes with no DB running (integration test skipped); with the container up, the integration test runs and passes; `docker compose up` exposes Postgres on `:22000`

## Boundaries

**In scope:**
- Postgres 16 + pgvector `:22000` service (`docker-compose`) + idempotent plain-SQL schema bootstrap
- All 7 tables (5 full, 2 stubbed); pgvector `vector(1024)` + HNSW cosine index
- Content-addressed, sharded, write-once blob store
- Sync `store` Protocol + `PostgresStore` (psycopg3) + `InMemoryStore` fake
- Retrofitting existing ingest/triage/digest scripts onto the store
- FreshRSS Atom-projection writer behind the store
- In-memory-fake unit tests + one live integration test

**Out of scope:**
- Column definitions / logic for `enrichment` and `ccir` — owned by the scoring phase (≈ P4)
- Entity-resolution NER + linking *logic* — only the schema lands here; linking is Phase 8
- Historical data backfill (`verdicts.jsonl`, feed state) — fresh-forward only, deliberate
- Async store / aio-pika integration — Phase 3 may add an async impl behind the same Protocol
- App-level concurrency control (advisory locks) — rely on Postgres transactions; not needed at current single-process scale
- Embedding *generation* (mE5-large inference) — Phase 5/8; Phase 2 only stores/queries vectors

## Constraints

- Postgres only; SQLite rejected (ADR-001 — concurrent writers; NF-3 one query surface)
- Sync interface (psycopg3); current scripts are synchronous
- Stdlib-first (NF-8): plain-SQL DDL, no migration framework, no ORM
- `vector(1024)` to match mE5-large dim; HNSW `vector_cosine_ops`; `LINK_THRESHOLD = 0.85` (R3/ADR-006)
- Blob hash = `sha256` of content (distinct from `Item.id`); flat-sharded `ab/cd/<hash>`
- Service port `:22000` (distinct from the spike's ephemeral `:22062`)
- `.env`-external secrets, never committed (NF-6)

## Acceptance Criteria

- [ ] `store.init_schema()` creates the `InfoTriage` schema + `vector` extension on a fresh DB; a second run is a no-op
- [ ] All 7 tables (`articles`, `enrichment`, `ccir`, `embeddings`, `entities`, `entity_links`, `audit`) exist after init
- [ ] `articles` round-trips a `contracts.Item` (all core + summary + body_ref + payload JSONB)
- [ ] `embeddings`/`entities` use `vector(1024)` + HNSW `vector_cosine_ops`; a `<=>` query links at sim ≥ 0.85, separates at < 0.85
- [ ] `put_blob(b)` → `get_blob(hash) == b`; duplicate put is a single-file no-op; failed write leaves no final-path file; path is `data/blobs/ab/cd/<hash>`
- [ ] `InMemoryStore` and `PostgresStore` both satisfy the `Store` Protocol
- [ ] `put_item` upserts on `Item.id` (one row, latest content); `get_item` miss → `None`; empty query → `[]`
- [ ] Existing scripts persist through the store; no read/migrate of `data/verdicts.jsonl`
- [ ] Atom-projection writer emits valid Atom XML for known stored articles
- [ ] `pytest` passes with no DB (integration skipped) and with the container up (integration runs + passes)
- [ ] `docker compose up` exposes `postgres:16`+pgvector on `:22000`
- [ ] (must-NOT) A failed persist raises — the store never silently drops/truncates a write (dedup no-op excepted)
- [ ] (must-NOT) `InMemoryStore` does not diverge from `PostgresStore`'s observable contract — a shared contract test runs against both

## Edge Coverage

**Coverage:** 20/20 applicable edges resolved · 0 unresolved

| Category | Requirement | Status | Resolution / Reason |
|----------|-------------|--------|---------------------|
| idempotency | R1 | ✅ covered | `init_schema()` second run is a no-op (AC) |
| concurrency | R1 | ✅ covered | Bootstrap is single-writer at deploy; `IF NOT EXISTS` makes accidental double-run safe |
| adjacency | R2 | ⛔ dismissed | R2 is table-existence; no merge/collision semantics |
| empty | R2 | ⛔ dismissed | Schema creation takes no input set |
| ordering | R2 | ⛔ dismissed | No output ordering for DDL |
| boundary | R3 | ✅ covered | Threshold inclusive: sim ≥ 0.85 links, < 0.85 separates (AC) |
| precision | R3 | ✅ covered | pgvector `<=>` cosine distance; compare `1 - dist ≥ 0.85`; no custom rounding |
| idempotency | R4 | ✅ covered | Duplicate `put_blob` is a single-file no-op (AC) |
| concurrency | R4 | ✅ covered | Write temp + `os.replace` (atomic); identical concurrent writes converge (content-addressed) |
| adjacency | R5 | ⛔ dismissed | Store interface has no merge/touch semantics |
| empty | R5 | ✅ covered | `get_item` miss → `None`; empty query → `[]` (AC) |
| ordering | R5 | ✅ covered | List queries `ORDER BY (ts, id)` — stable |
| idempotency | R5 | ✅ covered | `put_item` upsert on `Item.id`, last-write-wins (AC) |
| concurrency | R5 | ✅ covered | Postgres transactional guarantees; one connection per op |
| idempotency | R6 | ✅ covered | Re-running a retrofitted script → no dup rows (relies on R5 upsert) |
| concurrency | R6 | ✅ covered | Concurrent script runs safe via Postgres transactions |
| idempotency | R7 | ✅ covered | Atom projection is a pure read → same output for same state |
| concurrency | R7 | ✅ covered | Projection is read-only — safe concurrently |
| boundary | R8 | ✅ covered | Integration test skips iff connection to `:22000` fails within timeout |
| precision | R8 | ✅ covered | Cosine round-trip asserted within epsilon / by top-k ordering |

## Prohibitions (must-NOT)

**Coverage:** 2/2 applicable prohibitions resolved · 0 unresolved

| Prohibition (must-NOT statement) | Requirement | Status | Verification / Reason |
|----------------------------------|-------------|--------|------------------------|
| MUST NOT silently lose or truncate a write — a failed persist raises; never a silent no-op (documented content-dedup no-op excepted) | R5, R6 | resolved | verification: test (negative test: induced write failure raises, does not return success) |
| MUST NOT let `InMemoryStore` diverge from `PostgresStore`'s observable contract (same Protocol, same `None`/`[]`/error semantics) | R5, R8 | resolved | verification: test (shared contract test parametrized over both impls) |
| _(canon — not minted here)_ SQL injection via string-built queries | R5 | breadcrumb | Owned by parameterized psycopg3 queries + /gsd-secure-phase; not a bespoke prohibition |
| _(canon — not minted here)_ secrets / raw PII stored in `audit` or blobs in plaintext | R4, R2 | breadcrumb | Owned by /gsd-secure-phase + GDPR review; not minted here |

## Ambiguity Report

| Dimension          | Score | Min  | Status | Notes                                          |
|--------------------|-------|------|--------|------------------------------------------------|
| Goal Clarity       | 0.88  | 0.75 | ✓      | Named deliverables, schema, store shape locked |
| Boundary Clarity   | 0.82  | 0.70 | ✓      | Explicit later-phase exclusions                |
| Constraint Clarity | 0.85  | 0.65 | ✓      | psycopg3 sync, plain-SQL, sharded sha256 blobs |
| Acceptance Criteria| 0.82  | 0.70 | ✓      | 13 pass/fail criteria incl. 2 negative         |
| **Ambiguity**      | 0.15  | ≤0.20| ✓      |                                                |

Status: ✓ = met minimum, ⚠ = below minimum (planner treats as assumption)

## Interview Log

| Round | Perspective        | Question summary                          | Decision locked                                            |
|-------|--------------------|-------------------------------------------|------------------------------------------------------------|
| 1     | Researcher         | How much of the 7-table schema now?       | All 7 created; full DDL where known, `enrichment`/`ccir` stubs |
| 1     | Researcher         | Store API sync vs async?                   | Sync (psycopg3) Protocol + impl + in-memory fake; async later |
| 1     | Boundary Keeper    | Retrofit + backfill scope?                 | Retrofit scripts now; NO historical backfill (fresh-forward) |
| 2     | Researcher         | Schema management mechanism?               | Plain-SQL DDL applied idempotently by `store.init_schema()` |
| 2     | Simplifier         | Blob store details?                        | `sha256`-of-content, sharded `ab/cd/<hash>`, write-once dedup |
| 2     | Failure Analyst    | Test + provisioning strategy?              | Fake unit tests + one live integration test (skip if no DB); docker-compose pg16+pgvector `:22000` |
| 3     | Failure Analyst    | Threshold edge at exactly 0.85?            | Inclusive — sim ≥ 0.85 merges                              |
| 3     | Failure Analyst    | `put_item` on existing id?                 | Idempotent upsert (`ON CONFLICT DO UPDATE`), last-write-wins |
| 3     | Failure Analyst    | Concurrency guarantee?                      | Lean on Postgres txns + atomic blob rename; no app locking |
| 3     | Boundary Keeper    | Bespoke must-NOTs?                          | Keep no-silent-data-loss (test) + fake-must-not-diverge (shared contract test) |

---

*Phase: 02-storage-postgres-blobs*
*Spec created: 2026-06-28*
*Next step: /gsd-discuss-phase 2 — implementation decisions (how to build what's specified above)*
