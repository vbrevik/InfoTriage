# Phase 12: CNR alerting / dissemination - Pattern Map

**Mapped:** 2026-08-01
**Files analyzed:** 20 (new service files, 2 migration/contract files, 2 Store files, 7 ingest adapters, Dockerfile/requirements)
**Analogs found:** 18 / 20 (2 have no direct analog — outbox.py DLX-retry loop, ntfy bearer-token bootstrap)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|--------------------|------|-----------|-----------------|----------------|
| `apps/alerting/alerting_worker.py` | service (CLI entrypoint) | event-driven | `apps/wiki/wiki_worker.py` | exact |
| `apps/alerting/emitter.py` | service (consumer handler) | event-driven | `apps/wiki/wiki_worker.py` (consumer section) | exact |
| `apps/alerting/dedupe.py` | model/utility (DB query) | CRUD (atomic upsert) | `libs/store/src/store/_postgres.py::put_enrichment` | role-match |
| `apps/alerting/throttle.py` | utility (DB query) | batch/transform | `libs/store/src/store/_postgres.py::get_enrichment` (read-query shape) | partial |
| `apps/alerting/deep_link.py` | utility | transform | `apps/brief/vault_writer.py` (filename derivation) | exact |
| `apps/alerting/outbox.py` | service (HTTP client + retry) | request-response | none in-repo (httpx client pattern only, e.g. `apps/opml_health`) | no analog (new engineering) |
| `libs/store/sql/011-alert-state.sql` | migration | — | `libs/store/sql/006-enrichment.sql` | exact |
| `libs/contracts/src/contracts/_bus_rabbitmq.py` (modify `ROUTING_KEY_TO_QUEUE`) | config/route | pub-sub | same file, `q.wiki` fan-out precedent | exact |
| `libs/contracts/src/contracts/_item.py` (add `body` field) | model | CRUD | same file (existing `summary`/`body_ref` fields) | exact |
| `libs/store/src/store/_postgres.py::put_item`/`get_item` (add `body` column) | model/service | CRUD | same file, existing INSERT/SELECT column list | exact |
| `libs/store/src/store/_inmemory.py::put_item`/`get_item` (parity) | model/service | CRUD | same file, existing dict-store shape | exact |
| `apps/ingest-{gmail,imap,youtube,telegram,barentswatch,acled,obsidian}/*.py` (set `item.body`) | service (adapter) | CRUD (ingest write) | `apps/ingest-gmail/gmail_ingest.py` (`Item(...)` construction site) | exact (self-similar across all 7) |
| `apps/alerting/Dockerfile` | config | — | `apps/wiki/Dockerfile` | exact |
| `apps/alerting/requirements.txt` | config | — | `apps/wiki/requirements.txt` | exact |
| `apps/ntfy/Dockerfile` (extend for bearer token) | config | — | same file, existing `ntfy user add` block | no analog (new engineering, ADR-018 predates bearer tokens) |
| `tests/test_alerting_*.py` (6 files) | test | — | `tests/conftest.py` fixtures (`db_live`/`pg_store`) + existing `apps/wiki` test style | role-match |
| `tests/test_ingest_*_body.py` (7 files) | test | — | existing per-adapter ingest tests | role-match |

## Pattern Assignments

### `apps/alerting/alerting_worker.py` (service, event-driven)

**Analog:** `apps/wiki/wiki_worker.py` (328 lines, read in full)

**Fail-closed startup pattern** (`apps/wiki/wiki_worker.py:267-278`):
```python
async def _run_async_mode(args) -> None:
    if not args.dsn:
        print("ERROR: --dsn or INFOTRIAGE_PG_DSN required", file=sys.stderr)
        sys.exit(1)

    if args.mode == "events" and not args.amqp_dsn:
        print(
            "ERROR: --amqp-dsn or INFOTRIAGE_AMQP_DSN required for events mode",
            file=sys.stderr,
        )
        sys.exit(1)
```
Apply the identical shape for `NTFY_TOKEN` (SPEC R6, Pattern 7 in RESEARCH.md):
```python
ntfy_token = os.environ.get("NTFY_TOKEN", "")
if not ntfy_token:
    print("ERROR: NTFY_TOKEN required (bearer token for cnr-cat-i publish)", file=sys.stderr)
    sys.exit(1)
```

**Async task gather / CLI entrypoint** (`apps/wiki/wiki_worker.py:280-328`):
```python
with PostgresStore(dsn=args.dsn, blob_root=args.blob_root) as store:
    tasks = [run_health_server(host=args.health_host, port=args.health_port)]
    if args.mode == "periodic":
        tasks.append(run_periodic(store, args.vault_path, interval=args.interval, top_n=args.top_n))
    elif args.mode == "events":
        bus = RabbitMQBus(amqp_url=args.amqp_dsn)
        tasks.append(run_consumer(bus, store, args.vault_path, top_n=args.top_n))
    try:
        await asyncio.gather(*tasks)
    finally:
        if args.mode == "events":
            await bus.close()


def main() -> None:
    args = _build_parser().parse_args()
    ...
    asyncio.run(_run_async_mode(args))


if __name__ == "__main__":
    main()
```
For `apps/alerting`, `tasks` should gather THREE coroutines: `run_health_server(...)`, `run_consumer(bus, store, ntfy_token=...)`, and `run_digest_tick(store, bus, interval=3600)` (Pattern 4 in RESEARCH.md) — the digest tick is a new addition to this shape, not present in wiki_worker (wiki has no digest concept).

**Health server** (`apps/wiki/wiki_worker.py:118-129`) — copy verbatim, no changes needed:
```python
async def _handle_health(reader, writer) -> None:
    """Serve a liveness-only GET /health -> 200."""
    await reader.read(1024)
    body = b"OK"
    response = (
        b"HTTP/1.1 200 OK\r\n"
        b"Content-Length: " + str(len(body)).encode() + b"\r\n"
        b"Connection: close\r\n\r\n" + body
    )
    writer.write(response)
    await writer.drain()
    writer.close()


async def run_health_server(host: str = HEALTH_HOST, port: int = HEALTH_PORT) -> None:
    server = await asyncio.start_server(_handle_health, host, port)
    async with server:
        await server.serve_forever()
```

**CLI arg parsing pattern** (`apps/wiki/wiki_worker.py:240-264`) — mirror the `--dsn`/`--amqp-dsn`/`--health-host`/`--health-port` argparse block; add `--ntfy-url`/`--ntfy-token` (env-var-backed, same `os.environ.get(...)` default idiom) and `--digest-interval` (default 3600, `INFOTRIAGE_ALERTING_DIGEST_INTERVAL`).

---

### `apps/alerting/emitter.py` (service, event-driven)

**Analog:** `apps/wiki/wiki_worker.py` consumer section

**Dual routing-key consume on one queue** (adapted from `apps/wiki/wiki_worker.py:166-171` + RESEARCH.md Pattern 1):
```python
async def run_consumer(bus: RabbitMQBus, store, *, ntfy_token: str) -> None:
    await bus._ensure_connection()

    async def _handler(message) -> None:
        async with message.process():
            payload = json.loads(message.body.decode())
            item_id = message.headers["item_id"]
            await handle_trigger(item_id, payload, store, ntfy_token)

    await bus.consume("verdict.ready", _handler, prefetch_count=1, queue_name="q.alerting")
    await bus.consume("sab.published", _handler, prefetch_count=1, queue_name="q.alerting")
    await asyncio.Future()  # run forever
```
`bus.consume` signature (`libs/contracts/src/contracts/_bus_rabbitmq.py:215-226`, read this session):
```python
async def consume(
    self,
    routing_key: str,
    handler: Callable[[aio_pika.abc.AbstractIncomingMessage], Awaitable[Any]],
    prefetch_count: int = 1,
    queue_name: str | None = None,
) -> str:
```

**CRITICAL — payload must be joined against Store, not read off the wire message** (RESEARCH.md Pitfall 3, verified against `_events.py:24-34`): `VerdictReady` has no `pmesii` field. After confirming `cnr == "I"`, call:
```python
item = store.get_item(item_id)          # title, url, summary
enrichment = store.get_enrichment(item_id)  # pmesii, why
```
using the exact `get_item`/`get_enrichment` signatures below (Store Protocol dual-impl).

---

### `apps/alerting/dedupe.py` (utility, CRUD atomic upsert)

**Analog:** `libs/store/src/store/_postgres.py::put_enrichment` (lines 327-363, read in full)

**ON CONFLICT idiom to adapt for `DO NOTHING RETURNING`:**
```python
# libs/store/src/store/_postgres.py:338-363 (put_enrichment, existing DO UPDATE variant)
self._conn.execute(
    """
    INSERT INTO infotriage.enrichment
        (item_id, ccir, cnr, score, bucket, why, pmesii, tessoc)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (item_id) DO UPDATE SET
        ccir   = EXCLUDED.ccir, ...
    """,
    (item_id, fields.get("ccir"), ...),
)
self._conn.commit()
```
Adapt to dedupe's `DO NOTHING ... RETURNING dedupe_id` shape (RESEARCH.md Pattern 2):
```python
row = conn.execute(
    """
    INSERT INTO infotriage.alert_state (dedupe_id, item_id, cnr_tier, fired_at)
    VALUES (%s, %s, %s, now())
    ON CONFLICT (dedupe_id) DO NOTHING
    RETURNING dedupe_id
    """,
    (dedupe_id, item_id, cnr_tier),
).fetchone()
conn.commit()
should_fire = row is not None
```
Requires `CREATE UNIQUE INDEX IF NOT EXISTS ... ON infotriage.alert_state (dedupe_id)` — same idiom as `enrichment_item_id_unique` in `006-enrichment.sql:17-18`.

**Rollback-on-read pattern** (avoid idle-in-transaction, `_postgres.py:376`):
```python
self._conn.rollback()  # end read txn — avoid idle-in-transaction
```
Apply after any SELECT-only throttle/digest query in `throttle.py`.

---

### `apps/alerting/throttle.py` (utility, batch/transform)

**Analog:** read-query shape from `_postgres.py::get_enrichment` (lines 365-379); no exact sliding-window analog exists in-repo — this is genuinely new engineering per RESEARCH.md, but the query idiom (bind params, `.fetchone()`/`.fetchall()`, explicit rollback on read) must match `_postgres.py` conventions exactly:
```python
count_60s = conn.execute(
    "SELECT count(*) FROM infotriage.alert_state "
    "WHERE fired_at > now() - interval '60 seconds' AND suppressed = false"
).fetchone()[0]
```

---

### `apps/alerting/deep_link.py` (utility, transform)

**Analog:** `apps/brief/vault_writer.py` (418 lines; filename-derivation section read this session, lines ~108-112)

**Filename-safe_id derivation** (`apps/brief/vault_writer.py:108-112`):
```python
item_id = item.get("item_id", "unknown")
# Sanitize filename: remove special characters
safe_id = re.sub(r"[^\w\-]", "", str(item_id))
filename = f"{safe_id}.md"
```
Reuse verbatim — SPEC R5's acceptance criterion is literal path-match with the vault-writer's output. Since `item_id` is a sha256 hex digest (`\w`-only), `safe_id == item_id`, so the regex is a correctness guard, not a transform:
```python
import re
def obsidian_note_filename(item_id: str) -> str:
    safe_id = re.sub(r"[^\w\-]", "", str(item_id))
    return f"{safe_id}.md"
```

---

### `libs/store/sql/011-alert-state.sql` (migration)

**Analog:** `libs/store/sql/006-enrichment.sql` (31 lines, read in full)

Idempotency idiom to copy exactly (file header comment + statement shape):
```sql
-- CREATE UNIQUE INDEX IF NOT EXISTS is the correct idempotent pattern; ON CONFLICT (item_id)
-- honours a UNIQUE INDEX on the column, not only a named constraint.
CREATE UNIQUE INDEX IF NOT EXISTS enrichment_item_id_unique
    ON infotriage.enrichment (item_id);

ALTER TABLE infotriage.enrichment ADD COLUMN IF NOT EXISTS ccir   TEXT;
ALTER TABLE infotriage.enrichment ADD COLUMN IF NOT EXISTS score  INT CHECK (score BETWEEN 0 AND 10);
```
Migration numbering: next free slot confirmed `011-*.sql` (007 discipline, 008 translation-cache, 009 body, 010 backfill — per CONTEXT.md). Plain TEXT columns, no Postgres ENUM types anywhere in this schema (RESEARCH.md recommendation) — use TEXT + app-level validation for any `status`/`suppressed` column, matching `bucket`/`ccir`/`cnr` convention.

---

### `libs/contracts/src/contracts/_bus_rabbitmq.py` (modify `ROUTING_KEY_TO_QUEUE`)

**Analog:** same file, existing dict (read this session)

**Current state:**
```python
ROUTING_KEY_TO_QUEUE: dict[str, list[str]] = {
    "item.ingested": ["q.triage"],
    "verdict.ready": ["q.brief", "q.wiki"],
    "sab.published": ["q.notify"],
    "feed.unhealthy": ["q.ops"],
}
```
**Required change** (RESEARCH.md Pattern 1, `q.wiki` fan-out precedent from commit `ec52292`):
```python
ROUTING_KEY_TO_QUEUE: dict[str, list[str]] = {
    "item.ingested": ["q.triage"],
    "verdict.ready": ["q.brief", "q.wiki", "q.alerting"],   # ADD q.alerting
    "sab.published": ["q.notify", "q.alerting"],             # ADD q.alerting
    "feed.unhealthy": ["q.ops"],
}
```

---

### `libs/contracts/src/contracts/_item.py` (add `body: Optional[str]`)

**Analog:** same file (60 lines, read in full)

**Current fields (lines 32-34):**
```python
# Content fields
summary: Optional[str] = None
body_ref: Optional[str] = None
```
**Required addition (D-04):**
```python
summary: Optional[str] = None
body: Optional[str] = None   # NEW — full text where source has one; NULL, never ""
body_ref: Optional[str] = None
```
No changes needed to the `id` computed field (`_item.py:52-60`) — `id` hashes `source_type`/`url`/`title` only, `body` does not participate in dedup identity.

---

### `libs/store/src/store/_postgres.py::put_item`/`get_item` (add `body` column)

**Analog:** same file, existing INSERT/SELECT (lines 148-233, read in full)

**Current INSERT column list (`_postgres.py:164-196`):**
```python
self._conn.execute(
    """
    INSERT INTO infotriage.articles
        (id, source, source_type, url, title, ts, lang, summary, body_ref, payload, discipline, admiralty_reliability)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (id) DO UPDATE SET
        source                  = EXCLUDED.source,
        ...
        body_ref                = EXCLUDED.body_ref,
        ...
    """,
    (item.id, item.source, item.source_type, item.url, item.title, item.ts, item.lang,
     item.summary, item.body_ref, Jsonb(item.payload), item.discipline, item.admiralty_reliability),
)
```
Insert `body` into both the column list and VALUES tuple immediately after `summary` (before `body_ref`), and add `body = EXCLUDED.body` to the `DO UPDATE SET` clause — mirrors exactly how `009-articles-body.sql` already added the DDL; this is the write-path half of that migration's stated gap ("producer-side body UPSERT is the gap this sub-wave closes").

**Current SELECT (`_postgres.py:210-233`):**
```python
row = self._conn.execute(
    """
    SELECT source, source_type, url, title, ts, lang, summary, body_ref, payload, discipline, admiralty_reliability
    FROM infotriage.articles
    WHERE id = %s
    """,
    (item_id,),
).fetchone()
...
return Item(
    source=row["source"], ..., summary=row["summary"], body_ref=row["body_ref"], ...
)
```
Add `body` to the column list and to the `Item(...)` constructor call. **Do NOT let `apps/alerting`'s own queries select `articles.body`** — RESEARCH.md Pitfall 4 / SPEC P2/AC8 forbid this explicitly; only `_postgres.py::get_item` itself (used by other apps like `apps/brief`) should read it.

---

### `libs/store/src/store/_inmemory.py::put_item`/`get_item` (parity)

**Analog:** same file, existing dict-store shape (lines 89-112, read in full)

```python
def put_item(self, item: Item) -> None:
    """Upsert by item.id — last-write-wins (mirrors ON CONFLICT DO UPDATE)."""
    self._items[item.id] = item

def get_item(self, item_id: str) -> Item | None:
    """Return Item or None on miss — never raises on absence."""
    return self._items.get(item_id)
```
No code change required here — `InMemoryStore` stores the whole `Item` object, so adding `body` to `Item` automatically flows through with zero edits (parity is free). This mirrors the `put_enrichment`/`get_enrichment` dual-impl precedent D-02 cites (`_inmemory.py:136-153` — dict literal mirrors `_postgres.py`'s column list one-for-one, whereas `put_item`/`get_item` don't even need that because they store the model directly).

---

### `apps/ingest-{gmail,imap,youtube,telegram,barentswatch,acled,obsidian}/*.py` (set `item.body`)

**Analog:** `apps/ingest-gmail/gmail_ingest.py:104-113` (read this session) — the `Item(...)` construction site every adapter has one of:
```python
item = Item(
    source="gmail",
    source_type="gmail",
    url=f"gmail://message/{msg_id}",
    title=subject,
    ts=ts,
    lang="und",
    summary=snippet[:500],
)
```
**Required change per adapter:** add `body=full_text_or_none` where the adapter has full text available (e.g., full email body vs the 500-char `snippet`), leave `None` otherwise:
```python
item = Item(
    source="gmail",
    source_type="gmail",
    url=f"gmail://message/{msg_id}",
    title=subject,
    ts=ts,
    lang="und",
    summary=snippet[:500],
    body=full_body_text,   # NEW — None if not available; no size cap (SPEC R7)
)
```
No `persist_and_publish` call-site changes needed — confirmed at `libs/ingest_common/src/ingest_common/persist.py:18-48` (read this session): the function takes the already-constructed `Item` and calls `store.get_item`/`store.put_item` unconditionally; `body` rides through with zero signature changes. Do NOT add HTML sanitization or a char cap — RESEARCH.md Pitfall 1 flags this as a stale `12-PLAN.md` idea explicitly superseded by SPEC R7 ("no size cap (TEXT)").

---

### `apps/alerting/Dockerfile` + `apps/alerting/requirements.txt`

**Analog:** `apps/wiki/Dockerfile` + `apps/wiki/requirements.txt` (per RESEARCH.md Standard Stack — not re-read this session since RESEARCH.md already confirms exact pinned versions from these files)

`requirements.txt` should mirror `apps/wiki/requirements.txt` verbatim: `aio-pika>=9.6`, `psycopg[binary]>=3.3`, `pydantic>=2.0`, `httpx>=0.25`, `json-log-formatter>=1.1`, `PyYAML>=6.0`, `feedgen>=0.3.1` — possibly minus `fastapi`/`uvicorn` if the stdlib health server (Pattern above) is used instead of FastAPI.

## Shared Patterns

### Fail-closed startup on missing required config
**Source:** `apps/wiki/wiki_worker.py:269-278`
**Apply to:** `apps/alerting/alerting_worker.py` — extend the existing `--dsn`/`--amqp-dsn` checks with an `NTFY_TOKEN` check (SPEC R6):
```python
if not args.dsn:
    print("ERROR: --dsn or INFOTRIAGE_PG_DSN required", file=sys.stderr)
    sys.exit(1)
```

### Store Protocol dual-impl parity (Postgres + InMemory)
**Source:** `libs/store/src/store/_postgres.py:327-379` + `libs/store/src/store/_inmemory.py:136-153` (`put_enrichment`/`get_enrichment` pair)
**Apply to:** any new `alert_state` Store methods (`put_alert_state`/`get_alert_state`/throttle-count queries) — every new Store method needs both a `_postgres.py` SQL implementation and an `_inmemory.py` dict-based mirror with matching signatures and matching upsert/last-write-wins semantics.

### Read-transaction rollback (avoid idle-in-transaction)
**Source:** `libs/store/src/store/_postgres.py:218, 376`
```python
self._conn.rollback()  # end read txn — avoid idle-in-transaction
```
**Apply to:** every SELECT-only query in `dedupe.py`/`throttle.py` that doesn't write.

### Bind-param SQL only, never f-string
**Source:** `libs/store/src/store/_postgres.py:157` docstring ("Security (V5, T-02-01): all values via %s bind params; no f-string SQL"), consistently enforced across `put_item`/`put_enrichment`.
**Apply to:** all new SQL in `apps/alerting/dedupe.py`/`throttle.py`.

### asyncio.gather task composition for multi-mode services
**Source:** `apps/wiki/wiki_worker.py:280-305`
**Apply to:** `apps/alerting/alerting_worker.py` — gather health server + event consumer + hourly digest tick as three coroutines in one `asyncio.gather(...)` call, same shape wiki uses for health server + periodic/consumer.

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `apps/alerting/outbox.py` (retry/DLX delivery loop + ntfy httpx POST) | service | event-driven | No prior in-repo outbox/retry-to-DLX consumer exists; RESEARCH.md Pattern 5 recommends an in-process `for attempt, delay in [(1,1),(2,5)]` retry loop over the RabbitMQ TTL+DLX chain recipe — reasoned recommendation, not a shipped precedent. `httpx` usage itself is standard (`apps/opml_health`, `apps/ingest-gmail`, `apps/ingest-barentswatch`, `apps/dlq_consumer`, `apps/scheduler` all use it for outbound HTTP) but none of those implement a scheduled retry-then-DLX pattern. |
| `apps/ntfy/Dockerfile` bearer-token provisioning (`ntfy token add`) | config/bootstrap | — | Existing Dockerfile (ADR-018) only pre-bakes Basic Auth passwords via `ntfy user add`; token generation is fundamentally different (value is generated, not pre-chosen) and has no existing bake-in pattern to copy. RESEARCH.md Open Question 1 recommends a post-boot `docker exec` + operator-captured `.env` flow — new engineering, flagged for the planner as its own task. |

## Metadata

**Analog search scope:** `apps/wiki/`, `apps/brief/`, `apps/ingest-gmail/`, `libs/contracts/src/contracts/`, `libs/store/src/store/`, `libs/store/sql/`, `libs/ingest_common/src/ingest_common/`
**Files scanned:** 12 read directly this session (`_item.py`, `_events.py`, `006-enrichment.sql`, `009-articles-body.sql`, `_postgres.py` [put_item/get_item/put_enrichment/get_enrichment sections], `_inmemory.py` [put_item/get_item section], `wiki_worker.py` [CLI/main section], `gmail_ingest.py` [Item construction], `persist.py` [persist_and_publish]); 3 delegated to local model (`wiki_worker.py` full, `_bus_rabbitmq.py` full, `vault_writer.py` filename section)
**Pattern extraction date:** 2026-08-01
