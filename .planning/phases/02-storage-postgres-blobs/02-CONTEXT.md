# Phase 2: Storage — Postgres + blobs - Context

**Gathered:** 2026-06-28
**Status:** Ready for planning

<domain>
## Phase Boundary

Build the canonical persistence layer: a Postgres 16 + pgvector schema, an on-disk
content-addressed blob store, a single synchronous `store` interface (Protocol + Postgres impl +
in-memory fake), retrofit of existing scripts onto the store, and a FreshRSS Atom-projection
writer. No enrichment/ccir logic, no entity-resolution logic, no async, no embedding generation,
no historical backfill (see SPEC boundaries).

</domain>

<spec_lock>
## Requirements (locked via SPEC.md)

**8 requirements are locked.** See `02-SPEC.md` for full requirements, boundaries, acceptance
criteria, edge coverage, and prohibitions.

Downstream agents MUST read `02-SPEC.md` before planning or implementing. Requirements are not
duplicated here.

**In scope (from SPEC.md):**
- Postgres 16 + pgvector `:22000` service (docker-compose) + idempotent plain-SQL `init_schema()`
- All 7 tables (5 full: articles/audit/embeddings/entities/entity_links; 2 stubbed: enrichment/ccir); pgvector `vector(1024)` + HNSW cosine, link threshold ≥ 0.85 inclusive
- Content-addressed, sharded (`data/blobs/ab/cd/<hash>`), write-once blob store
- Sync `store` Protocol + `PostgresStore` (psycopg3) + `InMemoryStore` fake; `put_item` idempotent upsert
- Retrofit existing ingest/triage/digest scripts onto the store (no historical backfill)
- FreshRSS Atom-projection writer behind the store
- In-memory-fake unit tests + one live integration test (skip if DB down)
- Two must-NOTs (test-tier): no-silent-data-loss; fake-must-not-diverge

**Out of scope (from SPEC.md):**
- enrichment/ccir column definitions + logic (scoring phase ≈ P4); entity-resolution logic (P8)
- Historical data backfill; async store / aio-pika (P3); app-level concurrency locks
- Embedding generation (mE5-large inference, P5/8) — Phase 2 only stores/queries vectors

</spec_lock>

<decisions>
## Implementation Decisions

### Store package location & dependencies
- **D-01:** The store ships as a new installable package **`libs/store`** with its own
  `pyproject.toml` (editable install), mirroring Phase-1 D-01. It **depends on `contracts`** and
  imports `contracts.Item` (static typing against the canonical Item). Fills the gap the design
  doc's repo layout left (it lists `libs/contracts/` but no `libs/store/`).
- **D-01a (discretion):** The blob store lives inside `libs/store` and is exposed through the same
  `Store` interface (`put_blob`/`get_blob`) per SPEC R4/R5 — one mediating interface, not two.

### articles ↔ Item mapping & FTS scope
- **D-02:** `articles` uses a **hybrid mapping**: core/queryable fields as real columns
  (`id` PK, `source`, `source_type`, `url`, `title`, `ts`, `lang`, `body_ref`) for indexing/typed
  queries, plus the full `Item.payload` in a **JSONB** column. (Not all-JSONB — that loses indexing
  on common query axes: source_type, ts, lang.)
- **D-02a:** **FTS is deferred** to the search/RAG phase that actually queries it. Phase 2 does NOT
  add a `tsvector`/GIN column on `articles`, even though the design doc lists "JSONB+FTS" as the
  eventual store shape. Keeps Phase 2 within SPEC scope.

### Connection config & pooling
- **D-03:** Connection comes from a **single DSN env var** (e.g. `INFOTRIAGE_PG_DSN`) loaded from
  `.env` at runtime (Phase-1 D-02 — never baked into the package). The store is a **context manager**
  that opens one psycopg3 connection and closes it; **no connection pool** in Phase 2.
- **D-03a:** A pool (`psycopg_pool`) is deferred to P3+ when concurrent services arrive — it can be
  added behind the same `Store` Protocol without changing callers.

### Atom-projection writer (R7)
- **D-04:** **Pull-on-demand** projection (resolves the SPEC R7 flag): a read that queries stored
  articles and renders Atom XML; stateless and deterministic. NOT write-on-ingest (avoids coupling
  the store to projection).
- **D-04a:** The projection is **filtered to RSS/YouTube source types** — email is excluded per the
  design doc ("Email is NOT projected to FreshRSS"). So R7's "stored articles" = RSS/YouTube items.
- **D-04b:** Render Atom via **feedgen** (already the project's Atom dependency, NF-8) — reuse, do
  not hand-roll XML.

### Vector-retrieval correctness (ai-integration consideration, 2026-06-28)
- **D-05:** Phase 2 stores/queries vectors but builds **no AI behavior** (no embedding generation,
  no LLM, no RAG — those are P5/P8). Decision: instead of a separate AI-SPEC, the plan MUST carry
  explicit **vector-retrieval-correctness** checks as `must_haves` so the pgvector surface is
  planned/verified as a retrieval component, not a dumb column.
- **D-05a:** `embeddings.embedding` and `entities.embedding` are `vector(1024)`; the **1024 dim
  MUST match the embedder contract** (mE5-large, 1024-d). A dim mismatch is a silent retrieval
  break — a test asserts the column type/dimension.
- **D-05b:** The entity-link / similarity query uses `1 - (embedding <=> %s) >= 0.85` (inclusive)
  over an HNSW index (`m=16, ef_construction=64, vector_cosine_ops`) — the locked retrieval
  contract. A smoke test inserts known vectors and asserts neighbor behavior against the
  R3-VERDICT calibration (NATO ~0.92 pair merges; Trump/Putin ~0.72 pair does **not**).
- **D-05c:** Embedding generation stays out of scope — tests supply vectors directly (fixtures);
  no model is invoked in Phase 2.

### Claude's Discretion (defaults the planner/researcher may refine)
- **DD-1:** Realize the "InfoTriage schema" as an actual Postgres `CREATE SCHEMA infotriage`
  (unquoted → lowercase) with `search_path`, rather than a name-prefix on `public` tables.
- **DD-2:** DDL organized as ordered, versioned `.sql` files under `libs/store/sql/` (e.g.
  `001-schema.sql`, `002-articles.sql`, …) applied in order by `init_schema()`; `CREATE … IF NOT
  EXISTS` throughout for idempotency.
- **DD-3:** `enrichment`/`ccir` stubs = bare tables (`id` PK, `item_id` FK → `articles`,
  `created_at`) with a comment noting later phases own the real columns.
- **DD-4:** Integration test gated by a pytest marker + a fast socket pre-check to `:22000`
  (skip when unreachable); fake/Postgres parity via a shared, parametrized contract test (SPEC P2).
- **DD-5:** `audit` table records store write events (op, table, item id, timestamp) — exact columns
  at planner discretion.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Locked requirements
- `.planning/phases/02-storage-postgres-blobs/02-SPEC.md` — Locked requirements, boundaries,
  acceptance criteria, edge coverage, prohibitions. MUST read before planning.

### Architecture / design
- `docs/superpowers/specs/2026-06-24-app-split-architecture-design.md` §"Storage — polyglot, by
  data kind" (≈ L81–104) — Postgres (JSONB+FTS+pgvector+optional PostGIS), blob store
  `data/blobs/<hash>` "never in DB", FreshRSS Atom projection is **RSS/YouTube only, not email**;
  §"Data flow" (≈ L132–143) and §"Repo layout" (≈ L145–155, shows `libs/contracts/` but no
  `libs/store/` — D-01 fills this).
- `.planning/ROADMAP.md` — Phase 2 entry: goal (Postgres canonical, SQLite rejected), 4 success
  criteria, requirement ADR-001.
- `.planning/phases/00-concept-spike/findings/R3-VERDICT.md` — validated entity/embedding schema:
  `entities(id, name, name_norm, lang, type, embedding vector(1024))` + `entity_links(entity_id FK,
  item_id, mention, lang)`, HNSW `vector_cosine_ops`, threshold 0.85 (Trump/Putin ~0.72 split,
  NATO ~0.92 merge).

### Prior-phase decisions (carried forward)
- `.planning/phases/01-contracts-monorepo-skeleton/01-CONTEXT.md` — D-01 (installable `libs/*`
  packages via editable install) and D-02 (no secrets in packages; `.env` at runtime) — the basis
  for this phase's D-01/D-03.
- `libs/contracts/src/contracts/_item.py` / `_codec.py` — the canonical `Item` shape and the
  frontmatter⇆JSONB codec the `articles` JSONB column persists.

### Constraints
- `.planning/REQUIREMENTS.md` — NF-3 (one Postgres query surface, pgvector), ADR-001 (Postgres over
  SQLite), NF-8 (stdlib-first; feedgen is the project's Atom dep), NF-6 (.env external, never
  committed).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `libs/contracts` (`Item`, `to_frontmatter`/`from_frontmatter`): the `Item` is the row shape;
  the codec maps Item.payload ⇆ the JSONB column losslessly.
- `feedgen` (already used by `apps/ingest/*` per NF-8): reuse for the R7 Atom projection.
- `apps/ingest/_util.py` `escape()` and the existing Atom-generation patterns in
  `gmail_to_atom.py`/`yt_to_atom.py`/`imap_to_atom.py` — reference for feed-entry shape.

### Established Patterns
- Phase-1 Protocol + concrete + in-memory-fake pattern (`BusClient`/`InMemoryBus`): the `Store`
  interface follows the same shape (`Store` Protocol + `PostgresStore` + `InMemoryStore`).
- Editable-install monorepo (`libs/*` packages, root `requirements-dev.txt`): add `libs/store`
  the same way.

### Integration Points
- Retrofitted scripts (`apps/triage/digest.py`, `triage_score.py`, `fever_triage.py`,
  `apps/ingest/*`) construct a `Store` from `INFOTRIAGE_PG_DSN` and read/write through it.
- The Postgres service is added to a root `docker-compose.yml` on `:22000`.

</code_context>

<specifics>
## Specific Ideas

- Schema namespace realized as a real `infotriage` Postgres schema (DD-1).
- Blob path layout exactly `data/blobs/<h[:2]>/<h[2:4]>/<h>` (SPEC R4), sha256-of-content,
  atomic temp-then-`os.replace`.
- Entity-link merge is inclusive at cosine similarity ≥ 0.85 (SPEC R3).

</specifics>

<deferred>
## Deferred Ideas

- **Full-text search (tsvector + GIN on articles)** — the design doc's "JSONB+FTS" — deferred to
  the search/RAG phase that queries it (D-02a).
- **Connection pooling (`psycopg_pool`)** — deferred to P3+ when concurrent services exist (D-03a).
- **Async store / aio-pika alignment** — Phase 3 may add an async impl behind the same Protocol.
- **PostGIS for PMESII geolocation** — "optional" in the design doc; a later geo/COP phase.
- **Bus transport conflict to resolve in Phase 3:** the design doc names *Redis Streams* as the
  in-flight transport, while ROADMAP P3 + ADR-007 specify *RabbitMQ*. Out of scope here — flagged
  for Phase 3 discuss to reconcile.

</deferred>

---

*Phase: 2-storage-postgres-blobs*
*Context gathered: 2026-06-28*
