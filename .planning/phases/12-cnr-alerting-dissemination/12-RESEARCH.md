# Phase 12: CNR alerting / dissemination - Research

**Researched:** 2026-08-01
**Domain:** Event-driven push notification service (RabbitMQ consumer → Postgres dedupe/throttle → ntfy HTTP push), bundled with producer-side body-field wiring across 7 ingest adapters
**Confidence:** HIGH (architecture/patterns — all derived from live codebase); MEDIUM (ntfy bearer-token provisioning — new engineering, no prior in-repo precedent)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Carried forward from Turn-1 (2026-07-23) — still binding**
- **T1-01:** Workflow shape `INTEGRATED-SUB-WAVE` — Phase 13 body wiring ships as sub-wave (f) inside this phase. Reversibility: one-way — HANDOFF.json anchors `phase_12_phase_13_depend.verdict`; downstream phases assert body population only after Phase 12 ships.
- **T1-02:** ADR-016 supersedes unrecoverable ADR-004 (airgap doctrine: local-LLM-only + read-only ingest).
- **T1-03:** ADR-015 D1–D5 locked (CAT I only; ntfy single channel; 7-field payload; 3-tier throttle; DLX+outbox).

**Emitter runtime shape**
- **D-01:** Standalone `apps/alerting` service in its own container with its own `/health` endpoint on a 22xxx port — same pattern as wiki/brief/triage. Gets its own durable queue `q.alerting` bound to BOTH `verdict.ready` and `sab.published` via the existing widened `ROUTING_KEY_TO_QUEUE` list mechanism (`libs/contracts/src/contracts/_bus_rabbitmq.py`, the `q.wiki` fan-out precedent from commit `ec52292`). Reversibility: costly.

**Dedupe/throttle state store**
- **D-02:** New Postgres table `infotriage.alert_state` via migration `011-alert-state.sql`, accessed through the existing Store protocol (both PostgresStore and InMemoryStore implement — parity like `recall_items`). Columns cover `dedupe_id` PK, `fired_at`, suppression/digest bookkeeping. 24h dedupe TTL = `WHERE fired_at > now() - interval '24 hours'`; sliding windows computed from `fired_at` timestamps. No new infra (no Redis). Reversibility: costly.

**Digest alert mechanics**
- **D-03:** The alerting service runs its own asyncio hourly tick (no scheduler-container coupling, no piggyback-on-next-alert). If suppressed alerts exist since the last digest: publish exactly ONE message to `cnr-cat-i` — title `⚠ N suppressed CAT I alerts`, body grouped by PMESII tag, each entry carrying item title + `obsidian://` link + `alert_id`. An empty hour emits nothing.

**Body flow into articles.body (sub-wave f)**
- **D-04:** Add optional `body: Optional[str]` to the `Item` contract (`libs/contracts/src/contracts/_item.py`); `put_item` UPSERTs it into `articles.body` (NULL when absent — never empty string, per SPEC edge). Adapters with full text set the one field; everything flows through the existing `persist_and_publish` path. InMemory/Postgres parity required. Reversibility: costly — Item is the shared contract every app imports.

### Claude's Discretion
- `alert_state` exact column set, index choice, and the sliding-window query shape.
- Alerting service port number (next free 22xxx), Dockerfile layout, healthcheck wiring.
- Token provisioning mechanics (env var names, ntfy user/token bootstrap script) — within SPEC R6's fail-closed constraint.
- Digest message formatting details beyond the grouped structure in D-03.

### Deferred Ideas (OUT OF SCOPE)
- CAT II tier alerting and full-tier re-baseline — future phase; must cite 12-CONTEXT/12-SPEC as baseline.
- ntfy iOS/Android app pairing docs for the operator — ops docs, not this phase.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ADR-003 | Intelligence-cycle framework (Direction→Collection→Processing→Analysis→Production→**Dissemination**); this phase implements `DI-5` ("Push notifications on CAT I") from `REQUIREMENTS.md` §Dissemination | Architecture Patterns + Standard Stack below implement DI-5 end-to-end without touching Direction/Collection/Processing/Analysis stages. See also the 8 detailed requirements (R1–R8) locked in `12-SPEC.md`, which supersede the coarser ADR-003 pointer for planning purposes — plan against R1–R8, not a re-derivation of ADR-003. |
| R1 (SPEC) | CAT I alert emission, exactly-once across dual triggers | Architecture Patterns §1 (event topology), §2 (atomic dedupe) |
| R2 (SPEC) | Dedupe with 24h TTL | Architecture Patterns §2 |
| R3 (SPEC) | 3-tier sliding-window throttle + hourly digest | Architecture Patterns §3, §4 |
| R4 (SPEC) | Outbox + DLX, no alert lost | Architecture Patterns §5 |
| R5 (SPEC) | `obsidian://` deep link | Architecture Patterns §6; Common Pitfalls §3 |
| R6 (SPEC) | ntfy ACL + fail-closed token | Architecture Patterns §7; Common Pitfalls §2 (bearer-token gap) |
| R7 (SPEC) | Body UPSERT sub-wave (f), 7 adapters | Architecture Patterns §8 |
| R8 (SPEC) | SAB stays canonical, push is a pointer | Common Pitfalls §1, §4 |
</phase_requirements>

## Summary

Phase 12 is an event-driven consumer service, not a novel technology adoption — every primitive it needs (RabbitMQ fan-out queues, Postgres `ON CONFLICT` upsert-as-dedupe, `asyncio` periodic tick, FastAPI/stdlib `/health`, `httpx` HTTP client) is already live and battle-tested elsewhere in this codebase (`apps/wiki/wiki_worker.py`, `apps/opml_health/service.py`, `libs/store/src/store/_postgres.py::put_enrichment`). The correct approach is to clone these exact patterns into `apps/alerting/`, not to introduce new libraries or infrastructure. No new pip packages are required.

Three findings materially change how the emitter must be built, beyond what CONTEXT.md/SPEC.md already lock:

1. **`verdict.ready` does not carry `pmesii`.** `VerdictReady` (`libs/contracts/src/contracts/_events.py`) has no `pmesii` field, and `apps/triage/worker.py:339` publishes `payload.model_dump(mode="json")` — the exact typed model, nothing extra. `pmesii` only exists in `infotriage.enrichment` (Postgres). The emitter MUST call `store.get_enrichment(item_id)` (and `store.get_item(item_id)` for title/url/summary) after consuming either trigger event — it cannot build the 7-field payload from the wire message alone.
2. **`sab.published` is a batch event, not a per-item event, and its `item_refs` array is capped at the top 50 items by score** (`apps/brief/consumer.py:207-219`, `ORDER BY e.score DESC` then `[:50]`). A CAT I item with a low numeric `score` can fall outside that cap, meaning the `sab.published` trigger silently cannot see it. In the common case this is harmless (the `verdict.ready` trigger already fired and dedupe suppresses the `sab.published` no-op), but any plan that treats `sab.published` as an equally-reliable primary trigger is wrong — it is a fallback/second-look, not a guarantee.
3. **The already-shipped ntfy Dockerfile (`apps/ntfy/Dockerfile`, ADR-018) only pre-bakes `ntfy user add` (username/password → Basic Auth).** SPEC R6 requires a **bearer token**. `ntfy token add <user>` is a separate command producing a `tk_`-prefixed 32-char token, generated at runtime (not something the operator can pre-select and pass as a BuildKit secret the same way passwords were). Provisioning this token is new engineering for this phase (Claude's Discretion per CONTEXT.md, but genuinely unsolved by any existing pattern in the repo) — see Common Pitfalls §2 for a concrete recommended approach.

**Primary recommendation:** Build `apps/alerting/` as a fourth instance of the `wiki_worker.py`/`opml_health/service.py` shape (asyncio consumer + periodic tick + stdlib/FastAPI health server, PostgresStore + RabbitMQBus, `contracts.setup_logging`), add `011-alert-state.sql` following the exact `ON CONFLICT` idiom already used in `put_enrichment`, and treat ntfy bearer-token generation as new, carefully-tested bootstrap code layered onto the existing ADR-018 Dockerfile — not a copy of the stale `12-PLAN.md` draft (see Common Pitfalls §1).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Consume `verdict.ready` / `sab.published` | Backend / API (message consumer) | — | New `apps/alerting` service, same tier as `apps/wiki`, `apps/brief` |
| Dedupe + throttle state | Database / Storage (Postgres) | Backend (query logic) | `infotriage.alert_state` table; queries live in `apps/alerting`, not a new tier |
| Outbox / retry / DLX | Backend (RabbitMQ topology + retry loop) | Database (audit row on terminal failure) | Same RabbitMQ broker already used project-wide (ADR-007); no new broker |
| Push delivery | External service (ntfy container, local-only) | — | `apps/alerting` is an HTTP client to `infotriage-ntfy:80`; ntfy itself is already shipped (sub-wave a) |
| Deep link resolution | Client (Obsidian app on operator's Mac) | — | `obsidian://` URI is opened by the OS, not resolved server-side; `apps/alerting` only constructs the string |
| Body UPSERT (sub-wave f) | Backend (7 ingest adapters) | Database (`articles.body` column) | Producer-side write via existing `persist_and_publish` → `put_item` path; zero alerting-tier involvement (P3/AC8 isolation) |
| SAB canonical artifact | Backend (`apps/brief`) | — | Unchanged by this phase; alerting only reads enrichment/item rows, never writes SAB |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `aio-pika` | `>=9.6` (pinned in every `apps/*/requirements.txt`) | RabbitMQ async client — consume `q.alerting`, manage outbox topology | Already the project's sole AMQP client; `RabbitMQBus` wraps it (`libs/contracts/src/contracts/_bus_rabbitmq.py`) |
| `psycopg[binary]` | `>=3.3` | Postgres driver for `alert_state` table access | Same driver as every other Store-backed service |
| `pydantic` | `>=2.0` | `contracts.setup_logging`/`Item`/event models import path | Transitive dep of `contracts`; matches every app's requirements.txt |
| `httpx` | `>=0.25` | HTTP client to POST to ntfy's REST API | Already used for outbound HTTP in `apps/opml_health`, `apps/ingest-gmail`, `apps/ingest-barentswatch`, `apps/dlq_consumer`, `apps/scheduler` |
| `json-log-formatter` | `>=1.1` | `contracts.setup_logging` transitive dep | Required by every service per Phase 7 dep-superset test |
| `PyYAML` | `>=6.0` | `contracts` module-level import | Required by every service that imports `contracts` (07-03/07-04 lesson) |
| `feedgen` | `>=0.3.1` | `store/__init__.py` module-level import of `_atom.render_atom` | Required transitively even though `apps/alerting` never calls it — same as `apps/wiki`, `apps/triage` |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `fastapi` + `uvicorn` | `>=0.104` / `>=0.24` | `/health` endpoint | Only if the emitter needs a JSON `/report`-style endpoint (opml_health precedent); the stdlib `asyncio.start_server` health server (`wiki_worker.py` pattern) is simpler and sufficient for a liveness-only check — **prefer stdlib unless a richer status payload is wanted** |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Postgres `alert_state` table (D-02, locked) | Redis (sorted sets for sliding windows) | Redis is the textbook sliding-window tool, but D-02 explicitly rejects it ("No new infra (no Redis)"). Postgres `WHERE fired_at > now() - interval` scans are adequate at the stated ≤5 CAT I/day volume. |
| `httpx` sync/async POST to ntfy | `requests` | `requests` has zero footprint in this codebase; `httpx` is already the vetted async-capable HTTP client — use it for consistency, not `requests`. |
| Hand-rolled RabbitMQ TTL+DLX retry chain | `aio-pika`'s no built-in retry helper (there isn't one) | No off-the-shelf outbox/retry library is used anywhere in this repo; the DLX pattern is the project-standard hand-built primitive (ADR-007) — this is the one "hand-roll" that is explicitly sanctioned by prior architecture, not an exception to Don't-Hand-Roll below. |

**Installation:** No new packages. `apps/alerting/requirements.txt` should mirror `apps/wiki/requirements.txt` verbatim (all 7 Core-table entries above), possibly minus `fastapi`/`uvicorn` if the stdlib health server is chosen.

**Version verification:** All versions above were read directly from committed `apps/wiki/requirements.txt` and `apps/opml_health/requirements.txt` in this repo — these are the project's own pinned floors, already running in production. `[VERIFIED: codebase]` — no external registry check needed since nothing new is being installed.

## Package Legitimacy Audit

**No new external packages are introduced by this phase.** Every dependency `apps/alerting/requirements.txt` needs already ships in `apps/wiki/requirements.txt` and/or `apps/opml_health/requirements.txt` and is running in production today. The Package Legitimacy Gate protocol (registry/postinstall-script checks) applies to *newly introduced* packages; since none are introduced, the gate is not applicable here.

| Package | Registry | Status in this repo | Verdict | Disposition |
|---------|----------|----------------------|---------|-------------|
| `aio-pika`, `psycopg[binary]`, `pydantic`, `httpx`, `json-log-formatter`, `PyYAML`, `feedgen`, `pgvector` | PyPI | Already pinned + running in `apps/wiki`, `apps/opml_health`, `apps/triage` | N/A — reused, not newly introduced | Approved (reuse existing pins verbatim) |

**Packages removed due to [SLOP] verdict:** none.
**Packages flagged as suspicious [SUS]:** none.

## Architecture Patterns

### System Architecture Diagram

```
 apps/triage/worker.py            apps/brief/consumer.py
        │  publish                        │  publish
        │  "verdict.ready"                │  "sab.published"
        ▼                                 ▼
 ┌─────────────────────────────────────────────────────┐
 │  infotriage.events (topic exchange, RabbitMQ)        │
 └─────────────────────────────────────────────────────┘
        │ fan-out bind                    │ fan-out bind
        ▼                                 ▼
 ┌───────────────────────────────────────────────────────┐
 │  q.alerting  (durable, DLX-wired, NEW — bound to BOTH  │
 │  routing keys, same list-fan-out pattern as q.wiki)    │
 └───────────────────────────────────────────────────────┘
                        │ consume (apps/alerting/emitter.py)
                        ▼
         ┌───────────────────────────────────────┐
         │ 1. Filter: cnr == "I"? else ack+drop   │
         │ 2. Resolve item_id → title/url/summary │───► Store.get_item()
         │    → pmesii/why                        │───► Store.get_enrichment()
         │ 3. dedupe_id = sha256(item_id|cnr)[:16] │
         │ 4. Atomic INSERT..ON CONFLICT DO        │───► infotriage.alert_state
         │    NOTHING RETURNING dedupe_id          │      (Postgres, 011-alert-state.sql)
         │    → no row returned = suppress, ack    │
         │ 5. Throttle check (60s/10min sliding    │───► COUNT(*) WHERE fired_at > now()-interval
         │    windows over alert_state)            │
         │    → over cap: mark suppressed, ack     │
         │ 6. Build 7-field payload                │
         │ 7. Enqueue to outbox (ack verdict.ready  │
         │    ONLY after this write succeeds)       │
         └───────────────────────────────────────┘
                        │
                        ▼
         ┌───────────────────────────────────────┐
         │ outbox delivery loop: POST to ntfy      │
         │  200 OK → mark delivered                │
         │  fail → retry 1s, retry 5s, then         │
         │  route to outbox.dlx.queue + audit row   │
         └───────────────────────────────────────┘
                        │ HTTP POST (Bearer token)
                        ▼
         ┌───────────────────────────────────────┐
         │ infotriage-ntfy (127.0.0.1:22070)       │
         │ topic: cnr-cat-i                        │
         └───────────────────────────────────────┘
                        │ push
                        ▼
              Operator's ntfy client (phone/desktop)
              tap → obsidian://open?vault=...&file=<item_id>.md

 (parallel, orthogonal) hourly asyncio tick in the same service:
         alert_state WHERE suppressed AND not yet digested
                        │
                        ▼
         one grouped-by-pmesii digest message → same outbox path
```

### Recommended Project Structure
```
apps/alerting/
├── Dockerfile           # clone of apps/wiki/Dockerfile pattern (python:3.12-slim, non-root user)
├── requirements.txt     # subset of apps/wiki/requirements.txt (see Standard Stack)
├── emitter.py           # consume q.alerting, filter CAT I, build payload, call outbox
├── outbox.py            # enqueue/retry/DLX delivery loop + ntfy httpx client
├── dedupe.py            # dedupe_id formula + atomic check-and-set query
├── throttle.py          # sliding-window count queries + PMESII-grouped digest builder
├── deep_link.py         # obsidian:// URI builder — MUST reuse the exact filename logic
│                         # from apps/brief/vault_writer.py::write_item_obsidian (safe_id = item_id)
└── alerting_worker.py   # CLI entrypoint: --mode {events} + asyncio hourly tick + /health server
                          # (mirrors apps/wiki/wiki_worker.py's _build_parser/_run_async_mode shape)
```

### Pattern 1: Multi-queue fan-out binding (add `q.alerting`)
**What:** A single routing key can be bound to several independently-declared durable queues; each bound queue gets its own copy of the message.
**When to use:** Exactly D-01's requirement — `q.alerting` must receive both `verdict.ready` and `sab.published` without disturbing `q.brief`/`q.wiki`/`q.notify` consumers.
**Example:**
```python
# Source: libs/contracts/src/contracts/_bus_rabbitmq.py (existing, live code)
ROUTING_KEY_TO_QUEUE: dict[str, list[str]] = {
    "item.ingested": ["q.triage"],
    "verdict.ready": ["q.brief", "q.wiki", "q.alerting"],   # ADD q.alerting here
    "sab.published": ["q.notify", "q.alerting"],             # ADD q.alerting here
    "feed.unhealthy": ["q.ops"],
}
```
Consume with an explicit `queue_name` override (same as `apps/wiki/wiki_worker.py:166`):
```python
await bus.consume("verdict.ready", handler, prefetch_count=1, queue_name="q.alerting")
await bus.consume("sab.published", handler, prefetch_count=1, queue_name="q.alerting")
```
`[VERIFIED: codebase]` — `_bus_rabbitmq.py` already documents this exact fan-out mechanism using `q.wiki` as the precedent (see its module docstring, lines 13-17).

### Pattern 2: Atomic dedupe via `INSERT ... ON CONFLICT DO NOTHING RETURNING`
**What:** The existing `put_enrichment` uses `ON CONFLICT (item_id) DO UPDATE`. For dedupe (not upsert), the correct idiom is `DO NOTHING RETURNING dedupe_id` — a row is returned only for the caller that "won" the race.
**When to use:** SPEC R1's "atomic check-and-set, no race window" between the `verdict.ready` and `sab.published` triggers for the same item.
**Example:**
```python
# Pattern derived from libs/store/src/store/_postgres.py::put_enrichment's
# ON CONFLICT idiom (verified in this repo), adapted to DO NOTHING for dedupe semantics.
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
should_fire = row is not None   # None → another trigger already won; suppress
```
Requires a `UNIQUE INDEX` on `alert_state.dedupe_id` (same `CREATE UNIQUE INDEX IF NOT EXISTS` idiom as `006-enrichment.sql`'s `enrichment_item_id_unique`) — this is what makes `ON CONFLICT` legal.
`[VERIFIED: codebase — idiom extended from libs/store/src/store/_postgres.py:338-363]`

For the 24h TTL re-alert case (R2: "after 24h TTL expiry → may alert again"), the `dedupe_id` itself does not change (same formula), so a second `INSERT` after 24h must succeed. Two implementation choices, both valid — planner's discretion (D-02 leaves column/index shape open):
- **(a)** No uniqueness constraint at all on `dedupe_id`; instead, the check-and-set query becomes `SELECT 1 FROM alert_state WHERE dedupe_id = %s AND fired_at > now() - interval '24 hours' FOR UPDATE` inside an explicit transaction, then `INSERT` if no row found. Requires row-level locking to stay race-free.
- **(b)** Keep the `UNIQUE INDEX` but scope it to `(dedupe_id)` where a companion cleanup job (or the throttle query itself) treats rows older than 24h as logically expired and a fresh `INSERT ... ON CONFLICT (dedupe_id) DO UPDATE SET fired_at = now() WHERE alert_state.fired_at <= now() - interval '24 hours' RETURNING dedupe_id` re-arms it — `DO UPDATE ... WHERE` makes the conflict conditional, so a fresh-within-24h conflict returns no row (suppress) but a stale one updates and returns a row (re-fire).

Option (b) is the cleaner single-query answer and keeps the injected-clock test (SPEC R2's acceptance criterion) simple to drive.

### Pattern 3: Sliding-window throttle via timestamp scan
**What:** Count rows in `alert_state` within a rolling window, not a fixed clock bucket.
**When to use:** SPEC R3's "sliding windows — no fixed-clock burst loophole."
**Example:**
```python
count_60s = conn.execute(
    "SELECT count(*) FROM infotriage.alert_state "
    "WHERE fired_at > now() - interval '60 seconds' AND suppressed = false"
).fetchone()[0]
if count_60s >= 5:
    # 6th+ alert in the window: mark suppressed=true, do NOT push, ack the message
    ...
```
Same pattern for the 10-minute/10-count tier. Both checks run before the outbox enqueue (Pattern 2 already vetoed by dedupe first, per SPEC's stated priority ordering: dedupe → throttle → digest).

### Pattern 4: Hourly asyncio tick for the digest (no scheduler container)
**What:** A `while True: ... await asyncio.sleep(interval)` loop running inside the same service process — no cron, no `apscheduler`, no coupling to `apps/scheduler`.
**When to use:** D-03's explicit "own asyncio hourly tick."
**Example:**
```python
# Source: apps/wiki/wiki_worker.py::run_periodic (existing, live code) — same shape,
# different query (SELECT suppressed rows since last digest instead of top-N entities)
async def run_digest_tick(store, bus, *, interval: int = 3600) -> None:
    while True:
        try:
            suppressed = await asyncio.to_thread(get_undigested_suppressed, store)
            if suppressed:
                await asyncio.to_thread(publish_digest, store, bus, suppressed)
        except Exception as exc:
            log.error("digest tick failed: %s", exc)
        await asyncio.sleep(interval)
```
Run this as one of the tasks in `asyncio.gather(...)` alongside the health server and the event consumer, exactly like `wiki_worker.py::_run_async_mode` gathers `run_health_server` + `run_periodic`/`run_consumer`.
`[VERIFIED: codebase — apps/wiki/wiki_worker.py:86-113]`

### Pattern 5: RabbitMQ outbox retry via TTL + DLX chaining (1s, 5s, then terminal)
**What:** RabbitMQ has no native "retry after N seconds" primitive; the standard recipe is a per-attempt "wait" queue with `x-message-ttl` whose own dead-letter target is the retry point, chained N times, then routed to a terminal queue.
**When to use:** SPEC R4's exact retry schedule (1s, then 5s, then `outbox.dlx.queue`).
**Example:**
```python
# New topology, additive to the existing infotriage.dlx/infotriage.dlq pair —
# do NOT reuse the global DLQ for this; SPEC explicitly names outbox.dlx.queue
# as the alerting-specific terminal queue with its own audit row on landing.
await channel.declare_exchange("outbox.retry.exchange", aio_pika.ExchangeType.DIRECT, durable=True)
await channel.declare_queue(
    "outbox.wait.1s", durable=True,
    arguments={
        "x-message-ttl": 1000,
        "x-dead-letter-exchange": "outbox.retry.exchange",
        "x-dead-letter-routing-key": "retry",
    },
)
# ... "outbox.wait.5s" with x-message-ttl=5000, same DLX target ...
await channel.declare_queue("outbox.dlx.queue", durable=True)  # terminal, no further DLX
```
The alerting service's own retry loop is the simpler alternative and is what the SPEC's phrasing ("Emitter acks verdict.ready only after successful outbox enqueue... ntfy-down → 3 attempts → DLX") most naturally supports: **an in-process retry loop with `await asyncio.sleep(1)` then `await asyncio.sleep(5)` between `httpx` POST attempts, writing to `outbox.dlx.queue` (a plain durable queue, published to directly — no TTL/DLX chain needed) only on the 3rd failure** is simpler, has no 406-topology-mismatch risk, and satisfies every SPEC AC (`ntfy dead → 1s/5s retries → outbox.dlx.queue + audit row`) without introducing the TTL+DLX chain's extra queues. **Recommend the in-process retry loop over the RabbitMQ TTL/DLX chain** — reserve the DLX-chain recipe only if the planner decides retries must survive an `apps/alerting` process restart mid-backoff (SPEC does not require this; "broker outage relies on unacked redelivery" already covers the broker-down case via the existing DLX-first `q.alerting` declaration from Pattern 1).
`[ASSUMED — TTL+DLX chain recipe is a well-known RabbitMQ pattern (CITED via general RabbitMQ documentation), not something already implemented in this codebase; the in-process alternative is a same-session reasoned recommendation, not verified against a shipped precedent]`

### Pattern 6: `obsidian://` deep link — reuse the vault-writer's exact filename logic
**What:** `apps/brief/vault_writer.py::write_item_obsidian` writes each item to `<vault>/<safe_id>.md` where `safe_id = re.sub(r"[^\w\-]", "", item_id)`. Since `item_id` is a lowercase sha256 hex digest (`\w`-only), `safe_id == item_id` — the filename is just `<item_id>.md`.
**When to use:** SPEC R5's acceptance criterion is literally "matches the vault-writer's note path for the item" — get this wrong and the deep link 404s in Obsidian even though the note exists.
**Example:**
```python
# Source: apps/brief/vault_writer.py:78-98 (existing, live code) — filename derivation
import re
def obsidian_note_filename(item_id: str) -> str:
    safe_id = re.sub(r"[^\w\-]", "", str(item_id))
    return f"{safe_id}.md"

def obsidian_deep_link(item_id: str, vault_name: str) -> str:
    # obsidian:// URIs use the vault's display name (not filesystem path) for `vault=`
    from urllib.parse import quote
    return f"obsidian://open?vault={quote(vault_name)}&file={quote(obsidian_note_filename(item_id))}"
```
`vault_name` is not currently exposed as a distinct config value anywhere in the repo (`INFOTRIAGE_VAULT_PATH` is a filesystem path, e.g. `data/obsidian`, not the Obsidian-registered vault display name — Obsidian identifies vaults by folder basename by default). Plan to add an explicit `INFOTRIAGE_OBSIDIAN_VAULT_NAME` env var (or derive it as `Path(INFOTRIAGE_VAULT_PATH).name`) — **this is a genuine open item, not covered by any existing constant.** `[ASSUMED — Obsidian's URI vault-name resolution behavior is documented upstream (obsidian.md/help/Obsidian+URI) but not verified against this project's actual vault registration]`

### Pattern 7: Fail-closed startup on missing token (SPEC R6)
**What:** Refuse to start (non-zero exit, stderr message) rather than starting in a degraded/unauthenticated state.
**When to use:** Emitter startup when `NTFY_TOKEN` (or whatever env var name is chosen) is unset or empty.
**Example:**
```python
# Same fail-closed shape already used in wiki_worker.py:270-278 for --dsn/--amqp-dsn
ntfy_token = os.environ.get("NTFY_TOKEN", "")
if not ntfy_token:
    print("ERROR: NTFY_TOKEN required (bearer token for cnr-cat-i publish)", file=sys.stderr)
    sys.exit(1)
```
`[VERIFIED: codebase pattern — apps/wiki/wiki_worker.py:269-278]`

### Pattern 8: Producer-side body UPSERT (sub-wave f) — the SPEC-locked, narrow shape
**What:** D-04 is deliberately narrow: add `body: Optional[str]` to `Item`, let it ride the existing `persist_and_publish` → `put_item` path. **Do not** re-implement the elaborate per-adapter HTML-sanitization/10,000-char-cap scheme from the stale `12-PLAN.md` draft (see Common Pitfalls §1 — that plan predates SPEC.md and directly contradicts SPEC R7's "no size cap (TEXT)... backstopped by a >1MB transcript test").
**Example:**
```python
# libs/contracts/src/contracts/_item.py — add one field
class Item(BaseModel):
    ...
    summary: Optional[str] = None
    body: Optional[str] = None   # NEW — full text where source has one; NULL, never ""
    body_ref: Optional[str] = None
```
```python
# Each of the 7 adapters (apps/ingest-{gmail,imap,youtube,telegram,barentswatch,acled,obsidian})
# sets item.body = <full text> where available, leaves it None otherwise. No adapter-specific
# sanitization/truncation logic is required by SPEC R7 — TEXT columns have no Postgres size cap.
item = Item(..., body=full_text_or_none)
await persist_and_publish(store, bus, item)   # unchanged call site — body rides through
```
`libs/store/src/store/_postgres.py::put_item`'s INSERT column list and `ON CONFLICT DO UPDATE` clause both need the new `body` column added (mirrors how `009-articles-body.sql` already added the DDL — this sub-wave is the write path, not new DDL). `libs/store/src/store/_inmemory.py::put_item`/`get_item` need the same field for parity (matches the `recall_items`-style dual-impl precedent D-02 cites).
`[VERIFIED: codebase — libs/store/sql/009-articles-body.sql already documents "producer-side body UPSERT is the gap this sub-wave closes"]`

### Anti-Patterns to Avoid
- **Reading `articles.body` anywhere in the alerting path.** SPEC P2 (`sab_excerpt` must never be sourced from `articles.body`) and AC8 ("alerting tests pass with `articles.body` NULL for all rows") both forbid this. `sab_excerpt` must come from `enrichment.why` / `Item.summary`, capped at 500 chars — the same fields the scorer already reads (title + summary[:512], P3).
- **Treating `sab.published`'s `item_refs` as a complete/reliable CAT I item list.** It is top-50-by-score only (see Summary finding 2). Use it only as a dedupe-suppressed second look, never as the sole source of truth for "did this CAT I item get an alert."
- **Reusing the global `infotriage.dlq` for alerting failures.** SPEC explicitly names a distinct `outbox.dlx.queue`; conflating it with the shared broker-wide DLQ would make alerting failures invisible among unrelated poison-message noise from other services.
- **Piggybacking the digest tick on the next alert event** (D-03 explicitly rules this out) or on `apps/scheduler` (adds a cross-container coupling D-03 also rules out).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Idempotent dedupe under concurrent writers | A Python-side in-memory `set()` or lock, or a "check then insert" two-step (race-prone) | Postgres `INSERT ... ON CONFLICT ... RETURNING` (Pattern 2) | Atomic at the database level; the existing `put_enrichment` and `RabbitMQBus.publish`'s own `_seen` set (in-process only, not durable) are NOT sufficient for a cross-restart, cross-trigger dedupe requirement |
| Sliding-window rate limiting | A custom token-bucket implementation, or a Redis-backed limiter library | Direct `COUNT(*) WHERE fired_at > now() - interval` scan (Pattern 3) | At ≤5 CAT I/day the naive scan is O(rows-in-window), trivially fast; D-02 explicitly forbids adding Redis |
| HTTP retry-with-backoff to ntfy | A generic retry library (`tenacity`, `backoff`) — not currently a project dependency | A 6-line `for attempt, delay in [(1,1),(2,5)]:` loop (Pattern 5) | SPEC's retry schedule is fixed (1s, 5s, 2 retries then terminal) — a generic exponential-backoff library is overkill for a hard-coded 2-step schedule and would be the first new pip dependency this phase introduces for no real benefit |
| Obsidian URI construction | A bespoke Obsidian API client library | Plain `urllib.parse.quote` + string formatting (Pattern 6) | `obsidian://` is a documented, stable URI scheme; no SDK exists or is needed |

**Key insight:** Every hard problem in this phase (exactly-once delivery, rate limiting, retry) already has a project-native, already-vetted-in-production answer sitting in `libs/store` and `libs/contracts`. The engineering risk in this phase is not "which library to pick" — it's making sure the emitter correctly joins `verdict.ready`/`sab.published` payloads against `Store.get_item`/`get_enrichment` (Summary finding 1) and gets the ntfy bearer-token bootstrap right (Common Pitfalls §2), neither of which any library solves.

## Common Pitfalls

### Pitfall 1: The pre-existing `12-PLAN.md` is a stale, superseded draft — do not reuse it wholesale
**What goes wrong:** `12-PLAN.md` (dated 2026-07-23, pre-SPEC) proposes a 7-adapter body-extraction scheme with HTML sanitization, a hard 10,000-char cap per adapter, and separate "atom-bridge blob-backfill" vs "direct MCP" adapter categories. SPEC.md (dated 2026-08-01, locked, supersedes it) requires **no size cap** ("no size cap (TEXT), backstopped by a >1MB transcript test") and does not mandate per-adapter HTML sanitization as an R7 acceptance criterion. `12-PLAN.md` also shows the 7-field payload using `uuid4().hex` for `alert_id` and a different `sab://`-style deep-link scheme that SPEC/CONTEXT explicitly replaced with `obsidian://open?vault=...&file=...`.
**Why it happens:** `12-PLAN.md` was written before `/gsd-spec-phase 12` and `/gsd-discuss-phase 12` Turn-2 ran; CONTEXT.md itself flags it as "Pre-SPEC draft plan... REPLAN against SPEC + this CONTEXT (operator chose 'replan after')."
**How to avoid:** Treat `12-PLAN.md` as historical context only — its dependency-ordering (a→b→c→d→e→f) and file-layout ideas are still reasonable, but its concrete field values, char caps, and deep-link format are superseded. Always check a value against `12-SPEC.md`/`12-CONTEXT.md` before carrying it forward from `12-PLAN.md`.
**Warning signs:** Any task that cites a specific numeric cap (10,000 chars) or `sab://` URI format should be flagged for correction against the locked SPEC.

### Pitfall 2: The shipped ntfy image has no bearer-token mechanism yet
**What goes wrong:** SPEC R6 requires the emitter to authenticate with a **bearer token** (`Authorization: Bearer tk_...`), and requires the emitter to fail closed if that token is missing. But `apps/ntfy/Dockerfile` (ADR-018, already shipped) only runs `ntfy user add producer`/`ntfy user add reader` — this provisions **Basic Auth** username/password pairs, not tokens. `ntfy token add <username>` is a separate command that generates a random `tk_`-prefixed token at the time it is run; it cannot be pre-selected by the operator and baked in via a BuildKit secret the same way the passwords were (the existing pattern assumes the *value* is chosen ahead of time; a token's value is generated, not chosen).
**Why it happens:** Sub-wave (a) (already shipped, 2026-07-23) predates ADR-015's Decision 3 payload-shape lock and R6's bearer-token requirement — it only needed *some* working auth for the `make ntfy-publish-test` smoke test, and Basic Auth sufficed for that.
**How to avoid:** Extend the Dockerfile's builder-stage `RUN` block (or add a `make ntfy-token` operator step run once after `ntfy-up`) to also call `ntfy token add producer`, capture the printed `tk_...` value, and surface it to the operator for placement into `.env` as `NTFY_TOKEN` (mirroring how `NTFY_PRODUCER_PASSWORD`/`NTFY_READER_PASSWORD` already flow through `.env` → BuildKit secret). Because the token is generated (not chosen), the cleanest flow is almost certainly: **generate at first `docker exec` post-boot, write to a small file, print it once for the operator to copy into `.env`, and never bake a token value into the image layer.** This is genuinely new engineering for this phase — flag it explicitly for the planner as its own task, not an assumed one-liner.
**Warning signs:** Any plan task that says "reuse `NTFY_PRODUCER_PASSWORD` as the bearer token" is wrong — ntfy's Basic Auth and Bearer-token auth are different credential types (`ntfy token add` output format `tk_<29 more chars>`, confirmed via ntfy's own CLI usage text and config docs).
`[CITED: https://ntfy.sh/docs/config/ and https://github.com/binwiederhier/ntfy/blob/main/docs/config.md — `ntfy token add <user>` generates a token starting with `tk_`, 32 characters total, usable as `Authorization: Bearer <token>`]`

### Pitfall 3: `verdict.ready`/`sab.published` do not carry the fields the 7-field payload needs
**What goes wrong:** A naive emitter implementation tries to read `pmesii`, `title`, `url`, or `summary` directly off the consumed bus message and finds they aren't there (`VerdictReady` has `event, item_id, ccir, cnr, score, bucket, why, ts` only — see `_events.py`; `SabPublished` carries a batch-level `item_refs` list capped at 50, without `pmesii`).
**Why it happens:** These events were designed for their original consumers (brief renderer, wiki refresh trigger), which either already had the enrichment row in hand or didn't need `pmesii` at all. Phase 12 is the first consumer that needs the full enrichment row keyed only by `item_id`.
**How to avoid:** After consuming either trigger and confirming `cnr == "I"`, always call `store.get_item(item_id)` (for `title`, `url`, `summary`) and `store.get_enrichment(item_id)` (for `pmesii`, `why`) before building the payload. Both are cheap indexed point-lookups already used identically by `apps/brief/vault_writer.py`.
**Warning signs:** A payload-builder unit test that mocks only the bus message (no Store calls) and expects a fully-populated 7-field payload is testing the wrong contract.

### Pitfall 4: `articles.body` wire-format inflation is a real, documented risk — keep alerting's failure isolation real, not just asserted
**What goes wrong:** `009-articles-body.sql`'s own migration comment warns that `a.body` can inflate a row's JSON payload 5-100× (email/HTML-heavy sources). SPEC AC8 requires "alerting tests pass with `articles.body` NULL for all rows" as a failure-isolation guarantee — this is not a hypothetical, it's a pre-existing measured risk in a sibling code path (`apps/brief`'s `_ENRICHMENT_SQL`/`_SELECT` already read `a.body`).
**Why it happens:** Postgres TEXT columns have no size cap, and body text is now written by 7 independent adapters with no shared cap logic (per SPEC R7's locked "no size cap" decision).
**How to avoid:** Confirm at code-review time that no query inside `apps/alerting/` ever `SELECT`s the `articles.body` column (the emitter should only ever touch `infotriage.enrichment` + the non-`body` columns of `infotriage.articles`/`Item`). A grep-based test asserting `"body"` never appears in any SQL string inside `apps/alerting/` is a cheap, durable regression guard for P2/AC8.
**Warning signs:** Any `SELECT * FROM infotriage.articles` inside the alerting path (rather than an explicit column list) would silently pull in `body` and violate P2/AC8 the moment a future refactor adds a body-dependent field to a shared query helper.

## Code Examples

### Consuming both trigger routing keys on one queue (mirrors apps/wiki/wiki_worker.py:149-167)
```python
# Source: apps/wiki/wiki_worker.py (existing, live code) — adapted for two routing keys
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

### `/health` server (stdlib, mirrors apps/wiki/wiki_worker.py:175-195)
```python
# Source: apps/wiki/wiki_worker.py (existing, live code) — reused verbatim shape
async def _handle_health(reader, writer) -> None:
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
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| ntfy ACL: `producer`/`reader` Basic Auth users only (ADR-018, sub-wave a) | ntfy ACL: same two users PLUS a generated bearer token for the emitter (this phase) | This phase (Phase 12) | The emitter must be built against Bearer auth from day one — do not reuse the existing Basic Auth password as a stand-in |
| `sab://` reserved-but-unimplemented deep link (ADR-015 original draft) | `obsidian://open?vault=...&file=...` (ADR-015 §Open Items 2, resolved 2026-07-23; SPEC R5 locked) | 2026-07-23 | Any code/docs still referencing `sab://` (including `12-PLAN.md`) are stale |

**Deprecated/outdated:**
- `12-PLAN.md`'s `sab://item/<id>` deep-link format — superseded by `obsidian://` (see Pitfall 1).
- `12-PLAN.md`'s 10,000-char per-adapter body cap — superseded by SPEC R7's "no size cap (TEXT)."

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `ntfy token add <user>` generates a `tk_`-prefixed 32-char bearer token usable via `Authorization: Bearer <token>`, and cannot have its value pre-chosen the way a Basic-Auth password can | Common Pitfalls §2 | If ntfy actually does support specifying a custom token string, the recommended "generate-and-capture-post-boot" bootstrap flow could be simplified back into the existing BuildKit-secret pre-bake pattern. Verify against `ntfy token add --help` / current ntfy docs before finalizing the provisioning script. |
| A2 | Obsidian's `obsidian://open?vault=X` parameter expects the vault's **display/folder name**, not a filesystem path, and there is no existing project constant for it | Architecture Patterns §6 | If Obsidian actually accepts a path-form `vault=` value, `INFOTRIAGE_VAULT_PATH` could be reused directly instead of introducing a new env var. Low risk either way since this only affects the `deep_link`/`item_link` field's tap-through UX, not any pass/fail acceptance criterion beyond R5's path-match check. |
| A3 | The recommended in-process retry loop (1s, then 5s, then write to `outbox.dlx.queue`) satisfies SPEC R4/AC4 without needing the RabbitMQ TTL+DLX chain recipe | Architecture Patterns §5 | If the planner/reviewer decides retries must survive an `apps/alerting` process crash mid-backoff (not explicitly required by SPEC), the TTL+DLX chain becomes necessary instead of the simpler in-process loop. |

## Open Questions (RESOLVED)

> Both questions were "Claude's Discretion" carve-outs; the plans made concrete choices (2026-08-01):
> Q1 → post-boot `docker exec` token mint captured into `.env` at the 12-03 `checkpoint:human-verify` (recommendation adopted).
> Q2 → plain TEXT columns matching the `enrichment` convention, pinned column list in 12-02 (recommendation adopted).

1. **Bearer-token bootstrap mechanics for ntfy (SPEC R6, D-02/Claude's Discretion)** *(RESOLVED — 12-03)*
   - What we know: `ntfy token add <user>` generates the token; the existing Dockerfile only pre-bakes passwords.
   - What's unclear: Whether to generate the token at image-build time (inside the same `RUN` block that already starts/stops `ntfy serve` to seed `auth.db`) and write it to a file COPYed into the final image (then read via `docker exec` once), or generate it post-boot via a `make ntfy-token` operator step.
   - Recommendation: Prefer the post-boot `docker exec` + operator-captured `.env` value — it avoids baking any credential-shaped value into an image layer even transiently, matching the ADR-018 philosophy ("only bcrypt hashes land in image layers") extended to tokens (tokens are themselves bearer-equivalent secrets, arguably higher-value than a bcrypt hash since they're used directly, not hashed).

2. **`alert_state` exact column set (D-02 explicitly left open)** *(RESOLVED — 12-02)*
   - What we know: Needs `dedupe_id` PK/unique, `fired_at`, and enough bookkeeping to distinguish "fired" vs "suppressed-and-pending-digest" vs "already-digested."
   - What's unclear: Whether `suppressed`/`digested_at` should be separate boolean+timestamp columns or a single `status` enum-like TEXT column (matching the existing `bucket`/`ccir`/`cnr` TEXT-not-enum convention used throughout `infotriage.enrichment`).
   - Recommendation: Follow the existing project convention of plain TEXT columns with app-level validation (not Postgres ENUM types — none exist elsewhere in the schema) for consistency with `006-enrichment.sql`.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| RabbitMQ (`infotriage-rabbitmq`, port 22001) | `q.alerting` consumer | ✓ (already running for all other services) | — | — |
| Postgres (`infotriage-postgres`, port 22000) | `alert_state` table | ✓ (already running) | — | — |
| ntfy (`infotriage-ntfy`, port 22070) | Push delivery target | ✓ (shipped sub-wave a) | `binwiederhier/ntfy:latest` | — |
| Next free 22xxx port for `apps/alerting`'s own health server | D-01's `/health` endpoint | N/A (port not yet allocated) | — | Recommend `22050` — confirmed free by scanning every `22[0-9]{3}` occurrence in `docker-compose.yml` (highest allocated below the ntfy service's `22070` is `22042`; `22050` leaves headroom without colliding with the 22070 ntfy block) |

**Missing dependencies with no fallback:** none — all runtime infra already exists.
**Missing dependencies with fallback:** none.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (project-wide; `tests/` at repo root) |
| Config file | none dedicated — see `tests/conftest.py` for `db_live`/`pg_store` fixtures |
| Quick run command | `pytest tests/test_alerting_*.py -q` (files to be created this phase) |
| Full suite command | `make -f ops/Makefile test-safe` (throwaway Postgres, current baseline 685/0/0) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|--------------------|-------------|
| R1 | Dual-trigger exactly-once | unit (mocked Store+bus) | `pytest tests/test_alerting_emitter.py -x` | ❌ Wave 0 |
| R2 | Dedupe 24h TTL, injected clock | unit | `pytest tests/test_alerting_dedupe.py -x` | ❌ Wave 0 |
| R3 | Sliding-window throttle + digest | unit + `db_live` | `pytest tests/test_alerting_throttle.py -x` | ❌ Wave 0 |
| R4 | Outbox retry + DLX + broker restart | unit (mocked ntfy) + integration | `pytest tests/test_alerting_outbox.py -x` | ❌ Wave 0 |
| R5 | `obsidian://` URI matches vault-writer | unit | `pytest tests/test_alerting_deeplink.py -x` | ❌ Wave 0 |
| R6 | ntfy ACL 403/200 + fail-closed startup | integration (`make ntfy-up` required) + unit | `pytest tests/test_alerting_auth.py -x` | ❌ Wave 0 |
| R7 | 7-adapter body UPSERT, NULL vs body-bearing, >1MB backstop | unit per-adapter + `db_live` | `pytest tests/test_ingest_*_body.py -x` (7 files) | ❌ Wave 0 |
| R8 | SAB stays canonical, `articles.body` NULL isolation | negative test (grep-based SQL-string guard + full-suite run with NULL bodies) | `pytest tests/test_alerting_prohibitions.py -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** targeted `pytest tests/test_alerting_*.py -q` (sub-second to low-seconds, InMemoryStore-first)
- **Per wave merge:** `make -f ops/Makefile test-safe` (full suite against throwaway Postgres, ~35-45s per current baseline)
- **Phase gate:** Full suite green (685+N passed, 0 failed) before `/gsd-verify-work 12`

### Wave 0 Gaps
- [ ] `tests/test_alerting_emitter.py` — covers R1 (dual-trigger exactly-once)
- [ ] `tests/test_alerting_dedupe.py` — covers R2 (24h TTL, injected clock)
- [ ] `tests/test_alerting_throttle.py` — covers R3 (sliding windows + hourly digest)
- [ ] `tests/test_alerting_outbox.py` — covers R4 (retry/DLX/restart redelivery)
- [ ] `tests/test_alerting_deeplink.py` — covers R5 (`obsidian://` URI construction)
- [ ] `tests/test_alerting_auth.py` — covers R6 (ACL 403/200, fail-closed startup)
- [ ] `tests/test_ingest_{gmail,imap,youtube,telegram,barentswatch,acled,obsidian}_body.py` (or extend existing per-adapter test files) — covers R7
- [ ] `tests/test_alerting_prohibitions.py` — covers R8 negatives + all 5 SPEC prohibitions (P1-P5)
- [ ] `libs/store/sql/011-alert-state.sql` — new migration (no test file per se, but `init_schema()`'s existing glob-and-apply mechanism auto-picks it up; add a smoke assertion that the table exists post-`init_schema()`)
- [ ] `apps/alerting/requirements.txt` + `apps/alerting/Dockerfile` — no test coverage possible pre-build; covered by `docker compose config` + `make ntfy-up`-style smoke target

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | Bearer token auth to ntfy (`NTFY_TOKEN`); fail-closed startup on missing token (SPEC R6, Pattern 7) |
| V3 Session Management | no | Stateless HTTP POST per alert; no session concept |
| V4 Access Control | yes | ntfy topic ACL: `cnr-cat-i` requires token for both read and write (deny-all default); `cnr-cat-i-debug`/`-test` write-only |
| V5 Input Validation | yes | `sab_excerpt` hard-capped at 500 chars server-side (never trust upstream `why`/`summary` length); `FeedUnhealthy`-style `Field(max_length=...)` pydantic pattern already used elsewhere in `_events.py` is the project idiom to follow for any new alerting event models |
| V6 Cryptography | no (reuse only) | `dedupe_id = sha256(...)[:16]` is a stable-hash identifier, not a cryptographic security boundary — no new crypto primitive introduced |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Unauthenticated push to `cnr-cat-i` (spoofed alert injection) | Spoofing | ntfy `auth-default-access=deny-all` + per-topic bearer/basic ACL (already the ADR-018 posture; extend to the new token) |
| Alert flood / DoS via repeated verdict re-scoring | Denial of Service | 3-tier throttle (Pattern 3) is the mitigation this phase implements — do not weaken the sliding-window caps |
| Credential leakage via Docker image layers or logs | Information Disclosure | Never log `NTFY_TOKEN`/`NTFY_PRODUCER_PASSWORD` (mirrors the existing `_bus_rabbitmq.py` "never log the DSN" convention, T-03-01); bearer token must arrive via `.env`/env_file only, never `ARG`/`ENV` baked into a layer (matches ADR-018 §Architecture note) |
| Body-derived SSRF/XSS if `articles.body` ever leaked into a rendered surface | Tampering/Info Disclosure | Out of scope for alerting per P2/AC8 (alerting never reads `body`) — the actual sanitization concern belongs to `apps/brief`'s link-view renderer, already flagged in `009-articles-body.sql`'s own migration comment, not to this phase |

## Sources

### Primary (HIGH confidence)
- `libs/contracts/src/contracts/_bus_rabbitmq.py` — RabbitMQ topology, fan-out queue pattern, DLX declaration order (read in full this session)
- `libs/contracts/src/contracts/_events.py` — exact wire schema of `VerdictReady`/`SabPublished`/`FeedUnhealthy` (read in full this session)
- `libs/contracts/src/contracts/_item.py` — `Item` model + `id` computed field derivation (read in full this session)
- `libs/ingest_common/src/ingest_common/persist.py` — `persist_and_publish` choke point (read in full this session)
- `libs/store/src/store/_postgres.py` (lines 320-400, 127-145) — `put_enrichment`/`get_enrichment` ON CONFLICT idiom; `init_schema()` glob-and-apply migration mechanism (read this session)
- `libs/store/sql/006-enrichment.sql`, `009-articles-body.sql` — migration numbering precedent, wire-format-inflation warning (read in full this session)
- `apps/wiki/wiki_worker.py` — full consumer/health-server/CLI shape template (read in full this session)
- `apps/opml_health/service.py` — operator-event (`feed.unhealthy`) precedent, FastAPI `/health` alternative (read partially this session)
- `apps/brief/consumer.py` (lines 180-235) — `item_refs` top-50-cap + `ORDER BY e.score DESC` finding (read this session)
- `apps/brief/vault_writer.py` (lines 70-105) — `write_item_obsidian` filename derivation (`safe_id = item_id`) (read this session)
- `apps/triage/worker.py` (grep + targeted read) — confirmed `VerdictReady.model_dump(mode="json")` is the exact wire payload, no extra fields
- `docs/adr/ADR-015-cnr-alerting-channels-and-payload.md`, `ADR-016-airgap-and-safety-doctrine.md`, `ADR-013-recognized-picture-doctrine.md` — read in full this session
- `apps/ntfy/Dockerfile`, `ops/Makefile` (ntfy targets), `docker-compose.yml` (ntfy service block) — read this session; confirmed current auth is Basic Auth (username/password) only, no bearer token provisioning yet
- `.planning/phases/12-cnr-alerting-dissemination/12-CONTEXT.md`, `12-SPEC.md`, `12-PLAN.md` — all read in full this session

### Secondary (MEDIUM confidence)
- ntfy `ntfy token add` bearer-token behavior — WebSearch cross-referencing `ntfy.sh/docs/config` and the upstream `binwiederhier/ntfy` GitHub docs; not independently verified by running the command in this session (container-image-build-time verification recommended before finalizing the provisioning script)

### Tertiary (LOW confidence)
- Obsidian `obsidian://open?vault=` parameter semantics (vault display-name vs path) — not independently verified this session; flagged as Assumption A2

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — zero new packages, every dependency already pinned and running in this exact codebase
- Architecture: HIGH for patterns 1-4/6-8 (directly derived from live, read code); MEDIUM for pattern 5 (outbox/DLX shape — reasoned recommendation, not a shipped precedent in this repo)
- Pitfalls: HIGH for §1/§3/§4 (grounded in code actually read this session); MEDIUM for §2 (ntfy bearer-token mechanics — CITED from upstream docs, not verified against this project's exact ntfy version/build)

**Research date:** 2026-08-01
**Valid until:** 2026-08-31 (30 days — stable internal architecture; re-check ntfy CLI syntax if `binwiederhier/ntfy:latest` pulls a materially newer version before this phase executes, since the compose file deliberately tracks `:latest`)
