# Phase 05: triage-app — Pattern Map

**Mapped:** 2026-06-29
**Files analyzed:** 14 new/modified files
**Analogs found:** 12 / 14

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `apps/triage/worker.py` | service | event-driven | `libs/contracts/src/contracts/_bus_rabbitmq.py` (consumer side) | role-match |
| `apps/triage/triage_score.py` | utility | transform | self (targeted one-line fix only) | self |
| `apps/triage/Dockerfile` | config | — | `apps/ingest-imap/Dockerfile` | exact |
| `apps/triage/requirements.txt` | config | — | `apps/ingest-imap/requirements.txt` | exact |
| `libs/store/sql/006-enrichment.sql` | migration | — | `libs/store/sql/005-stubs.sql` + `003-vectors.sql` | role-match |
| `libs/store/src/store/_protocol.py` | protocol | CRUD | self (extension — add 4 method stubs) | self |
| `libs/store/src/store/_postgres.py` | service | CRUD | self (extension — `put_item` / `get_item` pattern) | self |
| `libs/store/src/store/_inmemory.py` | service | CRUD | self (extension — `put_item` / `get_item` pattern) | self |
| `libs/contracts/src/contracts/_bus_rabbitmq.py` | service | event-driven | self (add `consume()` alongside `subscribe()`) | self |
| `scripts/shadow_run.py` | utility | batch | `libs/store/src/store/_postgres.py` (direct psycopg3 read) | partial |
| `docker-compose.yml` | config | — | self (add triage stanza after `ingest-imap` block) | self |
| `tests/test_triage_enrichment.py` | test | CRUD | `tests/test_store_contract.py` | exact |
| `tests/test_triage_worker.py` | test | event-driven | `tests/test_store_contract.py` + `tests/test_score_parse.py` | role-match |
| `tests/test_triage_health.py` | test | request-response | no existing analog | none |

---

## Pattern Assignments

### `apps/triage/worker.py` (service, event-driven)

**Analog:** `libs/contracts/src/contracts/_bus_rabbitmq.py` (consumer internals) + `apps/triage/triage_score.py` (`llm()` for HTTP call pattern)

**Imports pattern** — mirror triage_score.py:
```python
# triage_score.py lines 14-15
import json, os, sys, argparse, urllib.request, urllib.error
```
worker.py imports:
```python
import asyncio, json, os, logging
import urllib.request
from contracts._bus_rabbitmq import RabbitMQBus
from contracts._events import ItemIngested, VerdictReady
from store._postgres import PostgresStore
from triage_score import score_item
```

**oMLX embedding call pattern** — mirror `llm()` exactly (`triage_score.py` lines 42–56):
```python
def llm(messages, max_tokens=400):
    base = os.environ.get("LLM_BASE_URL", "http://127.0.0.1:8000/v1")
    key = os.environ.get("LLM_API_KEY", "omlx")
    model = os.environ.get("LLM_MODEL", "qwen36-ud-4bit")
    body = json.dumps({
        "model": model, "messages": messages,
        "temperature": 0, "max_tokens": max_tokens,
    }).encode()
    req = urllib.request.Request(
        base.rstrip("/") + "/chat/completions", data=body,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)["choices"][0]["message"]["content"]
```
`get_embedding()` replaces `/chat/completions` with `/embeddings`, model with `intfloat/multilingual-e5-large`, and body structure with `{"model": ..., "input": text}`. Return `json.load(r)["data"][0]["embedding"]`.

**aio-pika consumer setup** — from `_bus_rabbitmq.py` `_ensure_connection` (lines 84–107):
```python
async def _ensure_connection(self) -> None:
    if self._connection and not self._connection.is_closed:
        return
    ...
    self._connection = await aio_pika.connect_robust(self.amqp_url)
    self._channel = await self._connection.channel(publisher_confirms=True)
    await self._channel.set_qos(prefetch_count=10)
    await self._declare_topology()
```
`run_consumer()` calls `await bus._ensure_connection()` then `await bus.consume("item.ingested", on_message, prefetch_count=1)`.

**asyncio gather pattern** (D-03):
```python
async def main() -> None:
    asyncio.gather(run_consumer(), run_health_server())

asyncio.run(main())
```

**Field mapping before VerdictReady** (from CONTEXT.md code_context):
```python
# triage_score returns: cnr "none"|"I"|"II", bucket "read"|"maybe"|"skip"
# VerdictReady expects:  cnr "Routine"|"I"|"II", bucket "keep"|"maybe"|"skip"
def map_cnr(cnr: str) -> str:
    return "Routine" if cnr == "none" else cnr

def map_bucket(bucket: str) -> str:
    return "keep" if bucket == "read" else bucket
```

**Health server pattern** (D-04):
```python
async def run_health_server(host: str = "0.0.0.0", port: int = 22030) -> None:
    async def handle(reader, writer) -> None:
        await reader.read(1024)
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK")
        await writer.drain()
        writer.close()
    server = await asyncio.start_server(handle, host, port)
    async with server:
        await server.serve_forever()
```

---

### `apps/triage/triage_score.py` (utility, transform — targeted fix only)

**Change:** Remove module-level `CCIR = load_ccir()` (line ~42). Add `ccir = load_ccir()` as first line inside `score_item()`. Update f-string reference from `{CCIR}` to `{ccir}` (lowercase). Interface unchanged.

**Current score_item() signature** (`triage_score.py` lines 58–72):
```python
def score_item(it):
    prompt = f"""...
{CCIR}
...
```
After fix, `CCIR` in f-string becomes `ccir` (the local variable set by `ccir = load_ccir()` at top of function body).

---

### `apps/triage/Dockerfile` (config)

**Analog:** `apps/ingest-imap/Dockerfile` (lines 1–22) — exact pattern:
```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY libs/contracts /build/contracts
COPY libs/store /build/store
RUN pip install --no-deps /build/contracts /build/store

COPY apps/triage/requirements.txt .
RUN pip install -r requirements.txt

COPY apps/triage/ .

# Secrets arrive at runtime via env_file (.env) only — no credential ARG/ENV (NF-6)
CMD ["python", "worker.py"]
```
Differences from ingest-imap: no `ingest_common` lib; CMD is `python worker.py` (not uvicorn); port is 22030.

---

### `apps/triage/requirements.txt` (config)

**Analog:** `apps/ingest-imap/requirements.txt` pattern. Content:
```
aio-pika
psycopg[binary]
pgvector
```
No new packages (per RESEARCH.md — Phase 5 adds zero new PyPI deps).

---

### `libs/store/sql/006-enrichment.sql` (migration)

**Analog:** `libs/store/sql/005-stubs.sql` (ADD COLUMN IF NOT EXISTS idempotent pattern).

**005-stubs.sql** — current enrichment stub (lines 6–12):
```sql
CREATE TABLE IF NOT EXISTS infotriage.enrichment (
    id          SERIAL      PRIMARY KEY,
    item_id     TEXT        NOT NULL REFERENCES infotriage.articles(id),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```
No UNIQUE constraint on `item_id`. **006-enrichment.sql must add the constraint before the columns** (needed for ON CONFLICT DO UPDATE):
```sql
ALTER TABLE infotriage.enrichment
    ADD CONSTRAINT IF NOT EXISTS enrichment_item_id_unique UNIQUE (item_id);

ALTER TABLE infotriage.enrichment ADD COLUMN IF NOT EXISTS ccir   TEXT;
ALTER TABLE infotriage.enrichment ADD COLUMN IF NOT EXISTS cnr    TEXT;
ALTER TABLE infotriage.enrichment ADD COLUMN IF NOT EXISTS score  INT CHECK (score BETWEEN 0 AND 10);
ALTER TABLE infotriage.enrichment ADD COLUMN IF NOT EXISTS bucket TEXT;
ALTER TABLE infotriage.enrichment ADD COLUMN IF NOT EXISTS why    TEXT;
ALTER TABLE infotriage.enrichment ADD COLUMN IF NOT EXISTS pmesii TEXT;
ALTER TABLE infotriage.enrichment ADD COLUMN IF NOT EXISTS tessoc TEXT;
```

**Note on embeddings table** (`003-vectors.sql` lines 27–32): `infotriage.embeddings` has no UNIQUE constraint on `item_id` — only SERIAL PK. `put_embedding` upsert (D-05) requires one. Either add to 006-enrichment.sql or a separate sub-migration:
```sql
ALTER TABLE infotriage.embeddings
    ADD CONSTRAINT IF NOT EXISTS embeddings_item_id_unique UNIQUE (item_id);
```

---

### `libs/store/src/store/_protocol.py` (protocol — extension)

**Analog:** self — follow the existing `put_item` / `get_item` stub pattern. Add after existing methods:
```python
from typing import Optional

# Add to Store Protocol:
def put_enrichment(self, item_id: str, fields: dict) -> None:
    """Upsert enrichment row. ON CONFLICT DO UPDATE all 7 fields."""
    ...

def get_enrichment(self, item_id: str) -> Optional[dict]:
    """Return enrichment dict or None if absent."""
    ...

def put_embedding(self, item_id: str, vector: list[float]) -> None:
    """Upsert embedding row to infotriage.embeddings."""
    ...

def find_near_duplicate(
    self, vector: list[float], window_days: int = 7, threshold: float = 0.84
) -> Optional[str]:
    """Return item_id of nearest duplicate within window+threshold, or None."""
    ...
```

---

### `libs/store/src/store/_postgres.py` (service, CRUD — extension)

**Analog:** self — `put_item` / `get_item` (lines 118–176) are the direct copy template.

**put_item upsert pattern** (`_postgres.py` lines 118–151):
```python
def put_item(self, item: Item) -> None:
    assert self._conn is not None, "PostgresStore must be used as a context manager: ..."
    self._conn.execute(
        """
        INSERT INTO infotriage.articles (id, source, ...)
        VALUES (%s, %s, ...)
        ON CONFLICT (id) DO UPDATE SET
            source = EXCLUDED.source,
            ...
        """,
        (item.id, item.source, ...),
    )
```
Copy this structure for `put_enrichment(item_id, fields)` and `put_embedding(item_id, vector)`. No `Jsonb()` wrapper needed (all enrichment fields are TEXT/INT, not JSONB).

**get_item pattern** (`_postgres.py` lines 161–176) — copy for `get_enrichment`:
```python
row = self._conn.execute(
    "SELECT ccir, cnr, score, bucket, why, pmesii, tessoc FROM infotriage.enrichment WHERE item_id = %s",
    (item_id,),
).fetchone()
if row is None:
    return None
return dict(row)
```

**register_vector() call** (`_postgres.py` line 91 in `__enter__`, line 115 in `init_schema`):
```python
def __enter__(self) -> "PostgresStore":
    self._conn = psycopg.connect(self._dsn, row_factory=dict_row)
    register_vector(self._conn)  # MUST be called before any vector query
    return self
```
`find_near_duplicate` can use `<=>` operator immediately because `register_vector` already ran in `__enter__`.

**find_near_duplicate SQL** (cosine distance — `<=>` not `<->`):
```python
def find_near_duplicate(self, vector, window_days=7, threshold=0.84):
    sql = """
        SELECT item_id, embedding <=> %s::vector AS dist
        FROM infotriage.embeddings
        WHERE created_at >= NOW() - INTERVAL %s
        ORDER BY embedding <=> %s::vector
        LIMIT 1
    """
    row = self._conn.execute(sql, (vector, f"{window_days} days", vector)).fetchone()
    if row and row["dist"] < (1.0 - threshold):
        return row["item_id"]
    return None
```

---

### `libs/store/src/store/_inmemory.py` (service, CRUD — extension)

**Analog:** self — storage dict pattern (class defined at line 24, `_items: dict[str, Item]` at line 38).

**put_item pattern** (line 49–51):
```python
def put_item(self, item: Item) -> None:
    self._items[item.id] = item
```

**get_item pattern** (line 53–56):
```python
def get_item(self, item_id: str) -> Item | None:
    return self._items.get(item_id)
```

New storage dicts follow the same pattern:
```python
self._enrichments: dict[str, dict] = {}
self._embeddings: dict[str, list[float]] = {}   # item_id → vector
```

**find_near_duplicate cosine loop** (D-07 — stdlib only, math.sqrt):
```python
import math

def _cosine_sim(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    return dot / (mag_a * mag_b) if mag_a and mag_b else 0.0

def find_near_duplicate(self, vector, window_days=7, threshold=0.84):
    # InMemoryStore ignores window_days (no timestamps tracked for test simplicity)
    best_id, best_sim = None, 0.0
    for item_id, stored_vec in self._embeddings.items():
        sim = _cosine_sim(vector, stored_vec)
        if sim > best_sim:
            best_sim, best_id = sim, item_id
    return best_id if best_sim >= threshold else None
```

---

### `libs/contracts/src/contracts/_bus_rabbitmq.py` (service, event-driven — extension)

**Analog:** self — add `consume()` alongside `subscribe()` (line 145). Does NOT modify the `BusClient` Protocol.

**subscribe() full text for reference** (lines 145–165) — drain-only, not suitable for persistent consumer:
```python
async def subscribe(self, routing_key: str, ...) -> list[dict]:
    # Creates consumer, sleeps 0.5s, cancels — test-drain only
    ...
```

**New `consume()` method pattern** — add after `subscribe()`:
```python
async def consume(
    self,
    routing_key: str,
    handler,
    prefetch_count: int = 1,
) -> None:
    """Register a persistent consumer callback. Runs until connection closed.

    handler(message: AbstractIncomingMessage) -> Awaitable[None]
    Use: async with message.process(): ... inside handler for auto-ack.
    """
    await self._ensure_connection()
    queue_name = self._ROUTING_KEY_TO_QUEUE.get(routing_key, routing_key)
    if queue_name not in self._queues:
        raise ValueError(f"Queue for routing key {routing_key!r} not declared")
    queue = self._queues[queue_name]
    await self._channel.set_qos(prefetch_count=prefetch_count)
    await queue.consume(handler)
    # Caller is responsible for keeping the event loop alive (asyncio.Future() / gather)
```
`_ROUTING_KEY_TO_QUEUE` mapping is already used in `subscribe()` — reuse the same dict lookup.

**__init__ reference** (lines 72–82) — `_queues` dict is populated by `_declare_topology()`:
```python
self._queues: dict[str, aio_pika.RobustQueue] = {}   # routing_key → queue
```

---

### `scripts/shadow_run.py` (utility, batch)

**Analog:** `libs/store/src/store/_postgres.py` for direct psycopg3 read pattern. No exact analog — closest is test fixtures using DEV_DSN.

**psycopg3 direct read pattern** (from `test_store_integration.py` lines 40–41, 89–95):
```python
DEV_DSN = "postgresql://infotriage:infotriage_dev@localhost:22000/infotriage"

import psycopg
from psycopg.rows import dict_row

with psycopg.connect(DEV_DSN, row_factory=dict_row) as conn:
    rows = conn.execute(
        """
        SELECT e.item_id, a.title, e.bucket
        FROM infotriage.enrichment e
        JOIN infotriage.articles a ON a.id = e.item_id
        WHERE e.bucket IS NOT NULL
        LIMIT 100
        """,
    ).fetchall()
```
Then re-run `score_item({"title": row["title"], "summary": row.get("summary",""), "source": ""})` and compare buckets.

**Output format** (from CONTEXT.md specifics): tabulated with columns `item_id (short)`, `title (truncated)`, `enrichment_bucket`, `rescore_bucket`, `match`. Use `print(f"{item_id[:8]:<10} {title[:40]:<42} {stored:<8} {rescore:<8} {'OK' if match else 'MISMATCH'}")`.

---

### `docker-compose.yml` (config — add triage stanza)

**Analog:** self — copy `ingest-imap` service block (lines 120–140), change service name, port, dockerfile, and remove unneeded volumes if triage doesn't need blob storage.

**ingest-imap block** (lines 120–140):
```yaml
  ingest-imap:
    build:
      context: .
      dockerfile: apps/ingest-imap/Dockerfile
    container_name: infotriage-ingest-imap
    restart: unless-stopped
    ports:
      - "127.0.0.1:22010:8000"
    env_file:
      - path: .env
        required: false
    environment:
      INFOTRIAGE_PG_DSN: ${INFOTRIAGE_PG_DSN:-postgresql://infotriage:infotriage_dev@postgres:5432/infotriage}
      INFOTRIAGE_AMQP_DSN: ${INFOTRIAGE_AMQP_DSN:-amqp://infotriage:infotriage_rmq@rabbitmq:5672}
      INFOTRIAGE_BLOB_ROOT: /data/blobs
    volumes:
      - ./data:/data
    depends_on:
      postgres:
        condition: service_healthy
      rabbitmq:
        condition: service_healthy
    networks: [infotriage]
```
Triage stanza changes: `22030:22030` (health port maps 1:1), dockerfile `apps/triage/Dockerfile`, add `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` env vars, remove `INFOTRIAGE_BLOB_ROOT` if triage writes no blobs.

---

### `tests/test_triage_enrichment.py` (test, CRUD)

**Analog:** `tests/test_store_contract.py` — parametrized `inmemory` + `postgres` fixture pattern.

**Parametrize fixture** (`test_store_contract.py` lines 68–81):
```python
@pytest.fixture(
    params=[
        "inmemory",
        pytest.param("postgres", marks=db_live),
    ]
)
def store(request, tmp_path):
    if request.param == "inmemory":
        yield InMemoryStore(blob_root=tmp_path / "blobs")
    else:
        dsn = _get_dsn()
        _truncate_all(dsn)
        with PostgresStore(dsn=dsn, blob_root=tmp_path / "blobs") as s:
            s.init_schema()
            yield s
```
Copy this pattern for `test_triage_enrichment.py`. Tests: `test_put_get_enrichment`, `test_put_enrichment_idempotent`, `test_find_near_duplicate`.

---

### `tests/test_triage_worker.py` (test, event-driven)

**Analog:** `tests/test_store_contract.py` (InMemoryStore fixture) + `tests/test_score_parse.py` (score_item call pattern).

Use `InMemoryStore` for all worker tests — no live Postgres needed. Mock `RabbitMQBus` or use `InMemoryBus` from contracts if available. Test structure:
```python
import pytest
from store._inmemory import InMemoryStore
from triage_score import score_item

@pytest.fixture
def store(tmp_path):
    return InMemoryStore(blob_root=tmp_path / "blobs")
```

---

### `tests/test_triage_health.py` (test, request-response)

**No analog found.** Use stdlib `asyncio` test approach:
```python
import asyncio, pytest

@pytest.mark.asyncio
async def test_health_200():
    # start server, open connection, send minimal HTTP GET, assert 200 in response
    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(b"GET /health HTTP/1.0\r\n\r\n")
    data = await reader.read(100)
    assert b"200" in data
    writer.close()
    server.close()
```

---

## Shared Patterns

### psycopg3 bind params — ALL SQL
**Source:** `libs/store/src/store/_postgres.py` (V5/T-02-01 comment in source)
**Apply to:** `_postgres.py` (new methods), `scripts/shadow_run.py`, `006-enrichment.sql`

Rule: Always `%s` placeholders. Never f-strings or string concatenation in SQL strings.

### register_vector() — vector queries
**Source:** `libs/store/src/store/_postgres.py` line 91 (`__enter__`) and line 115 (`init_schema`)
**Apply to:** `PostgresStore.find_near_duplicate()` — safe to call because `__enter__` already called `register_vector(self._conn)`.

### Context manager usage
**Source:** `libs/store/src/store/_postgres.py` lines 88–103
```python
def __enter__(self) -> "PostgresStore":
    self._conn = psycopg.connect(self._dsn, row_factory=dict_row)
    register_vector(self._conn)
    return self

def __exit__(self, exc_type, exc_val, exc_tb) -> None:
    if self._conn is not None:
        if exc_type is None:
            self._conn.commit()
        else:
            self._conn.rollback()
        self._conn.close()
        self._conn = None
```
**Apply to:** `worker.py` must open `PostgresStore` as context manager per triage request, or hold it open for the lifetime of the worker.

### assert _conn guard
**Source:** `_postgres.py` line 121 (`put_item`):
```python
assert self._conn is not None, "PostgresStore must be used as a context manager: ..."
```
**Apply to:** All 4 new PostgresStore methods (`put_enrichment`, `get_enrichment`, `put_embedding`, `find_near_duplicate`).

### connect_robust reconnect
**Source:** `libs/contracts/src/contracts/_bus_rabbitmq.py` `_ensure_connection` (lines 84–107)
**Apply to:** `worker.py run_consumer()` — call `await bus._ensure_connection()` before `consume()`. D-04 specifies health does NOT return 5xx on bus disconnect.

### env var pattern
**Source:** `apps/triage/triage_score.py` lines 42–56 (`llm()`)
```python
base = os.environ.get("LLM_BASE_URL", "http://127.0.0.1:8000/v1")
key  = os.environ.get("LLM_API_KEY", "omlx")
model = os.environ.get("LLM_MODEL", "qwen36-ud-4bit")
```
**Apply to:** `worker.py get_embedding()` — same env vars, same fallback defaults.

### Dockerfile local-lib install
**Source:** `apps/ingest-imap/Dockerfile` lines 7–11
```dockerfile
COPY libs/contracts /build/contracts
COPY libs/store /build/store
RUN pip install --no-deps /build/contracts /build/store
```
**Apply to:** `apps/triage/Dockerfile` — identical pattern.

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `tests/test_triage_health.py` | test | request-response | No existing asyncio health server tests in codebase |

---

## Critical Schema Notes (for planner)

1. **`infotriage.enrichment` has NO UNIQUE(item_id)** — confirmed from `005-stubs.sql`. `006-enrichment.sql` must add `ADD CONSTRAINT IF NOT EXISTS enrichment_item_id_unique UNIQUE (item_id)` **before** `put_enrichment` upsert can work.

2. **`infotriage.embeddings` has NO UNIQUE(item_id)** — confirmed from `003-vectors.sql`. `put_embedding` ON CONFLICT upsert requires adding `UNIQUE(item_id)` to `infotriage.embeddings`. Include in `006-enrichment.sql` or a new `007-embedding-unique.sql`.

3. **`RabbitMQBus.subscribe()` is drain-only** — 500ms window, not a persistent consumer. `consume()` must be added as a new method (not on the `BusClient` Protocol).

4. **`score_item()` uses module-level `CCIR`** — the D-02 fix requires both removing `CCIR = load_ccir()` at module level AND updating the f-string from `{CCIR}` to `{ccir}` (lowercase local var).

---

## Metadata

**Analog search scope:** `apps/triage/`, `apps/ingest-imap/`, `libs/store/`, `libs/contracts/`, `tests/`, `docker-compose.yml`
**Files scanned:** 14 source files read via ask-omlx
**Pattern extraction date:** 2026-06-29
