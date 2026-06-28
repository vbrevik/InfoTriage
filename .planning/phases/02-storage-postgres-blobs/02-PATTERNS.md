# Phase 2: Storage — Postgres + blobs — Pattern Map

**Mapped:** 2026-06-28
**Files analyzed:** 13 new/modified files
**Analogs found:** 13 / 13 (some partial/role-match)

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `libs/store/pyproject.toml` | config | — | `libs/contracts/pyproject.toml` | exact |
| `libs/store/src/store/__init__.py` | config | — | `libs/contracts/src/contracts/__init__.py` | exact |
| `libs/store/src/store/_protocol.py` | protocol/interface | request-response | `libs/contracts/src/contracts/_bus.py` (BusClient) | exact |
| `libs/store/src/store/_inmemory.py` | service/fake | CRUD | `libs/contracts/src/contracts/_bus.py` (InMemoryBus) | exact |
| `libs/store/src/store/_postgres.py` | service | CRUD | `libs/contracts/src/contracts/_bus.py` (InMemoryBus, context-manager shape) | role-match |
| `libs/store/src/store/_blob.py` | utility | file-I/O | `apps/ingest/_util.py` (helper pattern) | partial |
| `libs/store/src/store/_atom.py` | utility | transform | `apps/ingest/yt_to_atom.py` (Atom generation, feedgen) | role-match |
| `libs/store/sql/001-schema.sql` | config | — | none (new pattern) | no-analog |
| `libs/store/sql/002-articles.sql` | config | — | none (new pattern) | no-analog |
| `libs/store/sql/003-vectors.sql` | config | — | none (new pattern) | no-analog |
| `libs/store/sql/004-audit.sql` | config | — | none (new pattern) | no-analog |
| `libs/store/sql/005-stubs.sql` | config | — | none (new pattern) | no-analog |
| `docker-compose.yml` | config | — | existing `docker-compose.yml` (add service) | exact |
| `requirements-dev.txt` | config | — | existing `requirements-dev.txt` | exact |
| `tests/test_store_contract.py` | test | CRUD | Phase-1 test pattern (parametrized contract) | role-match |
| `tests/test_store_blob.py` | test | file-I/O | Phase-1 test pattern | role-match |
| `tests/test_atom_projection.py` | test | transform | Phase-1 test pattern | role-match |
| `apps/triage/digest.py` | script (retrofit) | CRUD | self (modify existing) | exact |

---

## Pattern Assignments

### `libs/store/pyproject.toml` (config)

**Analog:** `libs/contracts/pyproject.toml`

**Full structure to copy** (`libs/contracts/pyproject.toml` lines 1–16):
```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "store"
version = "0.1.0"
description = "InfoTriage persistence layer — Postgres + blob store"
requires-python = ">=3.11"
dependencies = [
    "contracts",              # editable, from libs/contracts
    "psycopg[binary]>=3.3",
    "pgvector>=0.4.2",
    "numpy>=1.24",
]

[tool.setuptools.packages.find]
where = ["src"]
```

**Also add to `requirements-dev.txt`** (mirror of line 1):
```
-e ./libs/store
```

**Add pytest marker to root `pyproject.toml`** (currently only has `[tool.pytest.ini_options]`):
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["apps/triage", "apps/opml", "apps/ingest"]
markers = [
    "db_live: requires Postgres :22000 to be running",
]
```

---

### `libs/store/src/store/__init__.py` (exports)

**Analog:** `libs/contracts/src/contracts/__init__.py` lines 12–27

**Pattern to copy:**
```python
# libs/contracts/src/contracts/__init__.py lines 12–15
from ._item import Item
from ._events import ItemIngested, VerdictReady, SabPublished, FeedUnhealthy
from ._codec import to_frontmatter, from_frontmatter
from ._bus import BusClient, InMemoryBus

__all__ = [
    "Item",
    ...
    "BusClient",
    "InMemoryBus",
]
```

**Adapted for store:**
```python
from ._protocol import Store
from ._postgres import PostgresStore
from ._inmemory import InMemoryStore
from ._atom import render_atom

__all__ = ["Store", "PostgresStore", "InMemoryStore", "render_atom"]
```

---

### `libs/store/src/store/_protocol.py` (Protocol, request-response)

**Analog:** `libs/contracts/src/contracts/_bus.py` lines 12–27 (BusClient Protocol)

**Protocol definition pattern** (`_bus.py` lines 12–27):
```python
# libs/contracts/src/contracts/_bus.py:12-14
from typing import Protocol, runtime_checkable

# _bus.py:16-27
@runtime_checkable
class BusClient(Protocol):
    """Transport-swappable bus interface. In-memory now; AMQP (Phase 3) later.

    Any class with matching publish/subscribe signatures satisfies this Protocol
    without explicit inheritance (PEP 544 structural subtyping).
    """

    def publish(self, routing_key: str, item_id: str, payload: dict) -> None:
        """Publish payload to routing_key. Idempotent..."""
        ...

    def subscribe(self, routing_key: str) -> list[dict]:
        """Return all payloads for routing_key in FIFO order. Returns [] if queue is empty."""
        ...
```

**Adapted for Store Protocol** — same `@runtime_checkable` decorator, same docstring style, same `...` body stubs:
```python
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
    def init_schema(self) -> None: ...
    def put_item(self, item: Item) -> None: ...
    def get_item(self, item_id: str) -> Item | None: ...
    def list_items(
        self,
        source_type_in: list[str] | None = None,
        limit: int = 200,
    ) -> list[Item]: ...
    def put_blob(self, data: bytes) -> str: ...
    def get_blob(self, blob_hash: str) -> bytes: ...
```

---

### `libs/store/src/store/_inmemory.py` (fake/CRUD)

**Analog:** `libs/contracts/src/contracts/_bus.py` lines 45–66 (InMemoryBus)

**InMemoryBus full implementation** (`_bus.py` lines 45–66):
```python
class InMemoryBus:
    def __init__(self) -> None:
        self._queues: dict[str, list[dict]] = {}
        self._seen: set[tuple[str, str]] = set()

    def publish(self, routing_key: str, item_id: str, payload: dict) -> None:
        key = (routing_key, item_id)
        if key in self._seen:
            return                                # dedup: same (routing_key, item_id) → no-op
        self._seen.add(key)
        self._queues.setdefault(routing_key, []).append(payload)

    def subscribe(self, routing_key: str) -> list[dict]:
        return list(self._queues.get(routing_key, []))  # empty queue → [] (no-op)
```

**Key patterns to copy:**
- `__init__` sets up plain dict/set storage — no external deps
- No thread-safety (Phase 1 note mirrors Phase 2: single-process scope)
- Empty-collection return for miss (`[]`, `None`) — exact semantics to replicate
- Dedup via set key — InMemoryStore replicates with `self._items: dict[str, Item] = {}`

**Adapted shape for InMemoryStore:**
```python
class InMemoryStore:
    """Dict-backed fake for unit tests. Must not diverge from PostgresStore contract."""

    def __init__(self, blob_root: Path) -> None:
        self._items: dict[str, Item] = {}
        self._blob_root = blob_root  # writes blobs to disk (not memory) to test shard paths

    def __enter__(self) -> "InMemoryStore":
        return self

    def __exit__(self, *args) -> None:
        pass  # no connection to close

    def init_schema(self) -> None:
        pass  # no-op for fake; blob_root mkdir on first put_blob

    def put_item(self, item: Item) -> None:
        self._items[item.id] = item  # last-write-wins upsert

    def get_item(self, item_id: str) -> Item | None:
        return self._items.get(item_id)  # None on miss

    def list_items(
        self, source_type_in: list[str] | None = None, limit: int = 200
    ) -> list[Item]:
        items = list(self._items.values())
        if source_type_in is not None:
            items = [i for i in items if i.source_type in source_type_in]
        items.sort(key=lambda i: (i.ts, i.id), reverse=True)
        return items[:limit]
    # put_blob / get_blob delegate to _blob helpers (same as PostgresStore)
```

---

### `libs/store/src/store/_postgres.py` (service/CRUD)

**Analog:** `libs/contracts/src/contracts/_bus.py` (InMemoryBus shape); no direct Postgres analog exists — this is the first DB-backed class in the repo.

**Context manager shape** — mirror InMemoryBus `__init__`, but with psycopg3:
```python
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pgvector.psycopg import register_vector   # NOT pgvector.psycopg2
from pathlib import Path
from contracts import Item

class PostgresStore:
    def __init__(self, dsn: str, blob_root: Path) -> None:
        self._dsn = dsn
        self._blob_root = blob_root
        self._conn: psycopg.Connection | None = None

    def __enter__(self) -> "PostgresStore":
        self._conn = psycopg.connect(self._dsn, row_factory=dict_row)
        register_vector(self._conn)   # MUST be called before any vector query
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

**init_schema — autocommit DDL connection:**
```python
def init_schema(self) -> None:
    sql_dir = Path(__file__).parent.parent.parent / "sql"
    with psycopg.connect(self._dsn, autocommit=True) as ddl_conn:
        register_vector(ddl_conn)
        for sql_file in sorted(sql_dir.glob("*.sql")):
            ddl_conn.execute(sql_file.read_text())
```

**put_item — upsert with Jsonb wrapper (CRITICAL):**
```python
def put_item(self, item: Item) -> None:
    assert self._conn is not None, "Use PostgresStore as context manager"
    self._conn.execute("""
        INSERT INTO infotriage.articles
            (id, source, source_type, url, title, ts, lang, summary, body_ref, payload)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE SET
            source = EXCLUDED.source, source_type = EXCLUDED.source_type,
            url = EXCLUDED.url, title = EXCLUDED.title, ts = EXCLUDED.ts,
            lang = EXCLUDED.lang, summary = EXCLUDED.summary,
            body_ref = EXCLUDED.body_ref, payload = EXCLUDED.payload
    """, (
        item.id, item.source, item.source_type, item.url, item.title,
        item.ts, item.lang, item.summary, item.body_ref,
        Jsonb(item.payload)   # dict → Jsonb() wrapper is REQUIRED; plain dict fails
    ))
    self._conn.commit()
```

**Critical pitfalls to avoid (from RESEARCH.md):**
- Import `from pgvector.psycopg import register_vector` — NOT `pgvector.psycopg2`
- Always wrap JSONB params: `Jsonb(item.payload)` — never pass raw dict
- Use fully-qualified table names `infotriage.articles` — don't rely on search_path
- `CREATE INDEX ... USING hnsw` (no `CONCURRENTLY`) — concurrent index creation fails inside a transaction
- `list_items` with source_type filter: use `WHERE source_type = ANY(%s)` with list param

---

### `libs/store/src/store/_blob.py` (utility, file-I/O)

**Analog:** `apps/ingest/_util.py` (None-safe escape helper pattern — single-concern utility with defensive error handling)

**_util.py pattern** (`_util.py` lines 1–36):
```python
# Single concern, stdlib-only, None-safe, fail-loud on bad input
from html import escape as _html_escape

def escape(s):
    if s is None:
        return ""
    if not isinstance(s, str):
        raise TypeError(...)
    return _html_escape(s, quote=True)
```

**Adapted blob helper** — same single-concern utility shape, stdlib-only, fail-loud:
```python
import hashlib, os, re
from pathlib import Path

def _shard_path(root: Path, h: str) -> Path:
    return root / h[:2] / h[2:4] / h

def _validate_hash(blob_hash: str) -> None:
    if not re.fullmatch(r'[0-9a-f]{64}', blob_hash):
        raise ValueError(f"Invalid blob hash: {blob_hash!r}")

def put_blob(root: Path, data: bytes) -> str:
    h = hashlib.sha256(data).hexdigest()
    dest = _shard_path(root, h)
    if dest.exists():
        return h              # dedup no-op
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp")
    try:
        tmp.write_bytes(data)
        os.replace(str(tmp), str(dest))  # atomic POSIX rename
    except Exception:
        tmp.unlink(missing_ok=True)      # never leave partial write
        raise                            # fail loud (must-NOT: no silent data loss)
    return h

def get_blob(root: Path, blob_hash: str) -> bytes:
    _validate_hash(blob_hash)            # path traversal guard
    return _shard_path(root, blob_hash).read_bytes()
    # FileNotFoundError on miss — caller handles
```

---

### `libs/store/src/store/_atom.py` (utility, transform)

**Analog:** `apps/ingest/yt_to_atom.py` (Atom generation via string manipulation — this is the feedgen-free reference; the new writer upgrades to feedgen). Also references `apps/ingest/_util.py` escape pattern.

**yt_to_atom.py uses manual XML string construction** — the new `_atom.py` replaces this with feedgen (already in `requirements.txt`). Key structural similarity: pure function, takes a data source, returns Atom XML.

**feedgen pattern from RESEARCH.md** (already verified against feedgen 1.0.0):
```python
from feedgen.feed import FeedGenerator
import datetime
from store._protocol import Store

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

    return fg.atom_str(pretty=True)  # returns bytes; decode('utf-8') for string
```

---

### `docker-compose.yml` (config — add service)

**Analog:** existing `docker-compose.yml` lines 1–47

**Service block pattern** (from existing `freshrss` service, lines 4–18 — copy structure):
```yaml
services:
  freshrss:
    image: freshrss/freshrss:latest
    container_name: infotriage-freshrss
    restart: unless-stopped
    ports:
      - "8088:80"
    environment:
      TZ: Europe/Oslo
    volumes:
      - ./data/freshrss:/var/www/FreshRSS/data
    networks: [infotriage]
```

**New postgres service** follows the same shape; append after `feeds:`:
```yaml
  postgres:
    image: pgvector/pgvector:pg16
    container_name: infotriage-postgres
    restart: unless-stopped
    ports:
      - "22000:5432"
    environment:
      POSTGRES_DB: infotriage
      POSTGRES_USER: infotriage
      POSTGRES_PASSWORD: infotriage_dev    # dev-only; loaded via .env in production
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    networks: [infotriage]
```

---

### `apps/triage/digest.py` (retrofit — modify existing)

**Analog:** self (the existing file)

**Current persist() function** (`digest.py` lines 139–142):
```python
def persist(verdicts):
    os.makedirs(os.path.dirname(STORE), exist_ok=True)
    with open(STORE, "a") as f:
        for v in verdicts:
            f.write(json.dumps(v) + "\n")
```

**Current import context** (`digest.py` lines 1–36 — key lines):
```python
from contracts import Item  # already imports contracts (D-08 wiring)
STORE = os.path.join(ROOT, "data", "verdicts.jsonl")  # this variable is removed
```

**Retrofit target:** Replace `persist(verdicts)` with `store.put_item(item)` calls. The `STORE` path variable goes away. `INFOTRIAGE_PG_DSN` is read from env and a `PostgresStore` is constructed in `main()` as a context manager (D-03 pattern).

**Construction pattern** (from RESEARCH.md D-03, mirror of InMemoryBus `__init__` in `_bus.py`):
```python
import os
from pathlib import Path
from store import PostgresStore

def main():
    dsn = os.environ["INFOTRIAGE_PG_DSN"]
    blob_root = Path("data/blobs")
    with PostgresStore(dsn=dsn, blob_root=blob_root) as store:
        store.init_schema()
        # ... existing logic, calling store.put_item(item) instead of persist()
```

---

### `tests/test_store_contract.py` (test, CRUD)

**Analog:** Phase-1 test pattern (no direct test analog in codebase — Phase-1 tests cover contracts). The parametrized fixture pattern is from RESEARCH.md Pattern 9.

**Shared parametrized fixture pattern:**
```python
import socket, os, pytest
from store import PostgresStore, InMemoryStore
from pathlib import Path

def _pg_reachable() -> bool:
    try:
        with socket.create_connection(("localhost", 22000), timeout=1.0):
            return True
    except OSError:
        return False

db_live = pytest.mark.skipif(
    not _pg_reachable(),
    reason="Postgres :22000 unreachable — integration test skipped"
)

@pytest.fixture(params=[
    "inmemory",
    pytest.param("postgres", marks=db_live),
])
def store(request, tmp_path):
    if request.param == "inmemory":
        yield InMemoryStore(blob_root=tmp_path / "blobs")
    else:
        dsn = os.environ.get(
            "INFOTRIAGE_PG_DSN",
            "postgresql://infotriage:infotriage_dev@localhost:22000/infotriage"
        )
        with PostgresStore(dsn=dsn, blob_root=tmp_path / "blobs") as s:
            s.init_schema()
            yield s
```

---

### `tests/test_store_blob.py` and `tests/test_atom_projection.py`

**Analog:** Same Phase-1 test structure (plain pytest, no special fixtures other than `tmp_path`).

**Key test shape** — use `tmp_path` for blob root (builtin pytest fixture):
```python
from store._blob import put_blob, get_blob
from pathlib import Path

def test_put_get_roundtrip(tmp_path):
    data = b"hello world"
    h = put_blob(tmp_path, data)
    assert get_blob(tmp_path, h) == data

def test_shard_path(tmp_path):
    data = b"x"
    h = put_blob(tmp_path, data)
    expected = tmp_path / h[:2] / h[2:4] / h
    assert expected.exists()
```

---

## Shared Patterns

### Context-manager resource lifetime
**Source:** `libs/contracts/src/contracts/_bus.py` (InMemoryBus `__init__` / field initialization)
**Apply to:** `PostgresStore.__init__`, `InMemoryStore.__init__`
- Fields initialized in `__init__`; actual resource (connection) opened in `__enter__`
- `__exit__` commits on success, rolls back on exception, always closes

### Protocol + runtime_checkable
**Source:** `libs/contracts/src/contracts/_bus.py` lines 12–27
**Apply to:** `_protocol.py` Store definition
```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class BusClient(Protocol):
    ...
```
Use `isinstance(store, Store)` (not `isinstance(store, PostgresStore)`) everywhere in test assertions and typing.

### Package structure: `src/` layout + `pyproject.toml`
**Source:** `libs/contracts/pyproject.toml` lines 14–16
```toml
[tool.setuptools.packages.find]
where = ["src"]
```
Apply to `libs/store/pyproject.toml` identically.

### Fail-loud, no silent swallowing
**Source:** `apps/ingest/_util.py` (raises `TypeError` on bad input rather than coercing)
**Apply to:** `_blob.py` `put_blob` (re-raises after cleanup), `_blob.py` `get_blob` (lets `FileNotFoundError` propagate), `PostgresStore.put_item` (lets `psycopg.Error` propagate — must-NOT prohibition)

### Env var for secrets, never baked in
**Source:** `apps/triage/digest.py` (Phase-1 D-02: `.env` at runtime, never in package)
**Apply to:** `PostgresStore` construction — read `INFOTRIAGE_PG_DSN` in caller (`main()` or test fixture), never inside the class itself.

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `libs/store/sql/*.sql` | config | — | No SQL files exist in the repo; plain-SQL DDL is new; use RESEARCH.md Schema DDL Reference section verbatim |

---

## Metadata

**Analog search scope:** `libs/contracts/`, `apps/triage/`, `apps/ingest/`, root config files
**Files scanned:** 12 source files + 3 config files
**Pattern extraction date:** 2026-06-28
