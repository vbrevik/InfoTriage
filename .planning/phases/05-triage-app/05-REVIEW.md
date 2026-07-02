---
phase: 05-triage-app
reviewed: 2026-07-02T06:58:02Z
depth: standard
files_reviewed: 15
files_reviewed_list:
  - apps/triage/Dockerfile
  - apps/triage/requirements.txt
  - apps/triage/triage_score.py
  - apps/triage/worker.py
  - docker-compose.yml
  - libs/contracts/src/contracts/_bus_rabbitmq.py
  - libs/store/sql/006-enrichment.sql
  - libs/store/src/store/_inmemory.py
  - libs/store/src/store/_postgres.py
  - libs/store/src/store/_protocol.py
  - scripts/shadow_run.py
  - tests/test_bus_consume.py
  - tests/test_triage_enrichment.py
  - tests/test_triage_health.py
  - tests/test_triage_score_hotread.py
  - tests/test_triage_worker.py
findings:
  critical: 1
  warning: 6
  info: 4
  total: 11
status: issues_found
---

# Phase 5: Code Review Report

**Reviewed:** 2026-07-02T06:58:02Z
**Depth:** standard
**Files Reviewed:** 15
**Status:** issues_found

## Summary

Reviewed the full triage-app phase (05-01 through 05-05): the worker (`worker.py`,
`triage_score.py`), the RabbitMQ bus transport, the Postgres/in-memory store additions
for enrichment + embedding dedup, the enrichment SQL migration, the shadow-run parity
script, and the Docker/compose deployment definitions plus their tests.

The core `process_item` flow (dedup → score → persist → publish) is well designed for
the stated invariant (enrichment write must commit before `verdict.ready` is published,
R2/R5), all SQL is parameterized, secrets are supplied via env/`.env` rather than
hardcoded into the image, and the test suite exercises the important edge cases
(missing article, enrichment-write failure, score clamping, dedup skip, header-vs-body
routing regression). However, one pre-existing method in the RabbitMQ transport
(`_rebuild_topology`, exercised for the first time by this phase's `consume()` usage)
has a real production data-loss risk, and the LLM-output parsing path in
`triage_score.py` has an unguarded type-coercion crash that the surrounding
error-handling was clearly intended to prevent but doesn't fully cover. Several
smaller robustness/quality issues are listed below.

## Critical Issues

### CR-01: `_rebuild_topology()` deletes ALL production queues (not just the mismatched one) on any topology conflict, with no environment gate

**File:** `libs/contracts/src/contracts/_bus_rabbitmq.py:93-126`

**Issue:** `_ensure_connection()` calls `_rebuild_topology()` automatically whenever any
`406 PRECONDITION_FAILED` error is detected during topology declaration (e.g. any queue
argument mismatch — a single queue's `x-dead-letter-exchange`/`x-dead-letter-routing-key`
arguments changing between deploys, an operator inspecting/redeclaring a queue with
different args, etc.):

```python
except Exception as e:
    if "406" in str(e) or "PRECONDITION_FAILED" in str(e):
        log.warning("Topology mismatch detected — rebuilding (migration): %s", e)
        try:
            await self._rebuild_topology()
            break
```

`_rebuild_topology()` then unconditionally deletes **every** primary queue plus the DLQ
(`q.triage`, `q.brief`, `q.notify`, `q.ops`, `infotriage.dlq`) — not just the one queue
whose arguments actually conflicted:

```python
for q_name in [DLQ_NAME, "q.triage", "q.brief", "q.notify", "q.ops"]:
    await ch.queue_delete(q_name)
```

`RabbitMQBus` is the production transport (`docker-compose.yml` wires
`INFOTRIAGE_AMQP_DSN` straight into the `triage` service, and this phase adds the first
real `consume()` caller — `worker.py`'s `run_consumer`). Any 406 on reconnect (which can
happen on ordinary redeploys, not just "dev/migration") will silently drop every
in-flight/unacked message across all four business queues and the DLQ, in production,
with no confirmation step. The docstring says "This is safe in dev... In production,
coordinate with ops before running" — but the code has no dev/prod distinction; it runs
unconditionally whenever a 406 is observed.

**Fix:** Do not auto-delete queues from a reconnect path at all in production code.
At minimum:
- Gate the rebuild behind an explicit opt-in (e.g. `RabbitMQBus(..., allow_topology_rebuild=False)` defaulting to `False`, or a `INFOTRIAGE_AMQP_ALLOW_REBUILD` env flag).
- If rebuild must happen, only delete the specific queue(s) that raised 406 (parse the queue name out of the AMQP error or attempt each queue declare individually and catch per-queue), not all four plus the DLQ.
- Log at `error`/alert level and refuse to proceed silently — a message-loss event should be loud, not a `log.warning` buried in reconnect retry noise.

## Warnings

### WR-01: `score_item()` bucket derivation can raise an uncaught `TypeError` on malformed-but-valid LLM JSON

**File:** `apps/triage/triage_score.py:132-142`

**Issue:** The `try/except` only wraps `json.loads(...)`:

```python
try:
    v = json.loads(raw[s:e+1])
except Exception:
    v = {...fallback...}
...
v["bucket"] = "skip" if ccir == "none" else ("read" if v.get("cnr") == "I"
                                             or v.get("score", 0) >= 7 else "maybe")
```

If the LLM returns valid JSON but with `"score"` as a quoted string (e.g.
`"score": "8"` — a common LLM hedging pattern despite the prompt asking for an
unquoted number), `v.get("score", 0) >= 7` compares `str >= int`, which raises
`TypeError` in Python 3. This happens *after* the deliberate malformed-output fallback,
so the very case the fallback exists to guard against (imperfect LLM output) can still
crash `score_item()`. The exception propagates through `process_item` → `on_message`,
nacking the message to the DLQ instead of degrading gracefully like the JSON-parse
failure path does. Contrast with `worker.clamp_score()`, which correctly coerces with
`try/except (TypeError, ValueError)`.

**Fix:**
```python
try:
    score_val = int(v.get("score", 0))
except (TypeError, ValueError):
    score_val = 0
v["bucket"] = "skip" if ccir == "none" else ("read" if v.get("cnr") == "I" or score_val >= 7 else "maybe")
```

### WR-02: Code-fence stripping uses `str.lstrip()` as if it stripped a prefix, not a character set

**File:** `apps/triage/triage_score.py:129-130`

**Issue:**
```python
if "```" in raw:
    raw = raw.split("```")[1].lstrip("json").strip()
```
`str.lstrip("json")` removes *any* leading characters that are members of the set
`{'j','s','o','n'}`, not the literal prefix `"json"`. It happens to work for the
common `\`\`\`json\n{...}` case, but it is a fragile pattern: any future model output
that begins with a run of those characters right after the fence (or a subtly
different fence tag) will be mis-parsed, and the failure mode is silent corruption of
the string passed to `json.loads()` rather than an obvious error.

**Fix:** Strip the literal prefix explicitly:
```python
raw = raw.split("```")[1].strip()
if raw.lower().startswith("json"):
    raw = raw[4:].strip()
```

### WR-03: In-memory publish-dedup set grows unboundedly and does not survive restarts

**File:** `libs/contracts/src/contracts/_bus_rabbitmq.py:75-76, 180-184`

**Issue:** `self._seen: set[tuple[str, str]] = set()` is used to dedup `publish()` calls
by `(routing_key, item_id)` and is never evicted, so a long-running worker process
accumulates one entry per published event for the life of the process (unbounded
process memory growth). More importantly, since this state is purely in-process, a
crash/restart of the worker loses all dedup history — if a message is redelivered
after a crash between a successful `publish()` and the AMQP ack of the *inbound*
`item.ingested` message, the same `verdict.ready` event can be re-published a second
time after restart, even though `publish()`'s dedup comment implies "same
(routing_key, item_id) → no-op" protection.

**Fix:** Either bound `_seen` (e.g. an LRU/TTL cache) or move de-duplication to a
durable store (already available via `PostgresStore`) if idempotent publish is a real
requirement; otherwise document that dedup is best-effort/process-local only.

### WR-04: `InMemoryStore` cosine similarity silently tolerates mismatched vector dimensions

**File:** `libs/store/src/store/_inmemory.py:29-40, 158-179`

**Issue:** `_cosine_sim()` computes `zip(a, b)`, which silently truncates to the
shorter of the two vectors if lengths differ, rather than raising. Combined with
`find_near_duplicate()` iterating over all stored embeddings, a dimension mismatch
(e.g. an embedding model change producing a different vector size) would silently
produce meaningless similarity scores in tests instead of surfacing the bug loudly,
undermining the "D-07: InMemoryStore mirrors production" parity guarantee this module
documents.

**Fix:** Validate `len(a) == len(b)` (or `== DIM`) and raise `ValueError` on mismatch.

### WR-05: File handles opened without `with` (resource leak / not exception-safe)

**File:** `apps/triage/triage_score.py:23, 30, 183`

**Issue:**
```python
return open(CCIR_PATH, encoding="utf-8").read()          # load_ccir, line 23
for line in open(path):                                   # load_dotenv, line 30
items = json.load(open(args.file))                        # main, line 183
```
None of these close the file handle explicitly (or on exception). CPython's refcounting
GC closes them eventually in the common case, but this is the specific anti-pattern the
project review checklist calls out ("missing `with` for file operations") and it's not
guaranteed to close promptly under exception paths or on alternative interpreters.

**Fix:** Use `with open(...) as f:` in all three locations.

### WR-06: `worker.main()` combines two forever-running tasks with `asyncio.gather()` without failure isolation

**File:** `apps/triage/worker.py:225-233`

**Issue:**
```python
with PostgresStore(dsn=pg_dsn, blob_root=blob_root) as store:
    await asyncio.gather(run_consumer(bus, store), run_health_server())
```
If either task raises an exception that isn't already swallowed by the retry loop
inside `_ensure_connection()` (e.g. a genuine programming error, or `run_health_server`
failing to bind its port), `asyncio.gather()` propagates that exception immediately but
does **not** cancel the other still-running task. The `with PostgresStore(...)` block's
`__exit__` then runs (closing the DB connection) while the other task may still be
executing and could attempt to use `store` afterward (e.g. an in-flight
`asyncio.to_thread(store.get_item, ...)` call), or the health server keeps serving `200
OK` after the consumer has effectively died, misleading the Docker healthcheck into
reporting the worker as live when it can no longer process messages.

**Fix:** Wrap in `asyncio.TaskGroup` (Python 3.11+, already targeting py3.12 per the
Dockerfile) so a failure in either task cancels the other, or explicitly cancel the
sibling task in a `try/except`/`finally` around `gather()`.

## Info

### IN-01: Duplicated LLM/embedding HTTP-call boilerplate between `triage_score.llm()` and `worker.get_embedding()`

**File:** `apps/triage/triage_score.py:36-49`, `apps/triage/worker.py:37-54`

**Issue:** Both functions independently build the same base-URL/header/timeout/request
pattern. The `worker.py` docstring explicitly says it "mirrors triage_score.llm()
exactly," which is itself an indicator this should be a shared helper rather than two
hand-synced copies — a future change to one (e.g. adding retry, changing timeout) is
easy to forget to apply to the other.

**Fix:** Extract a small shared `_post_json(base, key, path, body, timeout)` helper
into a common module.

### IN-02: Dev-default credentials repeated across multiple files with no guard against silent production use

**File:** `docker-compose.yml:55,76`, `scripts/shadow_run.py:36`, `libs/contracts/src/contracts/_bus_rabbitmq.py:39`

**Issue:** `POSTGRES_PASSWORD`, `RABBITMQ_DEFAULT_PASS`, the `infotriage_dev`/
`infotriage_rmq` DSNs, and the `omlx` API key all have hardcoded fallback defaults
(`${VAR:-default}` in compose, plain string constants elsewhere), and `env_file: .env`
is `required: false`. This is consistently documented as intentional dev-only
convenience, consistent with the rest of the codebase, so it's not a new issue
introduced by this phase — but there's still no automated check (e.g. a startup
assertion, or `required: true` for the credential-bearing vars) that would prevent an
operator from accidentally running a "production" deployment on these dev defaults if
`.env` is missing or incomplete.

**Fix:** Consider a startup check in `worker.py`/compose that fails loudly if
`INFOTRIAGE_PG_DSN`/`INFOTRIAGE_AMQP_DSN` resolve to the well-known dev defaults in a
non-dev environment (e.g. gated by an `ENVIRONMENT=production` flag).

### IN-03: `requirements.txt` pins only lower bounds

**File:** `apps/triage/requirements.txt:4-14`

**Issue:** All dependencies use `>=` with no upper bound and there's no lockfile
checked in for this app, so a future `pip install -r requirements.txt` (e.g. rebuilding
the Docker image) can silently pull a newer, potentially breaking transitive release.

**Fix:** Pin exact versions or add a lockfile (e.g. `pip-compile`) for reproducible
builds, consistent with how strictly `INFOTRIAGE_PG_DSN` is required elsewhere in this
phase.

### IN-04: Inconsistent strictness between required and optional env vars in `worker.main()`

**File:** `apps/triage/worker.py:226-230`

**Issue:** `INFOTRIAGE_PG_DSN` is read via `os.environ[...]` (raises `KeyError` and
crash-loops the container if missing — good, fail-loud behavior) while
`INFOTRIAGE_AMQP_DSN` is read via `os.environ.get(..., <dev default>)` (silently falls
back). Outside of the docker-compose context (where compose always injects a value),
running `worker.py` directly with a misconfigured/missing AMQP DSN would silently
attempt to connect to `127.0.0.1:22001` inside whatever process runs it, rather than
failing fast the way the Postgres DSN does.

**Fix:** For consistency, either require both via `os.environ[...]` or document why
AMQP alone gets a soft fallback.

---

_Reviewed: 2026-07-02T06:58:02Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
