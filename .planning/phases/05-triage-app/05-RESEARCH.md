# Phase 05: triage-app — Research

**Researched:** 2026-06-29
**Domain:** Event-driven Python worker — aio-pika consumer, pgvector dedup, psycopg3 enrichment, asyncio health server
**Confidence:** HIGH (all claims derived from codebase reads + Context7 official docs)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Worker module structure**
- D-01: New `apps/triage/worker.py` is the container entry point. aio-pika consumer loop and `/health` HTTP server both live here. `triage_score.py` is preserved as a pure scoring helper.
- D-02: `triage_score.py` gets one targeted fix: `load_ccir()` moved inside `score_item()`. Module-level `CCIR = load_ccir()` line (currently line 42) is removed.
- D-03: `worker.py` uses `asyncio.gather(run_consumer(), run_health_server())` inside `asyncio.run(main())`. Pure asyncio — no extra framework.
- D-04: `/health` HTTP server implemented with Python stdlib `asyncio.start_server()`. Zero new deps. Returns `200 OK` on `GET /health`. Liveness only — bus disconnect does NOT make health return 5xx.

**Embedding store access**
- D-05: Two new Store Protocol methods: `put_embedding(item_id, vector)` (upsert) and `find_near_duplicate(vector, window_days=7, threshold=0.84) -> Optional[str]` (returns matched item_id or None).
- D-06: `find_near_duplicate` returns `Optional[str]` (the matched `item_id`), not `bool`. SQL: `ORDER BY embedding <=> %s LIMIT 1` with 7-day window and cosine distance filter.
- D-07: `InMemoryStore` implements `find_near_duplicate` with Python cosine similarity loop.

**Shadow-run delivery**
- D-08: Phase 5 includes `scripts/shadow_run.py`. Queries enrichment + articles; re-runs `score_item()` standalone; prints side-by-side table comparing stored bucket vs rescore bucket.
- D-09: Parity = matching bucket on ≥10 articles. Old bucket source = `infotriage.enrichment.bucket` (the new event-driven scorer's output). Operator confirms parity, then removes fever_triage.py from production.

**Migration delivery**
- D-10: Enrichment schema migration delivered as `libs/store/sql/006-enrichment.sql` with `ALTER TABLE infotriage.enrichment ADD COLUMN IF NOT EXISTS ...` for all 7 columns. Runs via `init_schema()` idempotently.

### Claude's Discretion
None — all decisions are locked.

### Deferred Ideas (OUT OF SCOPE)
- SAB/digest generation — Phase 6
- CNR alerting / push notifications — Phase 12
- Entity resolution — Phase 8
- CCIR pre-filter cosine similarity (A-1) — Phase 9
- RAG recall — Phase 9
- `infotriage.ccir` table — Phase 9
- Admiralty reliability scoring (A-4) — post-M1 backlog
- FreshRSS subscription management — remains as-is
- Multiple concurrent triage worker scaling — single worker for M1
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| R1 | Enrichment schema migration: 7 new columns + `put_enrichment`/`get_enrichment` Store methods | 006-enrichment.sql pattern; ON CONFLICT DO UPDATE upsert; existing init_schema() loads all sql/*.sql sorted |
| R2 | Event subscription: triage container consumes `item.ingested`; missing-article event → log+ack (no crash) | aio-pika `connect_robust()` + `queue.consume(handler)` + new `RabbitMQBus.consume()` method needed |
| R3 | LLM scoring: port `score_item()` to event-driven; malformed LLM JSON → fallback; score clamped [0,10] | `score_item()` already handles malformed JSON (line 119-121); clamp in worker before `put_enrichment` |
| R4 | Semantic dedup: mE5-large embedding before LLM call; cosine ≥ 0.84 in 7-day window → skip | `put_embedding`/`find_near_duplicate` Store methods; `<=>` cosine operator; `register_vector()` |
| R5 | `verdict.ready` publication: after enrichment commit; cnr/bucket field mapping | `RabbitMQBus.publish("verdict.ready", item_id, payload.model_dump())`; map "none"→"Routine", "read"→"keep" |
| R6 | Shadow-run parity ≥10 items → retire `fever_triage.py` from scheduler and docker-compose | `scripts/shadow_run.py`; manual operator confirm; remove from compose triage stanza |
| R7 | Triage container port 22030; `GET /health` → 200; survives RabbitMQ disconnect | Dockerfile (python:3.12-slim pattern); `asyncio.start_server()`; `connect_robust()` auto-reconnect |
</phase_requirements>

---

## Summary

Phase 5 bridges the gap between the proven standalone scorer (`triage_score.py`) and the event-driven architecture established in Phases 2–4. The main work is four parallel streams: (1) SQL migration + Store Protocol extension, (2) new `apps/triage/worker.py` entry point that consumes `item.ingested` and publishes `verdict.ready`, (3) mE5-large embedding dedup added as a pre-filter before the LLM call, and (4) Dockerfile + docker-compose registration at port 22030.

All code patterns are well-established by prior phases. `psycopg3 + pgvector`, `aio-pika connect_robust()`, and the `python:3.12-slim` Dockerfile pattern are all proven. The most significant new technical decisions are: (a) the `RabbitMQBus` class needs a new `consume(routing_key, handler, prefetch_count)` method because the existing `subscribe()` is a test-drain only, and (b) the oMLX embedding call mirrors the existing `llm()` pattern in `triage_score.py` using `urllib.request`.

One important gap discovered in codebase analysis: `BusClient` Protocol and `RabbitMQBus` expose only `publish()` and `subscribe()` (drain-only). The worker's persistent consumer loop requires **either** a new `RabbitMQBus.consume(routing_key, handler, prefetch_count)` method **or** a direct aio-pika connection in `worker.py`. The CONTEXT.md decisions imply the former; the planner must pick one path explicitly.

**Primary recommendation:** Implement `worker.py` with `asyncio.gather(run_consumer(), run_health_server())`, extend `RabbitMQBus` with a `consume()` method for the persistent consumer, use `RabbitMQBus.publish()` for `verdict.ready`, and follow the established `python:3.12-slim` Dockerfile pattern.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| `item.ingested` consumption | Backend worker | — | aio-pika async consumer; triage is the sole subscriber of `q.triage` |
| LLM scoring (qwen36) | Backend worker | — | ADR-004: local LLM only; `score_item()` calls `LLM_BASE_URL` |
| mE5-large embedding | Backend worker | Database (pgvector) | Worker calls oMLX `/v1/embeddings`; result stored in `infotriage.embeddings` |
| Semantic dedup lookup | Database (pgvector) | Backend worker | `<=>` cosine distance query against HNSW index; worker interprets result |
| Enrichment persistence | Database (Postgres) | Backend worker | `put_enrichment` upserts to `infotriage.enrichment`; worker triggers it |
| `verdict.ready` publication | Backend worker | — | Published after `put_enrichment()` returns — ordering is a hard constraint |
| Health endpoint | Backend worker | — | Liveness only; stdlib `asyncio.start_server()` in same process |
| Schema migration | Database (Postgres) | — | `006-enrichment.sql` via `init_schema()` on container startup |
| Shadow-run comparison | Ops tooling | — | One-shot `scripts/shadow_run.py`; reads from Postgres; not in runtime path |

---

## Standard Stack

### Core (all pre-existing from Phases 2–4 — no new packages)

| Library | Version (in-use) | Purpose | Why Standard |
|---------|-----------------|---------|--------------|
| `aio-pika` | Phase 3 (≥9.x) | RabbitMQ async consumer/publisher | Established in Phase 3; `connect_robust()` auto-reconnect |
| `psycopg[binary]` | Phase 2 (≥3.1) | Postgres connection | Established in Phase 2; psycopg3 API used throughout |
| `pgvector` | Phase 2 | pgvector type adapter (`register_vector`) | `pgvector.psycopg.register_vector` already in `_postgres.py` |
| `contracts` (local) | Phase 3 | `ItemIngested`, `VerdictReady`, `RabbitMQBus` | Local lib; installed via `pip install --no-deps /build/contracts` |
| `store` (local) | Phase 2 | `Store` Protocol, `PostgresStore`, `InMemoryStore` | Local lib; installed via `pip install --no-deps /build/store` |
| Python stdlib | 3.12 | `asyncio`, `json`, `urllib.request`, `pathlib` | Zero deps; all worker I/O uses stdlib following existing `llm()` pattern |

### No New Runtime Dependencies
Phase 5 adds no new PyPI packages. All needed capabilities are already available:
- HTTP embedding call: `urllib.request` (mirrors existing `llm()` in `triage_score.py`)
- Health server: `asyncio.start_server()` (stdlib)
- Vector math (InMemoryStore): `math.sqrt` or inline dot product (stdlib)

**Dockerfile requirements.txt** will list: `aio-pika`, `psycopg[binary]`, `pgvector` (plus transitive deps). These are all Phase 2/3 proven.

---

## Package Legitimacy Audit

> Phase 5 installs **no new PyPI packages**. All runtime dependencies were introduced in Phases 2–4 and are already legitimacy-checked. No new audit required.

| Package | Status | Notes |
|---------|--------|-------|
| `aio-pika` | Pre-existing (Phase 3) | Already in use |
| `psycopg[binary]` | Pre-existing (Phase 2) | Already in use |
| `pgvector` | Pre-existing (Phase 2) | Already in use |
| `contracts` (local) | Local lib | Not a PyPI package |
| `store` (local) | Local lib | Not a PyPI package |

**Packages removed due to SLOP verdict:** none
**Packages flagged as suspicious (SUS):** none

---

## Architecture Patterns

### System Architecture Diagram

```
RabbitMQ
  q.triage  ──item.ingested──▶  worker.py (apps/triage/)
                                    │
                          [get_item from Postgres]
                                    │
                          [get_embedding via oMLX]
                                    │
                          [find_near_duplicate in pgvector]
                                    │
                         ┌──────────┴──────────────┐
                    duplicate?                   not duplicate
                         │                           │
                  put_enrichment             score_item(triage_score.py)
                  (bucket='skip')                    │
                  put_embedding              put_enrichment (all 7 fields)
                         │                  put_embedding
                         └──────────┬───────────────┘
                          VerdictReady mapping
                          bus.publish("verdict.ready")
                                    │
                                q.brief ──▶ Phase 6

asyncio.start_server()  ──GET /health──▶  200 OK (liveness, same process)
```

### Recommended Project Structure

```
apps/triage/
├── Dockerfile          # NEW — python:3.12-slim, installs contracts+store+requirements.txt
├── requirements.txt    # NEW — aio-pika, psycopg[binary], pgvector
├── worker.py           # NEW — container entry point; asyncio.gather(consumer, health)
├── triage_score.py     # MODIFY — remove CCIR=load_ccir() at module level; move inside score_item()
├── fever_triage.py     # KEEP FILE — retire from scheduler/compose only (do not delete)
├── digest.py           # UNTOUCHED
└── sab_html.py         # UNTOUCHED

libs/store/
├── sql/
│   └── 006-enrichment.sql   # NEW — ALTER TABLE ADD COLUMN IF NOT EXISTS ×7
└── src/store/
    ├── _protocol.py    # MODIFY — add put_enrichment, get_enrichment, put_embedding, find_near_duplicate
    ├── _postgres.py    # MODIFY — implement all 4 new methods
    └── _inmemory.py    # MODIFY — implement all 4 new methods (cosine loop for find_near_duplicate)

libs/contracts/src/contracts/
└── _bus_rabbitmq.py    # MODIFY — add consume(routing_key, handler, prefetch_count=1) method

scripts/
└── shadow_run.py       # NEW — parity check tool

docker-compose.yml      # MODIFY — add triage service on 22030; env_file: .env
```

### Pattern 1: aio-pika Persistent Consumer (for `RabbitMQBus.consume`)

**What:** Long-running consumer callback registered on a queue; runs until process exits.
**When to use:** `worker.py` `run_consumer()` coroutine.

```python
# Source: https://github.com/mosquito/aio-pika/blob/master/docs/source/quick-start.md
import aio_pika
from aio_pika.abc import AbstractIncomingMessage

async def run_consumer(amqp_url: str, handler) -> None:
    connection = await aio_pika.connect_robust(amqp_url)
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=1)   # process one message at a time
    queue = await channel.get_queue("q.triage")
    await queue.consume(handler)
    try:
        await asyncio.Future()   # run forever
    finally:
        await connection.close()

async def on_message(message: AbstractIncomingMessage) -> None:
    async with message.process():             # auto-acks on clean exit; nacks on exception
        payload = json.loads(message.body.decode())
        await handle_item(payload["item_id"])
```

**Critical:** `message.process()` without arguments re-queues on exception. If exception handling should nack-without-requeue (poison message), pass `requeue=False` explicitly.

### Pattern 2: Store Protocol Extension

**What:** Adding four new methods to `Store` Protocol and both concrete implementations.
**When to use:** Both `_protocol.py` and both concrete stores (`_postgres.py`, `_inmemory.py`).

```python
# _protocol.py addition — follow existing put_item / get_item pattern
from typing import Optional

class Store(Protocol):
    # ... existing methods ...

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

### Pattern 3: pgvector Cosine Distance Query (psycopg3)

**What:** Nearest-neighbor cosine search with distance filter.
**When to use:** `PostgresStore.find_near_duplicate()` implementation.

```python
# Source: https://github.com/pgvector/pgvector-python/blob/master/README.md
# register_vector(conn) MUST be called before this — already done in __enter__

def find_near_duplicate(self, vector: list[float], window_days: int = 7, threshold: float = 0.84) -> Optional[str]:
    # cosine distance = 1 - cosine_similarity; threshold 0.84 → distance < 0.16
    sql = """
        SELECT item_id, embedding <=> %s::vector AS dist
        FROM infotriage.embeddings
        WHERE created_at >= NOW() - INTERVAL %s
        ORDER BY embedding <=> %s::vector
        LIMIT 1
    """
    row = self._conn.execute(
        sql,
        (vector, f"{window_days} days", vector)
    ).fetchone()
    if row and row["dist"] < (1.0 - threshold):
        return row["item_id"]
    return None
```

Note: `<=>` is the pgvector cosine distance operator (not `<->` which is L2). [CITED: github.com/pgvector/pgvector-python/blob/master/README.md]

### Pattern 4: Asyncio Health Server (stdlib)

**What:** Minimal HTTP liveness server, zero deps.
**When to use:** `worker.py` `run_health_server()` coroutine.

```python
# Source: D-04 (CONTEXT.md) + Python stdlib asyncio docs [ASSUMED: exact impl style]
import asyncio

async def run_health_server(host: str = "0.0.0.0", port: int = 22030) -> None:
    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await reader.read(1024)  # consume request (ignore contents)
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK")
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(handle, host, port)
    async with server:
        await server.serve_forever()
```

### Pattern 5: oMLX Embedding Call

**What:** Call oMLX `/v1/embeddings` for mE5-large; mirrors existing `llm()` function.
**When to use:** `worker.py` `get_embedding()` function.

```python
# Source: CONTEXT.md D-05 specifics; mirrors triage_score.py llm() (lines 44-56) [CITED: 05-CONTEXT.md]
import urllib.request, json, os

def get_embedding(text: str) -> list[float]:
    base = os.environ.get("LLM_BASE_URL", "http://127.0.0.1:8000/v1")
    key  = os.environ.get("LLM_API_KEY", "omlx")
    body = json.dumps({
        "model": "intfloat/multilingual-e5-large",
        "input": text,
    }).encode()
    req = urllib.request.Request(
        base.rstrip("/") + "/embeddings", data=body,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)["data"][0]["embedding"]
```

Input: `title + " " + summary[:512]`. [CITED: 05-CONTEXT.md specifics section]

### Pattern 6: Field Mapping (triage_score → VerdictReady)

**What:** `score_item()` returns different literal values than `VerdictReady` expects.
**When to use:** In `worker.py` before constructing `VerdictReady`.

```python
# Source: 05-CONTEXT.md §code_context cnr/bucket field mapping [CITED: 05-CONTEXT.md]
# triage_score.py returns:  cnr: "I"|"II"|"none",  bucket: "read"|"maybe"|"skip"
# VerdictReady expects:      cnr: "I"|"II"|"Routine", bucket: "keep"|"maybe"|"skip"

def map_cnr(cnr: str) -> str:
    return "Routine" if cnr == "none" else cnr

def map_bucket(bucket: str) -> str:
    return "keep" if bucket == "read" else bucket
```

### Pattern 7: 006-enrichment.sql Migration

**What:** Idempotent ALTER TABLE adding 7 columns to the bare enrichment stub.
**When to use:** New `libs/store/sql/006-enrichment.sql`.

```sql
-- Source: D-10 (CONTEXT.md); follows 005-stubs.sql stub-and-extend pattern [CITED: 05-CONTEXT.md]
ALTER TABLE infotriage.enrichment ADD COLUMN IF NOT EXISTS ccir   TEXT;
ALTER TABLE infotriage.enrichment ADD COLUMN IF NOT EXISTS cnr    TEXT;
ALTER TABLE infotriage.enrichment ADD COLUMN IF NOT EXISTS score  INT CHECK (score BETWEEN 0 AND 10);
ALTER TABLE infotriage.enrichment ADD COLUMN IF NOT EXISTS bucket TEXT;
ALTER TABLE infotriage.enrichment ADD COLUMN IF NOT EXISTS why    TEXT;
ALTER TABLE infotriage.enrichment ADD COLUMN IF NOT EXISTS pmesii TEXT;
ALTER TABLE infotriage.enrichment ADD COLUMN IF NOT EXISTS tessoc TEXT;
```

### Pattern 8: put_enrichment SQL (psycopg3)

**What:** Upsert enrichment row; idempotent on duplicate item_id.
**When to use:** `PostgresStore.put_enrichment()`.

```python
# Source: Phase 2 patterns; follows put_item ON CONFLICT DO UPDATE style [CITED: _postgres.py]
def put_enrichment(self, item_id: str, fields: dict) -> None:
    self._conn.execute(
        """
        INSERT INTO infotriage.enrichment (item_id, ccir, cnr, score, bucket, why, pmesii, tessoc)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (item_id) DO UPDATE SET
            ccir=%s, cnr=%s, score=%s, bucket=%s, why=%s, pmesii=%s, tessoc=%s,
            created_at=NOW()
        """,
        (item_id,
         fields.get("ccir"), fields.get("cnr"), fields.get("score"),
         fields.get("bucket"), fields.get("why"), fields.get("pmesii"), fields.get("tessoc"),
         fields.get("ccir"), fields.get("cnr"), fields.get("score"),
         fields.get("bucket"), fields.get("why"), fields.get("pmesii"), fields.get("tessoc"))
    )
```

Note: `infotriage.enrichment` must have a `UNIQUE(item_id)` constraint for `ON CONFLICT` to work. If the stub table from 005-stubs.sql has no such constraint, 006-enrichment.sql must also add it: `ALTER TABLE infotriage.enrichment ADD CONSTRAINT enrichment_item_id_unique UNIQUE (item_id);` [ASSUMED: 005-stubs.sql may not have this constraint — check before writing the SQL].

### Anti-Patterns to Avoid

- **f-string SQL**: All SQL must use `%s` bind parameters. No f-strings or string concatenation in SQL. [CITED: _postgres.py V5/T-02-01 comment]
- **Cloud LLM**: The `LLM_BASE_URL` env var must point to oMLX or Spark; no external API calls. [CITED: docs/ARCHITECTURE.md ADR-004]
- **Module-level CCIR cache**: Do NOT keep `CCIR = load_ccir()` at module level after the D-02 fix. [CITED: 05-CONTEXT.md D-02]
- **Publish before enrichment commit**: `bus.publish("verdict.ready", ...)` must appear AFTER `store.put_enrichment()` returns. [CITED: 05-SPEC.md prohibitions]
- **Ack before enrichment write**: `message.process()` context manager ensures ack on clean exit; never manually ack before the enrichment row is committed. [CITED: 05-SPEC.md prohibitions]
- **Using `<->` for cosine distance**: pgvector uses `<=>` for cosine distance; `<->` is L2 (Euclidean). Using the wrong operator silently returns wrong results. [CITED: github.com/pgvector/pgvector-python/blob/master/README.md]

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| RabbitMQ reconnect on disconnect | Custom retry loop | `aio_pika.connect_robust()` | Handles exponential backoff, channel re-creation, topology re-declaration automatically |
| Vector cosine distance | Python cosine loop in Postgres queries | `<=>` pgvector operator + HNSW index | HNSW index makes ANN search O(log n); Python loop is O(n) and would be ~100× slower at scale |
| HTTP health server | Full ASGI/uvicorn stack | `asyncio.start_server()` | Two-line handler; zero new deps; returns 200 for liveness — nothing more needed |
| JSON parsing fallback | Custom regex extractor | Existing `triage_score.py` fallback (lines 115-121) | Already handles code-fence stripping + `{}`-extraction + exception catch; just reuse |
| Embedding HTTP call | `httpx`/`requests` library | `urllib.request` (stdlib) | Mirrors existing `llm()` pattern; no new dep; adequate for single-request-at-a-time |

**Key insight:** Every "hard" problem in Phase 5 is already solved by prior phases or stdlib. The work is wiring, not invention.

---

## Common Pitfalls

### Pitfall 1: `register_vector()` called before DDL (vector extension not yet created)
**What goes wrong:** `register_vector(conn)` raises `ProgrammingError` if the `vector` extension has not been created yet.
**Why it happens:** `init_schema()` opens a DDL autocommit connection, runs all SQL files, then calls `register_vector(ddl_conn)`. If called in the wrong order (before DDL), the type adapter can't bind.
**How to avoid:** Follow existing `_postgres.py` pattern: `register_vector()` is called AFTER all DDL files run in `init_schema()`, and again in `__enter__` for the main connection. [CITED: _postgres.py lines 64, 84]
**Warning signs:** `ProgrammingError: type "vector" does not exist` on startup.

### Pitfall 2: Missing UNIQUE constraint on `infotriage.enrichment.item_id`
**What goes wrong:** `ON CONFLICT (item_id) DO UPDATE` silently errors if no unique index/constraint exists on `item_id`.
**Why it happens:** The stub table from `005-stubs.sql` has no unique constraint — it only has `id SERIAL PK` and `item_id TEXT NOT NULL`.
**How to avoid:** `006-enrichment.sql` must add `ADD CONSTRAINT enrichment_item_id_unique UNIQUE (item_id)` before the `ON CONFLICT` upsert is used.
**Warning signs:** `psycopg.errors.InvalidColumnReference` or `there is no unique or exclusion constraint matching the ON CONFLICT specification` at runtime.

### Pitfall 3: Persistent consumer not in BusClient Protocol
**What goes wrong:** Calling `bus.subscribe("item.ingested")` in a tight loop for persistent consumption works for tests but is wrong for production — it returns a snapshot list (500ms drain window), not a callback consumer.
**Why it happens:** `BusClient.subscribe()` and `RabbitMQBus.subscribe()` are test-drain implementations returning `list[dict]`. No persistent consumer callback interface exists on the Protocol.
**How to avoid:** Either (A) add `RabbitMQBus.consume(routing_key, handler, prefetch_count=1)` as a non-Protocol method and call it from worker.py, or (B) open a direct `aio_pika.connect_robust()` connection in `worker.py`. Option A is what the CONTEXT.md decisions imply.
**Warning signs:** Messages are being processed only during the 500ms drain window and not continuously.

### Pitfall 4: `triage_score.py` module-level CCIR still cached after D-02 fix
**What goes wrong:** If `CCIR = load_ccir()` stays at module level AND `score_item()` is modified to also call `load_ccir()` internally, there's dead code but no functional regression. The pitfall is forgetting to remove the module-level line — hot-edit of `ccir.md` won't be picked up on the next call because the local variable still shadows the module-level read.
**Why it happens:** D-02 says to add `ccir = load_ccir()` as first line inside `score_item()`, replacing the `{CCIR}` reference in the f-string. But `score_item()` currently uses the module-level `CCIR` in the f-string (line 43 of the prompt). If the inner variable is named `ccir` (lowercase) and the f-string still references `{CCIR}` (uppercase), the hot-read won't take effect.
**How to avoid:** The fix has two parts: (1) remove line 42 (`CCIR = load_ccir()`), and (2) add `ccir = load_ccir()` inside `score_item()` as its first line, then update the f-string to reference `{ccir}` (lowercase).
**Warning signs:** Test for hot-edit fails; editing ccir.md doesn't change scores on next run.

### Pitfall 5: `VerdictReady` field mapping errors
**What goes wrong:** `triage_score.py` returns `cnr: "none"` and `bucket: "read"`, but `VerdictReady` is typed `cnr: Literal["I", "II", "Routine"]` and `bucket: Literal["keep", "maybe", "skip"]`. Passing raw scorer output to `VerdictReady` causes a pydantic validation error.
**Why it happens:** The scorer uses "none"/"read" while contracts use "Routine"/"keep". The mapping is done in worker.py.
**How to avoid:** Always apply `map_cnr()` and `map_bucket()` before constructing `VerdictReady`. [CITED: 05-CONTEXT.md code_context]

### Pitfall 6: Worker acks message before enrichment write on crash
**What goes wrong:** If `message.process()` auto-acks the message but the process crashes between ack and `put_enrichment()`, the article is silently lost.
**Why it happens:** aio-pika's `async with message.process()` acks on context manager exit (after the `async with` block). If `put_enrichment()` happens AFTER the context manager exits, there's a window.
**How to avoid:** All logic (get_item, get_embedding, find_near_duplicate, put_enrichment, put_embedding, bus.publish) must happen INSIDE the `async with message.process():` block. The context manager exits only after all of that completes. [CITED: 05-SPEC.md prohibitions]

---

## Runtime State Inventory

> Not applicable — Phase 5 creates new infrastructure, does not rename/refactor existing state. The `fever_triage.py` retirement is a removal from docker-compose and scheduler config, not a data migration.

**Actions at cutover (not a migration — see shadow-run R6):**
- Remove `fever_triage.py` invocation from scheduler service config
- Remove any fever-related cron entries in scheduler YAML
- Phase 5 does not move or transform existing data in Postgres; enrichment rows are NEW

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (pyproject.toml `[tool.pytest.ini_options]`) |
| Config file | `pyproject.toml` — testpaths=["tests"], pythonpath includes `apps/triage` |
| Quick run command | `pytest tests/test_triage_enrichment.py tests/test_score_parse.py -x` |
| Full suite command | `pytest -m "not db_live and not rabbitmq"` (unit only) or `pytest` (all, needs live deps) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| R1 | `put_enrichment`/`get_enrichment` round-trip + double-write idempotency | unit (InMemoryStore) | `pytest tests/test_triage_enrichment.py::test_put_get_enrichment -x` | ❌ Wave 0 |
| R1 | Schema has 7 new columns after migration | integration (db_live) | `pytest tests/test_store_integration.py::test_enrichment_schema -x -m db_live` | ❌ Wave 0 |
| R2 | Missing-article event: logs warning + acks (no crash) | unit (InMemoryStore + mock bus) | `pytest tests/test_triage_worker.py::test_missing_article_acks -x` | ❌ Wave 0 |
| R2 | MUST NOT ack before enrichment commit: mock put_enrichment raises → message nacked | unit | `pytest tests/test_triage_worker.py::test_enrichment_failure_nacks -x` | ❌ Wave 0 |
| R3 | Malformed LLM response → fallback enrichment row (no crash) | unit | `pytest tests/test_triage_worker.py::test_malformed_llm_fallback -x` | ❌ Wave 0 |
| R3 | Score clamped to [0, 10] | unit | `pytest tests/test_triage_worker.py::test_score_clamped -x` | ❌ Wave 0 |
| R3 | ccir.md hot-edit: modify file between two scoring runs; assert second uses new content | unit | `pytest tests/test_triage_worker.py::test_ccir_hot_read -x` | ❌ Wave 0 |
| R4 | Two near-duplicate articles → second gets bucket='skip', why contains 'duplicate', no LLM call | unit | `pytest tests/test_triage_worker.py::test_dedup_skip -x` | ❌ Wave 0 |
| R4 | Two distinct articles → both scored by LLM | unit | `pytest tests/test_triage_worker.py::test_dedup_distinct -x` | ❌ Wave 0 |
| R4 | `find_near_duplicate` (InMemoryStore cosine loop) | unit | `pytest tests/test_triage_enrichment.py::test_find_near_duplicate -x` | ❌ Wave 0 |
| R5 | `verdict.ready` event received with correct fields after item processed | unit (InMemoryBus) | `pytest tests/test_triage_worker.py::test_verdict_ready_fields -x` | ❌ Wave 0 |
| R5 | No `verdict.ready` if enrichment write fails | unit | `pytest tests/test_triage_worker.py::test_no_verdict_on_enrichment_failure -x` | ❌ Wave 0 |
| R7 | `GET /health` → 200 | unit (asyncio TestClient or httpx) | `pytest tests/test_triage_health.py::test_health_200 -x` | ❌ Wave 0 |

**Existing tests that remain valid (no changes needed):**
- `tests/test_score_parse.py` — covers score_item JSON parsing (still passes after D-02 fix since interface is unchanged)

### Sampling Rate
- **Per task commit:** `pytest tests/test_score_parse.py -x` (existing) + the relevant new test file for the task
- **Per wave merge:** `pytest -m "not rabbitmq"` (unit + db_live if Postgres running)
- **Phase gate:** Full suite green (including `pytest -m rabbitmq` against live RabbitMQ)

### Wave 0 Gaps
- [ ] `tests/test_triage_enrichment.py` — covers R1 (Store protocol extension), R4 (find_near_duplicate)
- [ ] `tests/test_triage_worker.py` — covers R2, R3, R4, R5 (worker integration with InMemoryStore + InMemoryBus)
- [ ] `tests/test_triage_health.py` — covers R7 (health endpoint)

*Note: `apps/triage` is already on `pythonpath` in `pyproject.toml` — no new pytest config needed.*

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | triage is internal service, no user auth |
| V3 Session Management | no | stateless event handler |
| V4 Access Control | no | internal Docker network only |
| V5 Input Validation | yes | `%s` bind params for all SQL; score clamped [0,10]; item_id is sha256 hex (ASCII-safe) |
| V6 Cryptography | no | no crypto operations in Phase 5 |

### Known Threat Patterns for This Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection via enrichment text fields (ccir, why, pmesii) | Tampering | `%s` bind params only — LLM output treated as opaque text, never interpolated into SQL |
| AMQP credentials in logs | Information Disclosure | log item_id only; never log INFOTRIAGE_AMQP_DSN; follows T-04-01 pattern |
| LLM_BASE_URL pointing to external host | Tampering | ADR-004: container env var; checked at startup |
| Container running as root | Elevation of Privilege | Add `USER nobody` or non-root USER in Dockerfile |

*Full security audit: `/gsd-secure-phase` post-implementation*

---

## Open Questions (RESOLVED)

1. **UNIQUE constraint on `infotriage.enrichment.item_id`**
   - What we know: 005-stubs.sql creates `enrichment(id SERIAL PK, item_id TEXT NOT NULL, created_at TIMESTAMPTZ)` — no unique constraint on `item_id`.
   - What's unclear: Whether there's already a unique constraint from a migration between 005 and now, or from Phase 2 init.
   - Recommendation: Planner should verify by running `\d infotriage.enrichment` on dev Postgres; 006-enrichment.sql must add `UNIQUE (item_id)` if absent.
   - RESOLVED (05-01 Task 2): `006-enrichment.sql` adds `CREATE UNIQUE INDEX IF NOT EXISTS enrichment_item_id_unique ON infotriage.enrichment (item_id)` — no constraint existed in 005-stubs.sql.

2. **RabbitMQBus.consume() vs direct aio-pika connection**
   - What we know: The existing `BusClient` Protocol has only `publish()` and `subscribe()` (drain-only). `subscribe()` is not suitable for a persistent consumer loop.
   - What's unclear: Whether to add `consume(routing_key, handler, prefetch_count)` to `RabbitMQBus` (cleanly extends the class without changing the Protocol), or to open a direct aio-pika connection in `worker.py`.
   - Recommendation: Add `consume()` to `RabbitMQBus` (not to the Protocol). Worker calls `await bus.consume("item.ingested", on_message, prefetch_count=1)`. This avoids duplicating topology declaration and follows the CONTEXT.md D-01 intent of "using the bus client".
   - RESOLVED (05-02 Task 1): `RabbitMQBus.consume(routing_key, handler, prefetch_count=1)` added as a new non-Protocol method on `RabbitMQBus` in `libs/bus/_bus_rabbitmq.py`.

3. **put_embedding: upsert or insert-only?**
   - What we know: D-05 says `put_embedding` uses "ON CONFLICT DO UPDATE (upsert, same idempotency pattern as `put_enrichment`)". The existing `infotriage.embeddings` table has `item_id FK` but may not have a unique constraint on `item_id`.
   - What's unclear: Whether 003-vectors.sql includes a unique constraint on `item_id` in `infotriage.embeddings`.
   - Recommendation: Add `UNIQUE(item_id)` to `infotriage.embeddings` in a sub-migration or confirm it already exists before writing the upsert.
   - RESOLVED (05-01 Task 2): `006-enrichment.sql` also adds `CREATE UNIQUE INDEX IF NOT EXISTS embeddings_item_id_unique ON infotriage.embeddings (item_id)` to enable the `ON CONFLICT DO UPDATE` upsert in `put_embedding`.

4. **Shadow-run "old bucket" source**
   - What we know: D-09 says "Old bucket source = `infotriage.enrichment.bucket` (the new event-driven scorer's output)". The comparison is: does re-running `score_item()` standalone produce the same bucket as the event-driven worker?
   - What's unclear: The "old path" (fever_triage.py) has never written to `infotriage.enrichment`. So for the shadow-run to work, the NEW event-driven worker must have scored ≥10 articles first, THEN the shadow_run.py compares those enrichment-stored buckets vs. re-running standalone.
   - Recommendation: Shadow-run plan step: (1) run triage worker against 111 live articles, (2) once ≥10 enrichment rows exist, run `scripts/shadow_run.py`, (3) confirm ≥10 matching buckets.
   - RESOLVED (05-05 Task 1): `shadow_run.py` fetches enrichment rows from `infotriage.enrichment`, re-runs `score_item()` on each item_id, and compares raw `bucket` values. The parity gate requires ≥10 matching rows before the Fever cutover proceeds.

---

## Environment Availability

| Dependency | Required By | Available | Notes |
|------------|-------------|-----------|-------|
| Postgres :22000 | Store tests (db_live), migration | ✓ (Phase 2) | pgvector/pgvector:pg16, infotriage.embeddings HNSW index in place |
| RabbitMQ :22001 | Bus tests (rabbitmq mark) | ✓ (Phase 3) | rabbitmq:3.13-management, topology declared by Phase 3 |
| oMLX :8000/v1 | Embedding calls (`get_embedding`) | ✓ (existing) | intfloat/multilingual-e5-large loaded on demand |
| Docker | Container build | ✓ | docker-compose.yml at project root |

**Missing dependencies with no fallback:** none

---

## State of the Art

| Old Approach | Current Approach | Notes |
|--------------|-----------------|-------|
| `fever_triage.py` polling FreshRSS Fever API | `worker.py` consuming `item.ingested` from RabbitMQ | Phase 5 transition |
| Keyword-overlap dedup | pgvector cosine HNSW dedup (mE5-large @ 0.84) | R2 spike proven mechanism |
| `score_item()` called with module-cached CCIR | `score_item()` reads ccir.md on every call | D-02 hot-read fix |
| Scores written to `verdicts.jsonl` (Phase 1 legacy) | Enrichment written to `infotriage.enrichment` (7 columns) | Phase 5 completes the migration |

**Deprecated/outdated in Phase 5:**
- `fever_triage.py`: Preserved as a file but retired from scheduler/compose — never call in production after cutover.
- `verdicts.jsonl`: Already deprecated in Phase 1; Phase 5 does not write to it.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `asyncio.start_server()` minimal handler shown uses `await reader.read(1024)` before writing response | Code Examples: Pattern 4 | HTTP client may not receive response if request isn't consumed first on some clients; use `reader.readline()` loop in practice |
| A2 | 005-stubs.sql has no `UNIQUE(item_id)` on `infotriage.enrichment` | Common Pitfalls #2 / Open Questions #1 | If constraint already exists, migration will error (idempotent `IF NOT EXISTS` resolves this) |
| A3 | `infotriage.embeddings` has no `UNIQUE(item_id)` constraint (003-vectors.sql not fully confirmed) | Open Questions #3 | If missing, put_embedding ON CONFLICT will fail at runtime |
| A4 | The `run_health_server()` coroutine using `asyncio.start_server()` works cleanly alongside `run_consumer()` in `asyncio.gather()` | Architecture Patterns | No known issue, but stdlib server + aio-pika in same event loop is the intended pattern per D-03 |

**Table is not empty.** Items A2 and A3 are verifiable immediately by querying the live Postgres schema.

---

## Sources

### Primary (MEDIUM confidence — Context7 official docs)
- `/mosquito/aio-pika` — connect_robust persistent consumer callback prefetch_count pattern
- `/pgvector/pgvector-python` — psycopg3 cosine distance `<=>` operator, register_vector

### Codebase reads (HIGH confidence — source code)
- `apps/triage/triage_score.py` — score_item(), llm(), load_ccir(), CCIR module-level var (line 42)
- `libs/store/src/store/_protocol.py` — Store Protocol methods
- `libs/store/src/store/_postgres.py` — psycopg3 patterns, register_vector, init_schema, Jsonb()
- `libs/store/src/store/_inmemory.py` — InMemoryStore pattern
- `libs/store/sql/003-vectors.sql` — infotriage.embeddings schema, HNSW index
- `libs/store/sql/005-stubs.sql` — infotriage.enrichment current stub schema
- `libs/contracts/src/contracts/_events.py` — ItemIngested, VerdictReady shapes
- `libs/contracts/src/contracts/_bus.py` — BusClient Protocol (publish + subscribe only)
- `libs/contracts/src/contracts/_bus_rabbitmq.py` — RabbitMQBus (subscribe is drain-only; no consume method)
- `docker-compose.yml` — service patterns, port band, env_file pattern
- `apps/ingest-imap/Dockerfile` — python:3.12-slim build pattern
- `tests/test_store_integration.py` — TRUNCATE isolation fixture, DEV_DSN pattern
- `tests/test_store_contract.py` — parametrized InMemoryStore/PostgresStore test pattern
- `tests/test_score_parse.py` — existing test structure for triage scorer

### CONTEXT.md decisions (HIGH confidence — operator-approved)
- `05-CONTEXT.md` — D-01 through D-10 (all locked implementation decisions)

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all packages are pre-existing, versions proven
- Architecture: HIGH — all patterns derived from codebase + official docs
- Pitfalls: HIGH — Pitfalls 1/2/3/5/6 verified from code; Pitfall 4 inferred from D-02 change semantics

**Research date:** 2026-06-29
**Valid until:** 2026-07-29 (30 days — stable stack, no fast-moving deps)
