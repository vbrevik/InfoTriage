---
phase: 02-storage-postgres-blobs
verified: 2026-06-28T20:00:00Z
status: passed
score: 4/4 must-haves verified
behavior_unverified: 0
overrides_applied: 0
---

# Phase 02: Storage — Postgres + Blobs Verification Report

**Phase Goal:** Postgres is the single canonical store; SQLite is rejected (concurrent writers).
**Verified:** 2026-06-28T20:00:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Postgres (pgvector/pgvector:pg16) runs on :22000 with infotriage schema containing all 7 tables: articles, enrichment, ccir, embeddings(vector(1024)), audit, entities, entity_links | VERIFIED | `docker exec infotriage-postgres psql ... "\dt infotriage.*"` → 7 rows confirmed; `format_type` → `vector(1024)` on embeddings and entities; HNSW indexes (m=16, ef_construction=64) confirmed in pg_indexes |
| 2 | On-disk content-addressed blob store (data/blobs/) with sharded paths holds blobs | VERIFIED | `_blob.py` implements `root/<h[:2]>/<h[2:4]>/<h>` sharding, atomic write via os.replace, traversal guard; 15 blob tests pass; directory is lazily created on first write (by-design for content-addressed storage) |
| 3 | A single `store` interface mediates all reads/writes; digest.py goes through it — not appending to data/verdicts.jsonl | VERIFIED | `Store` Protocol in `_protocol.py`; `PostgresStore` and `InMemoryStore` satisfy it; grep for `verdicts.jsonl\|persist\|STORE=` in digest.py returns 0 matches; `store.put_item()` call confirmed at line 379 |
| 4 | Atom-projection writer for FreshRSS lives behind the same Store interface | VERIFIED | `render_atom(store, limit=50) -> bytes` in `_atom.py` accepts any Store impl, pulls `list_items(source_type_in=["rss","yt"])`, renders via feedgen; email excluded (D-04a); 13 Atom tests pass |

**Score:** 4/4 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `libs/store/pyproject.toml` | Store package manifest | VERIFIED | Exists; declares deps on `contracts`, `psycopg[binary]>=3.3`, `pgvector>=0.4.2`, `numpy>=1.24` |
| `libs/store/src/store/__init__.py` | Package exports | VERIFIED | Exports `Store`, `PostgresStore`, `InMemoryStore`, `render_atom` in `__all__` |
| `libs/store/src/store/_protocol.py` | `@runtime_checkable Store Protocol` | VERIFIED | Protocol with all 8 methods; structural check: `isinstance(InMemoryStore(...), Store)` → True |
| `libs/store/src/store/_blob.py` | Content-addressed blob store | VERIFIED | Stdlib-only; `put_blob`/`get_blob`; `_shard_path` (2-level); atomic write; traversal guard |
| `libs/store/src/store/_inmemory.py` | Dict-backed fake | VERIFIED | Dict store + blob delegation to `_blob` helpers; satisfies Store Protocol |
| `libs/store/src/store/_postgres.py` | psycopg3 + pgvector impl | VERIFIED | `PostgresStore` with `init_schema` (autocommit), `put_item` (ON CONFLICT + audit), `get_item`, `list_items`, blob delegation; Jsonb wrapper; register_vector after DDL |
| `libs/store/src/store/_atom.py` | Atom projection | VERIFIED | `render_atom` → feedgen output; filters to rss/yt; deterministic (fixed epoch); returns bytes |
| `libs/store/sql/001-schema.sql` | Schema + extension DDL | VERIFIED | `CREATE SCHEMA IF NOT EXISTS infotriage`; `CREATE EXTENSION IF NOT EXISTS vector`; sorts first |
| `libs/store/sql/002-articles.sql` | articles table DDL | VERIFIED | Hybrid mapping: real columns + `payload JSONB`; no tsvector/GIN (D-02a) |
| `libs/store/sql/003-vectors.sql` | Vector tables + HNSW DDL | VERIFIED | `entities`, `entity_links`, `embeddings`; `embedding vector(1024)`; HNSW cosine (m=16, ef_construction=64); no CONCURRENTLY |
| `libs/store/sql/004-audit.sql` | audit table DDL | VERIFIED | `BIGSERIAL PK`, op, table_name, item_id, ts |
| `libs/store/sql/005-stubs.sql` | enrichment + ccir stubs | VERIFIED | Bare stub tables with FK to articles and comment marking later phases |
| `apps/triage/digest.py` | Retrofitted digest (store-backed) | VERIFIED | Imports `PostgresStore`; `map_verdict_to_item` helper; `store.put_item()` at line 379; INFOTRIAGE_PG_DSN; `persist()` and `STORE` constant removed |
| `docker-compose.yml` | Postgres service on :22000 | VERIFIED | `pgvector/pgvector:pg16`, port `127.0.0.1:22000:5432`, `pg_isready` healthcheck, infotriage network |
| `requirements-dev.txt` | `-e ./libs/store` entry | VERIFIED | Line 2: `-e ./libs/store` confirmed |
| `pyproject.toml` | `db_live` marker registration | VERIFIED | `markers = ["db_live: requires Postgres :22000 to be running"]` |
| `tests/test_store_blob.py` | Blob unit tests | VERIFIED | 15 tests; roundtrip, dedup, sharding, traversal guard, atomic failure |
| `tests/test_store_contract.py` | Shared parametrized contract tests | VERIFIED | 12 tests; inmemory+postgres params; lazy postgres import; upsert, miss→None, empty→[], ordering, source_type filter, blob roundtrip |
| `tests/test_atom_projection.py` | Atom projection tests | VERIFIED | 13 tests; rss/yt included, imap excluded, valid XML, deterministic |
| `tests/test_store_integration.py` | Live integration tests | VERIFIED | 7 db_live tests: init idempotency, 7-tables, item roundtrip, live upsert, vector(1024), cosine threshold (NATO links/Putin stays distinct), no-silent-loss |
| `tests/test_digest_retrofit.py` | Retrofit unit tests | VERIFIED | 12 tests; mapping correctness, store-backed persistence, upsert |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `digest.py` | `PostgresStore` | `from store import PostgresStore` | WIRED | Line 22 import; used at lines 374-379 as context manager |
| `digest.py` | `INFOTRIAGE_PG_DSN` | `os.environ["INFOTRIAGE_PG_DSN"]` | WIRED | Line 374; raises KeyError if absent (no silent failure) |
| `PostgresStore.init_schema` | `libs/store/sql/*.sql` | `sorted(sql_dir.glob("*.sql"))` | WIRED | `_postgres.py` line 103-104; lexical order, autocommit connection |
| `PostgresStore.put_item` | `infotriage.audit` | same transaction | WIRED | `_postgres.py` lines 157-163; audit INSERT in same transaction (DD-5) |
| `InMemoryStore.put_blob/get_blob` | `_blob` helpers | `from ._blob import put_blob as _put_blob` | WIRED | `_inmemory.py` lines 18-19; delegates filesystem I/O |
| `render_atom` | `store.list_items(source_type_in=["rss","yt"])` | `_atom.py` line 59 | WIRED | D-04a filter applied in list_items call; email excluded |
| `PostgresStore` payload | `Jsonb()` wrapper | `from psycopg.types.json import Jsonb` | WIRED | `_postgres.py` line 153; Pitfall 2 avoided |
| `PostgresStore` vector registration | `register_vector(ddl_conn)` after DDL | `_postgres.py` line 105 | WIRED | Called after SQL execution loop (bug-fix: after CREATE EXTENSION, not before) |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `digest.py` persistence seam | `store.put_item(map_verdict_to_item(v))` | `fetch_window()` → `score_item()` → verdict dict | Yes — verdict fields (title, source, ccir, score, etc.) from live Fever API + LLM scorer | FLOWING |
| `render_atom` | `items` from `store.list_items(...)` | `infotriage.articles` table via SELECT | Yes — real articles via parameterized SELECT ORDER BY ts DESC, id DESC | FLOWING |
| `_blob.py` blob content | `data` bytes at `put_blob(root, data)` | caller-supplied bytes (MIME/PDF/HTML) | N/A — no production blob written yet (digest uses body_ref=None); blob write path is complete and tested | FLOWING (ready; no production data written in Phase 2 scope) |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Store package imports + Protocol satisfied | `python -c "from store import Store, PostgresStore, InMemoryStore, render_atom; ..."` | `isinstance: True`, `pg isinstance: True` | PASS |
| Full test suite with live DB | `pytest tests/ -q --tb=no` | 158 passed | PASS |
| Full test suite without DB | `pytest tests/ -q -k "not db_live"` | 151 passed | PASS |
| Integration tests (db_live) | `pytest tests/test_store_integration.py -v --tb=short` | 7 passed | PASS |
| Unit tests (blob/contract/atom/retrofit) | `pytest tests/test_store_blob.py tests/test_store_contract.py tests/test_atom_projection.py tests/test_digest_retrofit.py -q` | 64 passed | PASS |
| Live DB — 7 tables confirmed | `docker exec infotriage-postgres psql ... "\dt infotriage.*"` | 7 rows: articles, audit, ccir, embeddings, enrichment, entities, entity_links | PASS |
| Live DB — vector(1024) confirmed | `psql ... "format_type(atttypid,atttypmod)"` on embeddings + entities | `vector(1024)` for both | PASS |
| Live DB — HNSW indexes confirmed | `psql ... pg_indexes WHERE indexname LIKE '%hnsw%'` | 2 rows: idx_entities_embedding_hnsw + idx_embeddings_embedding_hnsw (m=16, ef_construction=64) | PASS |
| Live DB — pgvector extension | `psql ... pg_extension WHERE extname='vector'` | 1 row | PASS |
| verdicts.jsonl path removed | `grep "verdicts.jsonl\|persist\|STORE\s*=" apps/triage/digest.py` | 0 matches | PASS |

### Probe Execution

No probes declared in PLAN files. Conventional `scripts/*/tests/probe-*.sh` files do not exist. Step 7c: SKIPPED (no probe files).

### Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| ADR-001 | 02-01, 02-02, 02-03, 02-04 | Postgres over SQLite (concurrent writers); one Postgres query surface | SATISFIED | PostgresStore is the canonical impl; no SQLite anywhere in Phase 2; `infotriage` schema on :22000; Store Protocol mediates all access |
| NF-3 (cross-ref) | 02-01..04 | One query surface — Postgres with InfoTriage.* schema, pgvector | SATISFIED | Single `store` interface; PostgresStore is the only persistence backend; pgvector extension installed and HNSW indexes live |

No orphaned REQUIREMENTS.md IDs for Phase 2 (REQUIREMENTS.md uses D-*, C-*, P-*, NF-* IDs; all NF-3 and ADR-001 are accounted for across all 4 plans).

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None | — | No TBD/FIXME/XXX markers | — | — |
| None | — | No TODO/HACK/PLACEHOLDER patterns | — | — |
| None | — | No empty implementations or stub returns | — | — |

Debt-marker scan: clean. No unresolved markers in any file modified by this phase.

### Human Verification Required

None. All 4 success criteria are verifiable programmatically and have been verified against the live codebase and database.

### Gaps Summary

No gaps. All 4 phase success criteria are fully achieved:

1. **Postgres + 7 tables + vector(1024) + HNSW**: Confirmed live in the running container at :22000. Schema, extension, tables, column types, and indexes all verified against the live DB via psql.

2. **Blob store infrastructure**: `_blob.py` implements the complete content-addressed blob store (sharding, atomicity, traversal guard). The `data/blobs` directory is correctly absent until the first `put_blob` call — this is by-design for content-addressed storage. 15 unit tests cover all behaviors. Phase 2 scope does not require production blob content to exist (digest.py uses `body_ref=None`; blob-producing ingest adapters come in Phase 4).

3. **Single store interface + digest.py retrofit**: `Store` Protocol mediates all reads/writes. `digest.py` removed `persist()` and `verdicts.jsonl` write path entirely; now constructs `PostgresStore` from `INFOTRIAGE_PG_DSN` and calls `store.put_item()` per verdict. `triage_score.py` / `fever_triage.py` confirmed not to be store writers per Phase 2 SPEC.

4. **Atom projection behind the store interface**: `render_atom(store)` accepts any `Store` impl, pulls RSS/YouTube items only (D-04a), renders via feedgen (D-04b). Wired to the same interface as all other reads/writes.

---

_Verified: 2026-06-28T20:00:00Z_
_Verifier: Claude (gsd-verifier)_
