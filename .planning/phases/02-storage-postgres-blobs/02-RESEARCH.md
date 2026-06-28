# Phase 02: Storage — Postgres + blobs - Research

**Researched:** 2026-06-28
**Domain:** PostgreSQL 16 + pgvector, psycopg3, content-addressed blob store, feedgen Atom projection
**Confidence:** HIGH (stack fully verified; all packages confirmed on authoritative sources)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**D-01:** `libs/store` ships as a new installable package with its own `pyproject.toml` (editable install), depends on `contracts`, imports `contracts.Item`.
**D-01a:** Blob store lives inside `libs/store`, exposed through the same `Store` interface (`put_blob`/`get_blob`) — one mediating interface, not two.
**D-02:** `articles` uses a hybrid mapping: core/queryable fields as real columns + full `Item.payload` in a JSONB column. NOT all-JSONB.
**D-02a:** FTS (tsvector + GIN) deferred to the search/RAG phase. Phase 2 does NOT add a tsvector column.
**D-03:** Connection from a single DSN env var `INFOTRIAGE_PG_DSN`, loaded from `.env` at runtime. Store is a context manager that opens one psycopg3 connection and closes it. No connection pool.
**D-03a:** Pool (`psycopg_pool`) deferred to P3+.
**D-04:** Pull-on-demand Atom projection (reads stored articles, renders Atom XML); NOT write-on-ingest.
**D-04a:** Projection filtered to RSS/YouTube source types only — email EXCLUDED.
**D-04b:** Render Atom via `feedgen` (already the project's Atom dependency, NF-8).

### Claude's Discretion

**DD-1:** `infotriage` Postgres schema via `CREATE SCHEMA infotriage` (unquoted → lowercase) with `search_path`, rather than name-prefix on public tables.
**DD-2:** DDL as ordered, versioned `.sql` files under `libs/store/sql/` (e.g. `001-schema.sql`, `002-articles.sql`) applied in order by `init_schema()`, with `CREATE … IF NOT EXISTS` throughout.
**DD-3:** `enrichment`/`ccir` stubs = bare tables (`id` PK, `item_id` FK → `articles`, `created_at`) with a comment noting later phases own the columns.
**DD-4:** Integration test gated by a pytest marker + fast socket pre-check to `:22000`; fake/Postgres parity via a shared, parametrized contract test.
**DD-5:** `audit` table records store write events (op, table, item id, timestamp) — exact columns at planner discretion.

### Deferred Ideas (OUT OF SCOPE)

- Full-text search (tsvector + GIN on articles) — deferred to search/RAG phase
- Connection pooling (`psycopg_pool`) — deferred to P3+
- Async store / aio-pika alignment — Phase 3
- PostGIS for PMESII geolocation — later geo/COP phase
- Bus transport conflict (Redis Streams vs RabbitMQ) — Phase 3 discuss
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| R1 | `store.init_schema()` applies plain-SQL DDL idempotently — `CREATE EXTENSION IF NOT EXISTS vector` + all tables; second run is a no-op | psycopg3 DDL execution via autocommit; `IF NOT EXISTS` throughout; versioned SQL files |
| R2 | All 7 tables exist after init (5 full: articles, audit, embeddings, entities, entity_links; 2 stubs: enrichment, ccir) | Schema DDL patterns, FK relationships, stub table design (DD-3) |
| R3 | `embeddings`/`entities` use `vector(1024)` with HNSW `vector_cosine_ops`; link threshold 0.85 inclusive | pgvector HNSW index creation; `<=>` cosine distance; similarity = `1 - distance`; threshold filter |
| R4 | Content-addressed blob store: sha256-sharded `data/blobs/ab/cd/<hash>`, write-once, atomic via temp+`os.replace` | Pure stdlib + os; no external dep |
| R5 | Store Protocol + `PostgresStore` (psycopg3) + `InMemoryStore` fake; `put_item` upsert on Item.id; `get_item` miss → None | psycopg3 ON CONFLICT DO UPDATE; typing.Protocol @runtime_checkable; InMemoryStore dict |
| R6 | Existing ingest/triage/digest scripts retrofitted onto store; no historical backfill | digest.py `persist()` replacement; ingest Item construction; triage_score.py unchanged |
| R7 | FreshRSS Atom-projection writer: pull-on-demand, RSS/YT only, via feedgen | feedgen FeedGenerator API; list_items filter; atom_str() |
| R8 | Unit tests on InMemoryStore; one live integration test (init_schema + cosine round-trip) skipped if DB unreachable; docker-compose pg16+pgvector on :22000 | pytest marker + socket pre-check; pgvector/pgvector:pg16 image (already cached) |
</phase_requirements>

---

## Summary

Phase 2 builds the canonical persistence layer for InfoTriage. The core challenge is not algorithmic — the schema is fully specified from Phase 0 spike results — but structural: a well-designed `libs/store` package that mirrors the Phase 1 `libs/contracts` pattern (Protocol + concrete + in-memory fake), integrates psycopg3 with the pgvector type adapter, and wraps a content-addressed blob store behind the same interface.

The primary technical risk is the psycopg3 / pgvector type registration seam: `register_vector(conn)` must be called once per connection after opening, and numpy arrays must be used for vector parameters. The secondary risk is the `init_schema()` DDL execution strategy — plain SQL files work cleanly with psycopg3's non-parameterized execution path, but the commit/autocommit boundary matters for `CREATE EXTENSION IF NOT EXISTS vector` (the vector extension must be installed; if already present, the `IF NOT EXISTS` makes it a no-op).

The retrofit scope is intentionally shallow: `digest.py` `persist()` and the ingest scripts need to call `store.put_item()` and optionally `store.put_blob()`. No historical data migration is in scope.

**Primary recommendation:** Model `libs/store` exactly after `libs/contracts` — `pyproject.toml` with editable install, `typing.Protocol` with `@runtime_checkable`, inner `_postgres.py` / `_inmemory.py` modules, and shared parametrized contract tests. Add versioned `.sql` files under `libs/store/sql/`. Expose blob operations as first-class `Store` Protocol methods.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Schema bootstrap (`init_schema`) | `PostgresStore` (libs/store) | — | DDL is a store-level concern; callers never touch raw SQL |
| Item persistence (put/get/list) | `PostgresStore` (libs/store) | `InMemoryStore` fake (tests) | Store Protocol abstracts both behind same interface |
| Blob content storage | `_blob.py` helper (inside libs/store) | — | On-disk, not DB; accessed via `put_blob`/`get_blob` on Store Protocol |
| Vector similarity search | Postgres + pgvector (DB tier) | — | HNSW index lives in DB; Python only passes query vector |
| Atom projection | Projection fn in `libs/store` or `apps/` | — | Pure read from Store; stateless function `render_atom(store) -> bytes` |
| Script retrofit | `apps/triage/digest.py`, `apps/ingest/*` | — | Callers own their Store construction; store is injected or constructed in main() |
| Docker service | `docker-compose.yml` (root) | — | Single compose file for all services |

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| psycopg | 3.3.4 | PostgreSQL adapter (sync) | Official psycopg3; modern Python driver with native async support deferrable for P3; sync interface matches current single-process scripts |
| pgvector (Python) | 0.4.2 | Register vector type adapters for psycopg3; numpy array ↔ `vector` column | Official Python client from the pgvector project; only way to correctly serialize numpy arrays to pgvector types |
| feedgen | 1.0.0 | Atom XML generation | Already in `requirements.txt` (NF-8); no new runtime dep |
| numpy | (transitive via pgvector) | Vector array representation for pgvector params | Required by pgvector-python; already installed on system |

[VERIFIED: context7 /websites/psycopg_psycopg3, /pgvector/pgvector-python, /lkiesow/python-feedgen] [VERIFIED: pip3 index versions psycopg — 3.3.4 is latest]

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| psycopg[binary] | 3.3.4 | Pre-compiled C extension for psycopg3 | Development installs; avoids needing libpq-dev. Use `psycopg[binary]` in `pyproject.toml` |
| hashlib | stdlib | SHA-256 for blob content addressing | No additional dep; `hashlib.sha256(data).hexdigest()` |
| os / pathlib | stdlib | Atomic blob write (`os.replace`), path manipulation | No additional dep |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| psycopg3 (sync) | asyncpg | asyncpg is async-only; current scripts are sync. Defer to P3 |
| psycopg3 (sync) | psycopg2 | psycopg2 is the old adapter; psycopg3 is the modern successor with better type support |
| Plain SQL files | SQLAlchemy, Alembic | NF-8 (stdlib-first): no migration framework. `IF NOT EXISTS` makes plain SQL idempotent |
| numpy arrays for vectors | pgvector.Vector() wrapper | Both work; numpy arrays pass directly after `register_vector`. Vector() wrapper is an alternative |

**Installation (for `libs/store/pyproject.toml`):**
```toml
[project]
name = "store"
version = "0.1.0"
dependencies = [
    "contracts",            # editable, from libs/contracts
    "psycopg[binary]>=3.3",
    "pgvector>=0.4.2",
    "numpy>=1.24",
]
```

**Editable install (add to `requirements-dev.txt`):**
```
-e ./libs/store
```

---

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| psycopg | PyPI | Active since 2021 (v3.0); 3.x lineage; latest 3.3.4 on 2026-05-01 | Unknown (PyPI does not expose counts via index API) | psycopg.org (official) | SUS (unknown-downloads) | Approved — well-established official driver; confirmed via Context7 official docs |
| psycopg-binary | PyPI | Same lineage as psycopg | Unknown | psycopg.org (official) | SUS (unknown-downloads) | Approved — companion binary wheel for psycopg |
| pgvector | PyPI | 0.4.2 published 2025-12-05; GitHub: pgvector/pgvector-python | Unknown | github.com/pgvector/pgvector-python | SUS (unknown-downloads) | Approved — official Python client from the pgvector project; already installed (0.4.2) |
| feedgen | PyPI | 2023-12-25 (1.0.0); project active since 2013 | Unknown | lkiesow.github.io/python-feedgen | SUS (unknown-downloads) | Approved — already in requirements.txt; long-established |

**SUS verdict explanation:** All four packages return `SUS` due to `unknown-downloads` — the legitimacy seam cannot retrieve download counts from PyPI's index API. This is a data-availability limitation, not a red flag. All packages are confirmed via authoritative sources (official documentation, official GitHub organizations) fetched via Context7.

**Packages removed due to SLOP verdict:** none

**Packages flagged as suspicious (SUS) requiring human-verify checkpoint:** none — SUS verdicts are due to PyPI download-count unavailability, not legitimacy signals. These are the canonical packages for their respective purposes.

---

## Architecture Patterns

### System Architecture Diagram

```
  INGEST SCRIPTS               STORE INTERFACE              STORAGE BACKENDS
  (apps/ingest/*)              (libs/store)
  
  gmail_to_atom.py ──┐         ┌──────────────────┐        ┌─────────────────────┐
  imap_to_atom.py  ──┤ Item    │  Store Protocol  │        │  PostgreSQL 16      │
  yt_to_atom.py    ──┤──────►  │  put_item(item)  │──────► │  :22000             │
                     │         │  get_item(id)    │        │  schema: infotriage │
  TRIAGE SCRIPTS               │  list_items(..)  │        │  + pgvector         │
  (apps/triage/*)              │  put_blob(bytes) │        └──────────┬──────────┘
                     │         │  get_blob(hash)  │                   │
  digest.py ─────────┘         └────────┬─────────┘        ┌──────────▼──────────┐
                                        │                   │  data/blobs/        │
                                        │ test fake         │  ab/cd/<sha256>     │
                                        ▼                   │  (write-once, dedup)│
                               InMemoryStore (dict)         └─────────────────────┘
                               (unit tests only)
                                        
  ATOM PROJECTION (R7)
  render_atom(store) ──────────► list_items(source_type_in=["rss","yt"])
                                         │
                                         ▼
                                 feedgen FeedGenerator
                                         │
                                         ▼
                                 valid Atom XML (bytes)
```

### Recommended Project Structure
```
libs/store/
├── pyproject.toml            # declares psycopg[binary], pgvector, numpy deps
├── sql/
│   ├── 001-schema.sql        # CREATE SCHEMA infotriage; CREATE EXTENSION vector
│   ├── 002-articles.sql      # articles table (Item mapping + JSONB payload)
│   ├── 003-vectors.sql       # embeddings, entities, entity_links + HNSW indexes
│   ├── 004-audit.sql         # audit table
│   └── 005-stubs.sql         # enrichment + ccir stubs (Phase 4/8 extend)
└── src/
    └── store/
        ├── __init__.py       # exports Store, PostgresStore, InMemoryStore, BlobStore
        ├── _protocol.py      # Store Protocol (@runtime_checkable typing.Protocol)
        ├── _postgres.py      # PostgresStore: psycopg3 + register_vector
        ├── _inmemory.py      # InMemoryStore: dict-based fake
        └── _blob.py          # blob helpers: hash(), shard_path(), put(), get()

tests/
├── test_store_contract.py    # shared parametrized contract tests (InMemory + Postgres)
├── test_store_blob.py        # blob store unit tests
└── test_atom_projection.py   # Atom projection unit tests
```

### Pattern 1: Store Protocol (mirrors Phase-1 BusClient)
**What:** `typing.Protocol` with `@runtime_checkable` so callers can do `isinstance(store, Store)`
**When to use:** All store construction, injection in scripts and tests

```python
# Source: Phase-1 pattern (libs/contracts/src/contracts/_bus.py); adapted for Store
from typing import Protocol, runtime_checkable
from contracts import Item

@runtime_checkable
class Store(Protocol):
    """Single mediating interface for all InfoTriage persistence.
    
    Implementations: PostgresStore (production), InMemoryStore (tests).
    Context manager: opens and closes the underlying connection.
    """
    def __enter__(self) -> "Store": ...
    def __exit__(self, *args) -> None: ...

    def init_schema(self) -> None:
        """Apply all DDL idempotently. Safe to call on an existing schema."""
        ...

    def put_item(self, item: Item) -> None:
        """Upsert item by item.id (ON CONFLICT DO UPDATE). Raises on failure."""
        ...

    def get_item(self, item_id: str) -> Item | None:
        """Return Item for id, or None on miss."""
        ...

    def list_items(
        self,
        source_type_in: list[str] | None = None,
        limit: int = 200,
    ) -> list[Item]:
        """Return items ordered by (ts DESC, id). Empty list on no match."""
        ...

    def put_blob(self, data: bytes) -> str:
        """Store bytes, return sha256 hex. Duplicate put is a no-op. Raises on failure."""
        ...

    def get_blob(self, blob_hash: str) -> bytes:
        """Return bytes for hash. Raises FileNotFoundError on miss."""
        ...
```

### Pattern 2: PostgresStore — psycopg3 with pgvector registration
**What:** Context manager that opens one psycopg3 connection, registers vector types, exposes Store Protocol
**When to use:** Production; construction from `INFOTRIAGE_PG_DSN` env var

```python
# Source: https://www.psycopg.org/psycopg3/docs/api/connections.html
#         https://github.com/pgvector/pgvector-python/blob/master/_autodocs/examples.md
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pgvector.psycopg import register_vector
from pathlib import Path

class PostgresStore:
    def __init__(self, dsn: str, blob_root: Path) -> None:
        self._dsn = dsn
        self._blob_root = blob_root
        self._conn: psycopg.Connection | None = None

    def __enter__(self) -> "PostgresStore":
        self._conn = psycopg.connect(self._dsn, row_factory=dict_row)
        register_vector(self._conn)   # must be called before any vector queries
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._conn:
            if exc_type is None:
                self._conn.commit()
            else:
                self._conn.rollback()
            self._conn.close()
            self._conn = None
```

### Pattern 3: init_schema — idempotent DDL execution
**What:** Apply ordered SQL files; safe to run on an existing schema
**When to use:** Once at startup or deployment; safe to re-run

```python
# Source: https://www.psycopg.org/psycopg3/docs/basic/transactions.html (autocommit)
def init_schema(self) -> None:
    """Apply all DDL files under sql/ in order. Idempotent (IF NOT EXISTS throughout)."""
    sql_dir = Path(__file__).parent.parent.parent / "sql"
    # Use a fresh autocommit connection for DDL.
    # CREATE EXTENSION requires superuser or the extension to be trusted;
    # autocommit avoids a wrapping transaction that could cause issues
    # with certain PostgreSQL configurations.
    with psycopg.connect(self._dsn, autocommit=True) as ddl_conn:
        register_vector(ddl_conn)
        for sql_file in sorted(sql_dir.glob("*.sql")):
            ddl_conn.execute(sql_file.read_text())
```

**Why autocommit for DDL:** psycopg3 defaults to a transaction wrapper. `CREATE EXTENSION IF NOT EXISTS vector` and `CREATE INDEX USING hnsw` both work in transactions on Postgres 16, but using `autocommit=True` for the DDL connection avoids edge cases where some DDL cannot be rolled back and simplifies error recovery. [CITED: https://www.psycopg.org/psycopg3/docs/basic/transactions.html]

### Pattern 4: put_item — idempotent upsert (ON CONFLICT)
**What:** Last-write-wins upsert keyed on `Item.id`
**When to use:** Every time an ingest script calls `store.put_item(item)`

```python
# Source: https://www.psycopg.org/psycopg3/docs/basic/adapt.html (Jsonb)
def put_item(self, item: Item) -> None:
    assert self._conn is not None, "Use PostgresStore as context manager"
    self._conn.execute("""
        INSERT INTO infotriage.articles
            (id, source, source_type, url, title, ts, lang, summary, body_ref, payload)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE SET
            source       = EXCLUDED.source,
            source_type  = EXCLUDED.source_type,
            url          = EXCLUDED.url,
            title        = EXCLUDED.title,
            ts           = EXCLUDED.ts,
            lang         = EXCLUDED.lang,
            summary      = EXCLUDED.summary,
            body_ref     = EXCLUDED.body_ref,
            payload      = EXCLUDED.payload
    """, (
        item.id, item.source, item.source_type, item.url, item.title,
        item.ts, item.lang, item.summary, item.body_ref,
        Jsonb(item.payload)       # psycopg3 requires Jsonb() wrapper for JSONB columns
    ))
    self._conn.commit()
```

### Pattern 5: pgvector cosine similarity — threshold ≥ 0.85
**What:** Find entities whose embedding is within cosine distance threshold of a query vector
**When to use:** Entity linking (Phase 8 will use this); Phase 2 exposes it as a schema capability

```sql
-- Source: https://github.com/pgvector/pgvector/blob/master/_autodocs/api-reference/vector-operators.md
-- <=> returns cosine DISTANCE (0=identical, 2=opposite). Cosine SIMILARITY = 1 - distance.
-- For threshold >= 0.85 (inclusive):
SELECT id, name, 1 - (embedding <=> %s) AS similarity
FROM infotriage.entities
WHERE 1 - (embedding <=> %s) >= 0.85
ORDER BY embedding <=> %s
LIMIT 10;
```

```python
# Python side: pass numpy float32 array after register_vector(conn)
import numpy as np
query_vec = np.array([...], dtype=np.float32)   # must be float32, dim=1024
cur = conn.execute(
    "SELECT id, name, 1-(embedding <=> %s) AS sim FROM infotriage.entities "
    "WHERE 1-(embedding <=> %s) >= 0.85 ORDER BY embedding <=> %s LIMIT 10",
    (query_vec, query_vec, query_vec)
)
```

### Pattern 6: Blob store — write-once, sharded, atomic
**What:** Content-addressed, shard-rooted file store; each blob stored exactly once
**When to use:** Storing raw HTML, PDF, transcripts, MIME content for an Item

```python
# Source: stdlib — os.replace() atomic rename (POSIX-atomic within same filesystem)
import hashlib, os
from pathlib import Path

BLOB_SHARD_DEPTH = 2  # data/blobs/ab/cd/<sha256>

def _shard_path(root: Path, h: str) -> Path:
    return root / h[:2] / h[2:4] / h

def put_blob(self, data: bytes) -> str:
    h = hashlib.sha256(data).hexdigest()
    dest = _shard_path(self._blob_root, h)
    if dest.exists():
        return h              # dedup: exact same bytes already stored, no-op
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp")
    try:
        tmp.write_bytes(data)
        os.replace(str(tmp), str(dest))  # atomic rename — POSIX guarantee
    except Exception:
        tmp.unlink(missing_ok=True)      # cleanup partial write
        raise                            # never silently swallow write failures
    return h

def get_blob(self, blob_hash: str) -> bytes:
    return _shard_path(self._blob_root, blob_hash).read_bytes()
    # read_bytes() raises FileNotFoundError on miss — caller handles
```

### Pattern 7: Integration test skip via socket pre-check
**What:** pytest marker + socket check; skip integration tests when Postgres is unreachable
**When to use:** CI without DB; local dev without docker up

```python
# Source: https://github.com/pytest-dev/pytest/blob/main/doc/en/how-to/skipping.rst
import socket, pytest

def _pg_reachable() -> bool:
    """Return True if :22000 accepts a TCP connection within 1 second."""
    try:
        with socket.create_connection(("localhost", 22000), timeout=1.0):
            return True
    except OSError:
        return False

# Evaluated once at collection time — fast, no DB ping
db_live = pytest.mark.skipif(
    not _pg_reachable(),
    reason="Postgres :22000 unreachable — integration test skipped"
)
```

**Register the marker in `pyproject.toml`:**
```toml
[tool.pytest.ini_options]
markers = [
    "db_live: requires Postgres :22000 to be running",
]
```

### Pattern 8: feedgen Atom projection
**What:** Pull-on-demand Atom feed from stored articles; RSS/YouTube only
**When to use:** FreshRSS subscription to stored article feed

```python
# Source: https://github.com/lkiesow/python-feedgen/blob/main/readme.rst
from feedgen.feed import FeedGenerator

def render_atom(store: Store, limit: int = 50) -> bytes:
    """Pull-on-demand Atom projection of RSS+YouTube articles. Email excluded (D-04a)."""
    fg = FeedGenerator()
    fg.id("http://localhost/infotriage/atom")
    fg.title("InfoTriage")
    fg.link(href="http://localhost/", rel="alternate")
    fg.link(href="http://localhost/atom.xml", rel="self")
    fg.language("no")
    fg.updated(datetime.datetime.now(tz=datetime.timezone.utc))

    items = store.list_items(source_type_in=["rss", "yt"], limit=limit)
    for item in items:
        fe = fg.add_entry(order="append")
        fe.id(item.url or f"infotriage:{item.id}")
        fe.title(item.title)
        if item.url:
            fe.link(href=item.url)
        fe.published(item.ts)
        fe.updated(item.ts)
        if item.summary:
            fe.summary(item.summary)

    return fg.atom_str(pretty=True)  # returns bytes — decode utf-8 if str needed
```

### Pattern 9: Shared parametrized contract test
**What:** Same test suite runs against both InMemoryStore and PostgresStore
**When to use:** Must-NOT prohibition — fake must not diverge from Postgres semantics

```python
# Source: Phase-1 pattern; pytest parametrize with marks
@pytest.fixture(params=[
    "inmemory",
    pytest.param("postgres", marks=db_live),
])
def store(request, tmp_path):
    if request.param == "inmemory":
        s = InMemoryStore(blob_root=tmp_path / "blobs")
        yield s
    else:
        dsn = os.environ.get("INFOTRIAGE_PG_DSN", "postgresql://infotriage:infotriage_dev@localhost:22000/infotriage")
        with PostgresStore(dsn=dsn, blob_root=tmp_path / "blobs") as s:
            s.init_schema()
            yield s

def test_put_get_roundtrip(store, sample_item):
    store.put_item(sample_item)
    got = store.get_item(sample_item.id)
    assert got is not None
    assert got.id == sample_item.id
    assert got.title == sample_item.title

def test_get_miss_returns_none(store):
    assert store.get_item("nonexistent-id") is None

def test_put_item_upsert(store, sample_item):
    store.put_item(sample_item)
    modified = sample_item.model_copy(update={"title": "Updated Title"})
    store.put_item(modified)
    got = store.get_item(sample_item.id)
    assert got.title == "Updated Title"   # last-write-wins

def test_list_empty_returns_empty_list(store):
    assert store.list_items() == []
```

### Anti-Patterns to Avoid

- **Passing a Python dict directly as a JSONB parameter:** `conn.execute("INSERT ... VALUES (%s)", (item.payload,))` will fail or produce unexpected results. Always use `Jsonb(item.payload)` from `psycopg.types.json`.

- **Calling vector queries before `register_vector(conn)`:** Without type registration, numpy arrays are serialized as text, not as the pgvector `vector` type. psycopg3 will raise a type error or silently corrupt the query. Always call `register_vector(conn)` immediately after opening the connection.

- **Using `prepare=True` (or relying on the auto-prepare cache) for DDL statements:** psycopg3's statement preparation fails for DDL that contains `DEFAULT %s`. All DDL in `libs/store/sql/` should be plain SQL with no `%s` params — run them as text strings via `conn.execute(sql_text)`.

- **Writing the blob before checking existence:** The check-then-write pattern is correct for content-addressed storage because hash collisions are cosmologically impossible for sha256. If `dest.exists()` → return early without writing.

- **Using `os.rename()` instead of `os.replace()` for atomic blob writes:** `os.rename()` raises `FileExistsError` on Windows and may not be atomic across filesystems. Use `os.replace()` which is atomic on POSIX when source and destination are on the same filesystem (guaranteed when using a `.tmp` sibling).

- **Using a separate BlobStore class exposed to callers:** D-01a is explicit — one `Store` interface for everything. `put_blob`/`get_blob` are methods on `Store`, not a separate class. The blob logic is a helper module called by both impls.

- **InMemoryStore blob storage using in-memory dict:** The InMemoryStore should write blobs to a `tmp_path` directory (via `tmp_path` pytest fixture), not to a raw dict of bytes. This tests the actual path sharding logic and is closer to the real impl. [ASSUMED — but strongly implied by D-01a and SPEC R4 blob path acceptance criteria]

---

## Schema DDL Reference

### SQL file order and content

```sql
-- 001-schema.sql
CREATE SCHEMA IF NOT EXISTS infotriage;
SET search_path = infotriage, public;
CREATE EXTENSION IF NOT EXISTS vector;
```

```sql
-- 002-articles.sql
-- Maps to contracts.Item. id is the sha256 computed_field from _item.py.
CREATE TABLE IF NOT EXISTS infotriage.articles (
    id          TEXT        PRIMARY KEY,       -- sha256(source_type+url+title)
    source      TEXT        NOT NULL,          -- "NRK Nyheter"
    source_type TEXT        NOT NULL,          -- "rss", "imap", "yt"
    url         TEXT        NOT NULL DEFAULT '',
    title       TEXT        NOT NULL,
    ts          TIMESTAMPTZ NOT NULL,
    lang        TEXT        NOT NULL,
    summary     TEXT,
    body_ref    TEXT,                          -- sha256 hash → data/blobs/
    payload     JSONB       NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_articles_source_type ON infotriage.articles (source_type);
CREATE INDEX IF NOT EXISTS idx_articles_ts          ON infotriage.articles (ts DESC);
CREATE INDEX IF NOT EXISTS idx_articles_lang        ON infotriage.articles (lang);
```

```sql
-- 003-vectors.sql
CREATE TABLE IF NOT EXISTS infotriage.entities (
    id          SERIAL      PRIMARY KEY,
    name        TEXT        NOT NULL,
    name_norm   TEXT        NOT NULL,
    lang        TEXT        NOT NULL,
    type        TEXT,
    embedding   vector(1024)                   -- mE5-large / bge-m3 1024-dim
);
CREATE TABLE IF NOT EXISTS infotriage.entity_links (
    id          SERIAL      PRIMARY KEY,
    entity_id   INT         NOT NULL REFERENCES infotriage.entities(id),
    item_id     TEXT        NOT NULL REFERENCES infotriage.articles(id),
    mention     TEXT        NOT NULL,
    lang        TEXT        NOT NULL
);
CREATE TABLE IF NOT EXISTS infotriage.embeddings (
    id          SERIAL      PRIMARY KEY,
    item_id     TEXT        NOT NULL REFERENCES infotriage.articles(id),
    embedding   vector(1024) NOT NULL,
    model       TEXT        NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
-- HNSW indexes — cannot be created CONCURRENTLY, so use IF NOT EXISTS
CREATE INDEX IF NOT EXISTS idx_entities_embedding_hnsw
    ON infotriage.entities USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
CREATE INDEX IF NOT EXISTS idx_embeddings_embedding_hnsw
    ON infotriage.embeddings USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
```

```sql
-- 004-audit.sql
CREATE TABLE IF NOT EXISTS infotriage.audit (
    id          BIGSERIAL   PRIMARY KEY,
    op          TEXT        NOT NULL,          -- 'put_item', 'put_blob'
    table_name  TEXT,                          -- 'articles', etc.
    item_id     TEXT,                          -- Item.id or blob hash
    ts          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

```sql
-- 005-stubs.sql
-- Phase 4 owns enrichment columns (ccir, cnr, score, bucket, why, ...)
CREATE TABLE IF NOT EXISTS infotriage.enrichment (
    id          SERIAL      PRIMARY KEY,
    item_id     TEXT        NOT NULL REFERENCES infotriage.articles(id),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
-- Phase 4/5 defines ccir columns
CREATE TABLE IF NOT EXISTS infotriage.ccir (
    id          SERIAL      PRIMARY KEY,
    item_id     TEXT        NOT NULL REFERENCES infotriage.articles(id),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Atom XML generation | Custom string interpolation or `xml.etree` | `feedgen` (already in requirements.txt) | Handles namespace declarations, RFC 4287 compliance, encoding edge cases |
| Content hash | Custom checksum | `hashlib.sha256(data).hexdigest()` (stdlib) | Correct; no dep |
| Atomic file write | `open(dest, 'wb').write(data)` directly | `tmp.write_bytes(data); os.replace(tmp, dest)` | Direct write is non-atomic; partial failure leaves a corrupt file at the final path |
| Postgres DDL migration | Alembic, Flyway, custom versioning | Versioned `.sql` files + `IF NOT EXISTS` + `init_schema()` | NF-8 stdlib-first; `IF NOT EXISTS` makes plain SQL idempotent; no migration state table needed at this scale |
| Vector type serialization | Manual string formatting of `[1,2,3]` | pgvector-python `register_vector(conn)` + numpy array | pgvector has documented encoding for its binary protocol; hand-rolling gets array framing wrong |
| Protocol checking | `isinstance(store, PostgresStore)` | `isinstance(store, Store)` (runtime_checkable Protocol) | Protocol checking decouples callers from concrete type |

**Key insight:** The only new runtime dependencies are psycopg3 and pgvector (Python). feedgen and hashlib are already in the project. The entire blob store is stdlib. Minimal footprint.

---

## Common Pitfalls

### Pitfall 1: `register_vector` import path confusion (psycopg2 vs psycopg3)
**What goes wrong:** Using `from pgvector.psycopg2 import register_vector` instead of `from pgvector.psycopg import register_vector` — the psycopg3 adapter lives in `pgvector.psycopg`, NOT `pgvector.psycopg2`. The psycopg2 variant has identical signature but registers different type OIDs and will silently fail or error when used with a psycopg3 connection.
**Why it happens:** The pgvector-python package provides adapters for both psycopg2 and psycopg3 under different submodule paths.
**How to avoid:** Always `from pgvector.psycopg import register_vector` (no `2`).
**Warning signs:** `AttributeError: 'psycopg.Connection' object has no attribute 'cursor'` (psycopg2-style) or `ProgrammingError: can't adapt type 'numpy.ndarray'` when running vector queries.
[CITED: https://github.com/pgvector/pgvector-python/blob/master/_autodocs/database-drivers.md]

### Pitfall 2: JSONB dict not wrapped with `Jsonb()`
**What goes wrong:** `conn.execute("INSERT INTO articles ... VALUES (%s)", (item.payload,))` — psycopg3 does not automatically serialize Python dicts to JSONB. Without the `Jsonb()` wrapper, the dict is adapted as a Python object literal, causing a type error or wrong value.
**Why it happens:** psycopg3's type adaptation is explicit for JSON/JSONB to avoid ambiguity between JSON and JSONB columns.
**How to avoid:** Always wrap: `Jsonb(item.payload)` from `psycopg.types.json`.
**Warning signs:** `psycopg.errors.UndefinedFunction: operator does not exist: jsonb = text` or `ProgrammingError` during INSERT.
[CITED: https://www.psycopg.org/psycopg3/docs/basic/adapt.html]

### Pitfall 3: Forgetting `conn.commit()` in non-autocommit mode
**What goes wrong:** psycopg3 wraps all operations in a transaction by default. Without `conn.commit()`, changes are visible within the connection but not persisted; they roll back when the connection closes.
**Why it happens:** psycopg3 default is `autocommit=False`. Each `put_item` must be followed by an explicit `conn.commit()` (or the context manager exits cleanly).
**How to avoid:** Call `conn.commit()` after each `put_item`, or accumulate writes and commit in `__exit__` (see context manager pattern above).
**Warning signs:** Rows visible in the current connection's cursor but gone after reconnection.

### Pitfall 4: HNSW index creation with `CREATE INDEX CONCURRENTLY` fails inside a transaction
**What goes wrong:** `CREATE INDEX CONCURRENTLY` cannot run inside a transaction block. psycopg3 in non-autocommit mode wraps DDL in a transaction → error.
**Why it happens:** PostgreSQL restriction on concurrent index builds.
**How to avoid:** Use `CREATE INDEX IF NOT EXISTS ... USING hnsw` (without `CONCURRENTLY`) — which CAN run in a transaction and is safe for `init_schema()`. Concurrent build is only relevant for live systems with large existing tables (not needed for Phase 2).
**Warning signs:** `psycopg.errors.ActiveSqlTransaction: CREATE INDEX CONCURRENTLY cannot run inside a transaction block`

### Pitfall 5: `search_path` not set; queries find no tables
**What goes wrong:** After `CREATE SCHEMA infotriage`, if `search_path` is not set on the connection, queries like `SELECT * FROM articles` fail with "table not found". All queries must be fully-qualified (`infotriage.articles`) OR the search_path must include `infotriage`.
**Why it happens:** psycopg3 connects to the default search_path (`"$user", public`). The `infotriage` schema is not on this path by default.
**How to avoid:** Either (a) use fully-qualified table names everywhere (`infotriage.articles`) — preferred for clarity, or (b) run `SET search_path = infotriage, public` on each new connection. Option (a) is safer because it works regardless of connection state.
**Warning signs:** `psycopg.errors.UndefinedTable: relation "articles" does not exist` when using unqualified table names.

### Pitfall 6: `feedgen` `atom_str()` returns bytes, not str
**What goes wrong:** Treating `fg.atom_str(pretty=True)` as a string and trying to write it to a text-mode file with `f.write(result)` — raises `TypeError: write() argument must be str, not bytes`.
**Why it happens:** feedgen serializes to bytes (UTF-8 encoded XML). This is correct XML behavior.
**How to avoid:** Either open the output file in binary mode (`open(path, 'wb')`) or decode: `fg.atom_str(pretty=True).decode('utf-8')`.

### Pitfall 7: Blob shard depth is 2-level, not flat
**What goes wrong:** Building paths as `data/blobs/<hash>` (flat) instead of `data/blobs/<h[:2]>/<h[2:4]>/<h>` (2-level sharded). A flat store with thousands of files in one directory degrades filesystem performance.
**Why it happens:** Forgetting the sharding requirement.
**How to avoid:** Always use `_shard_path(root, h)` helper — `root / h[:2] / h[2:4] / h`.

---

## Code Examples

### psycopg3: JSONB upsert round-trip
```python
# Source: https://www.psycopg.org/psycopg3/docs/basic/adapt.html
from psycopg.types.json import Jsonb
with psycopg.connect(dsn, row_factory=dict_row) as conn:
    conn.execute(
        "INSERT INTO infotriage.articles (id, title, payload) VALUES (%s, %s, %s) "
        "ON CONFLICT (id) DO UPDATE SET payload = EXCLUDED.payload",
        ("abc123", "Test", Jsonb({"score": 9, "ccir": "PIR-1"}))
    )
    conn.commit()
    row = conn.execute(
        "SELECT payload FROM infotriage.articles WHERE id = %s", ("abc123",)
    ).fetchone()
    print(row["payload"])  # {"score": 9, "ccir": "PIR-1"}
```

### pgvector: cosine similarity threshold query
```python
# Source: https://github.com/pgvector/pgvector-python/blob/master/_autodocs/examples.md
import numpy as np
from pgvector.psycopg import register_vector

with psycopg.connect(dsn) as conn:
    register_vector(conn)
    q = np.array([0.1] * 1024, dtype=np.float32)   # query vector, dim must match schema
    rows = conn.execute(
        "SELECT id, name, 1-(embedding <=> %s) AS sim "
        "FROM infotriage.entities "
        "WHERE 1-(embedding <=> %s) >= 0.85 "
        "ORDER BY embedding <=> %s LIMIT 10",
        (q, q, q)
    ).fetchall()
    for row in rows:
        print(row)  # (id, name, similarity_float)
```

### pytest: parametrized contract test with db_live skip
```python
# Source: https://github.com/pytest-dev/pytest/blob/main/doc/en/how-to/skipping.rst
import socket, pytest

def _pg_reachable():
    try:
        with socket.create_connection(("localhost", 22000), timeout=1.0):
            return True
    except OSError:
        return False

db_live = pytest.mark.skipif(not _pg_reachable(), reason="Postgres :22000 unreachable")

@pytest.fixture(params=["inmemory", pytest.param("postgres", marks=db_live)])
def store(request, tmp_path):
    if request.param == "inmemory":
        return InMemoryStore(blob_root=tmp_path / "blobs")
    dsn = os.environ.get("INFOTRIAGE_PG_DSN", "...")
    with PostgresStore(dsn=dsn, blob_root=tmp_path / "blobs") as s:
        s.init_schema()
        yield s
```

### feedgen: Atom entry from Item
```python
# Source: https://github.com/lkiesow/python-feedgen/blob/main/readme.rst
from feedgen.feed import FeedGenerator
fg = FeedGenerator()
fg.id("http://localhost/infotriage/atom")
fg.title("InfoTriage")
fg.link(href="http://localhost/", rel="alternate")
fg.link(href="http://localhost/atom.xml", rel="self")
fg.language("no")

fe = fg.add_entry(order="append")
fe.id(item.url or f"infotriage:{item.id}")
fe.title(item.title)
if item.url:
    fe.link(href=item.url)
fe.published(item.ts)
fe.updated(item.ts)
if item.summary:
    fe.summary(item.summary)

xml_bytes = fg.atom_str(pretty=True)   # bytes; .decode('utf-8') for string
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| psycopg2 + psycopg2-binary | psycopg3 (package: `psycopg`) | psycopg 3.0 released 2021 | psycopg3 uses async-ready design, server-side binding, better type adapter API |
| IVFFlat index for pgvector | HNSW index | pgvector 0.5.0 (2023) | HNSW has no `lists` tuning, works on small corpora without minimum row count, better recall |
| feedgen 0.9.x legacy API | feedgen 1.0.0 | Dec 2023 | 1.0.0 is the current stable; no breaking changes to the `FeedGenerator`/`add_entry` API |

**Deprecated/outdated:**
- `psycopg2`: The old driver. Still works, but psycopg3 is the successor and required for the vector type adapter from `pgvector.psycopg`.
- `IVFFlat` pgvector index: Requires `VACUUM` before querying and a minimum number of rows. HNSW is simpler for incremental inserts and small corpora — exactly the Phase 2 use case.
- `feedgen.feed.Feed` (was a confusing alias in older versions): Use `FeedGenerator` directly.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `InMemoryStore` blob storage should write to a `tmp_path` directory (not keep bytes in memory) to test actual shard path logic | Architecture Patterns → Pattern 6 | If wrong: blob path acceptance criteria not tested; path regression sneaks through |
| A2 | `feedgen` `add_entry(order="append")` is the correct API for appending entries (vs `order="prepend"`) | Code Examples | Low risk — either ordering can be reversed in list_items call; cosmetic only |
| A3 | `numpy>=1.24` is the correct minimum version for pgvector 0.4.2 compatibility | Standard Stack | If wrong: install fails; fix: relax to numpy>=1.0 |
| A4 | `digest.py` `persist()` is the only persistence function to retrofit in `apps/triage/`; `triage_score.py` and `fever_triage.py` do not write to a store | Architecture Patterns (retrofit scope) | If wrong: retrofit is incomplete; fix: scan all write paths in both files |
| A5 | The `audit` table records store writes (not reads); `op` values are string literals like `'put_item'`, `'put_blob'` | Schema DDL Reference | Low risk — exact audit granularity is DD-5 (Claude's Discretion) |

**If this table is empty:** It is not empty. A1 is the most important assumption to verify before implementing InMemoryStore.

---

## Open Questions

1. **Where does the Atom projection function live?**
   - What we know: D-04 says "a writer behind the store interface"; it's a stateless function `render_atom(store) -> bytes`
   - What's unclear: Should it live in `libs/store/src/store/_atom.py` (closer to the store) or in `apps/` (closer to the ingest scripts that currently handle Atom)?
   - Recommendation: Put it in `libs/store/src/store/_atom.py` and export as `render_atom`. It depends only on `Store` (interface) and `feedgen` — both are `libs/store` dependencies. This keeps the projection bundled with the store package.

2. **Should `put_item` also write an audit record in the same transaction?**
   - What we know: DD-5 says audit table records write events; SPEC acceptance criteria don't specify exactly when audit rows appear
   - What's unclear: Same transaction (strong consistency) or best-effort (after commit)?
   - Recommendation: Same transaction for `put_item` (audit row and article row commit together). This satisfies the no-silent-data-loss prohibition because a failed audit write rolls back the article write too.

3. **`list_items` with `source_type_in` filter — SQL `IN` vs multiple `=` queries?**
   - What we know: Projection calls `list_items(source_type_in=["rss", "yt"])`
   - What's unclear: How to pass a variable-length `IN` clause safely in psycopg3
   - Recommendation: Use psycopg3's tuple parameter: `WHERE source_type = ANY(%s)` with `params=(["rss", "yt"],)` — this is the idiomatic psycopg3 way to pass a list to `ANY()`. [ASSUMED — based on psycopg3 docs pattern for array params]

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | All | ✓ | 3.13.5 | — |
| Docker | R8 docker-compose service | ✓ | 29.4.0 | — |
| `pgvector/pgvector:pg16` image | R8 postgres service | ✓ | cached locally | `docker pull pgvector/pgvector:pg16` |
| `postgres:16` image | R8 (alternative base) | ✓ | cached locally | — |
| psycopg3 (`psycopg`) | R5 PostgresStore | ✗ NOT INSTALLED | — | Add to `libs/store/pyproject.toml`; install via `pip install -e libs/store` |
| pgvector Python | R3 vector registration | ✓ | 0.4.2 | — |
| feedgen | R7 Atom projection | ✓ | 1.0.0 | — |
| numpy | R3 vector params | ✓ (via pgvector) | installed | — |
| pytest | R8 test framework | ✓ | 8.3.3 | — |
| Postgres :22000 | R8 live integration test | ✗ NOT RUNNING | — | `docker compose up postgres`; unit tests skip automatically |

**Missing dependencies with no fallback:**
- `psycopg` (psycopg3): must be installed before `PostgresStore` can be used. Wave 0 task: add to `libs/store/pyproject.toml` + `pip install -e libs/store`.

**Missing dependencies with fallback:**
- Postgres :22000: not running. Integration tests auto-skip via `db_live` marker. Unit tests on `InMemoryStore` always run.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.3.3 |
| Config file | `pyproject.toml` (`[tool.pytest.ini_options]`) |
| Quick run command | `pytest tests/ -x -q` |
| Full suite command | `pytest tests/ -v` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| R1 | `init_schema()` creates schema + tables on fresh DB; second call no-op | integration | `pytest tests/test_store_contract.py::test_init_schema_idempotent -m db_live` | ❌ Wave 0 |
| R2 | All 7 tables present after init | integration | `pytest tests/test_store_contract.py::test_all_tables_exist -m db_live` | ❌ Wave 0 |
| R3 | `<=>` cosine query returns neighbors; ≥0.85 links, <0.85 separates | integration | `pytest tests/test_store_contract.py::test_vector_cosine_threshold -m db_live` | ❌ Wave 0 |
| R4 | `put_blob(b)` then `get_blob(h)==b`; duplicate put one file; path is `ab/cd/<hash>` | unit | `pytest tests/test_store_blob.py -x` | ❌ Wave 0 |
| R4 | Partial-write failure leaves no file at final path | unit | `pytest tests/test_store_blob.py::test_atomic_write_failure` | ❌ Wave 0 |
| R5 | Both impls satisfy `Store` Protocol (`isinstance` check) | unit | `pytest tests/test_store_contract.py::test_protocol_satisfied` | ❌ Wave 0 |
| R5 | `put_item` twice → one row, latest content | unit+integration | `pytest tests/test_store_contract.py::test_put_item_upsert` | ❌ Wave 0 |
| R5 | `get_item("absent")` → `None`; empty list_items → `[]` | unit | `pytest tests/test_store_contract.py::test_get_miss_returns_none test_list_empty` | ❌ Wave 0 |
| R5 (must-NOT) | Failed persist raises; no silent no-op | unit | `pytest tests/test_store_contract.py::test_write_failure_raises` | ❌ Wave 0 |
| R5 (must-NOT) | InMemoryStore does not diverge (shared contract test) | unit | `pytest tests/test_store_contract.py -k "not db_live"` | ❌ Wave 0 |
| R6 | Retrofitted digest.py persists via store (row appears) | integration | `pytest tests/test_store_contract.py::test_digest_retrofit -m db_live` | ❌ Wave 0 |
| R7 | Atom projection emits valid Atom XML for known articles; RSS/YT only, email excluded | unit | `pytest tests/test_atom_projection.py` | ❌ Wave 0 |
| R8 | `pytest` passes with no DB (integration skipped) | unit | `pytest tests/ -x -q` (no DB needed) | ❌ Wave 0 |
| R8 | Integration test runs and passes with container up | integration | `pytest tests/ -x -v -m db_live` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/ -x -q` (all unit tests, integration auto-skipped if no DB)
- **Per wave merge:** `pytest tests/ -v` (full suite)
- **Phase gate:** 87 existing tests still green + all new Phase 2 tests green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_store_contract.py` — shared parametrized contract tests covering R1–R6, R8, must-NOTs
- [ ] `tests/test_store_blob.py` — blob store unit tests covering R4
- [ ] `tests/test_atom_projection.py` — Atom projection unit tests covering R7
- [ ] `libs/store/` package scaffolding — `pyproject.toml`, SQL files, `src/store/` modules
- [ ] `psycopg` install: add to `libs/store/pyproject.toml` + `requirements-dev.txt`; `pip install -e libs/store`
- [ ] `pyproject.toml` pytest marker registration: `db_live` marker to suppress warnings

---

## Security Domain

> `security_enforcement` is absent from `.planning/config.json`; treating as enabled.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | Single-user local; no auth at Phase 2 |
| V3 Session Management | No | Single-process, no sessions |
| V4 Access Control | No | Local-only deployment |
| V5 Input Validation | Yes | psycopg3 parameterized queries — ALL queries use `%s` params, never f-string or string concatenation; `Jsonb()` wrapper |
| V6 Cryptography | Partial | `hashlib.sha256` for blob addressing (non-secret use); NEVER store plaintext passwords or secrets in articles/audit/blobs |
| V7 Error Handling | Yes | Store must raise on failure (must-NOT prohibition); errors never silently swallowed |

### Known Threat Patterns for this Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection via dynamic table/column names | Tampering | All queries use psycopg3 `%s` params; no f-string SQL; DDL files have no user input |
| Blob path traversal (e.g. `hash = "../../etc/passwd"`) | Tampering | Validate that `blob_hash` is a 64-char hex string before constructing path: `re.fullmatch(r'[0-9a-f]{64}', blob_hash)` |
| Secrets in `Item.payload` persisted to JSONB | Information Disclosure | Out of scope for Phase 2 (GDPR review in `/gsd-secure-phase`); noted as breadcrumb in SPEC prohibitions |
| YAML deserialization (from `contracts._codec`) | Tampering | Already mitigated in Phase 1 — `yaml.safe_load` exclusively (T-01-01 from Phase 1 codec) |
| `defusedxml` for any XML sources | Tampering | Already mandated from spike (T-00-01-XXE) — ingest scripts use `defusedxml`; store itself does not parse XML |

---

## Sources

### Primary (MEDIUM confidence — Context7)
- `/websites/psycopg_psycopg3` — connection context manager, parameterized queries, Jsonb wrapper, autocommit, DDL patterns
- `/pgvector/pgvector-python` — `register_vector(conn)` psycopg3 usage, numpy array insert, cosine distance query
- `/pgvector/pgvector` — HNSW index creation with `vector_cosine_ops`, `<=>` operator semantics
- `/lkiesow/python-feedgen` — `FeedGenerator`, `add_entry`, `atom_str(pretty=True)`
- `/pytest-dev/pytest` — `skipif` marker, custom marker registration, parametrize with marks

### Secondary (codebase investigation)
- `libs/contracts/src/contracts/_bus.py` — BusClient Protocol pattern to mirror for Store Protocol
- `libs/contracts/src/contracts/_item.py` — canonical Item fields for articles table column mapping
- `apps/triage/digest.py` — `persist()` function (retrofit target); `STORE = "data/verdicts.jsonl"` to be replaced
- `.planning/phases/00-concept-spike/findings/R3-VERDICT.md` — entity schema (entities/entity_links + HNSW threshold 0.85) validated in spike

### Tertiary (environment verification)
- `pip3 index versions psycopg` → 3.3.4 confirmed on PyPI [VERIFIED: PyPI registry]
- `pip3 show pgvector` → 0.4.2 already installed [VERIFIED: local environment]
- `docker images` → `pgvector/pgvector:pg16` already cached locally [VERIFIED: local environment]
- `grep -c "^def test_"` across `tests/*.py` → 87 test functions [VERIFIED: codebase]

---

## Metadata

**Confidence breakdown:**
- Standard stack: MEDIUM — psycopg3 and pgvector-python confirmed via Context7 (High reputation sources); versions confirmed on PyPI
- Schema DDL: HIGH — schema spec is fully locked in CONTEXT.md + SPEC.md; entity schema validated in Phase 0 spike (R3-VERDICT.md)
- Architecture: HIGH — mirrors Phase 1 patterns directly; all design decisions locked in CONTEXT.md
- Pitfalls: MEDIUM — psycopg3/pgvector integration pitfalls from official docs; some from training knowledge

**Research date:** 2026-06-28
**Valid until:** 2026-07-28 (stable libs; psycopg3 patch releases do not break API)
