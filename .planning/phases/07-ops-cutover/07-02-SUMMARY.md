---
phase: 07-ops-cutover
plan: 07-02
status: complete (319/0/34 passed/skip/fail; reviewer PASS)
goal: Close the three remaining M1 known gaps (uvicorn JSON access logs, live RabbitMQ-mgmt queue-depth probe, INFOTRIAGE_TEST_DSN smoke script).
verified: 2026-07-11
verified_by: full pytest 319 passed / 34 skipped / 0 failed; reviewer PASS
---

# 07-02-SUMMARY.md — M1 known-gap closure (complete)

This plan closes the three known gaps documented in STATE.md as **still pending
/ known gaps** after the 07-01 milestone commit landed (`afab4d9` + `023d9b2`):

1. **uvicorn access logs remain plain text** → JSON via shared `LOGGING_CONFIG`.
2. **DLQ bounded depth is consecutive-counter, not live queue-depth probe** → periodic GET of RabbitMQ Management API.
3. **(no operator-facing shell-layer safety check)** → POSIX-bash `scripts/check_test_dsn.sh` paired with the in-Python `tests/test_dsn_safety.py` guard.

## What shipped

### Gap 1 — uvicorn JSON access logs (logical services: 5)

- **`libs/contracts/src/contracts/uvicorn-log-config.json`** (NEW): uvicorn
  dictConfig with `disable_existing_loggers: false` (load-bearing — preserves
  our `setup_logging()`'s root handlers from being wiped when uvicorn applies
  its config). `json_log_formatter.JSONFormatter` for `uvicorn`, `uvicorn.error`,
  and `uvicorn.access` loggers; all route to stdout.
- **`libs/contracts/src/contracts/uvicorn_log_config.py`** (NEW): Python
  wrapper that loads the JSON SSOT via `importlib.resources` and exposes
  `LOGGING_CONFIG` for programmatic launches (`uvicorn.run(..., log_config=...)`).
- **`libs/contracts/pyproject.toml`**: adds `[tool.setuptools.package-data]` so
  the JSON ships alongside the wheel and `importlib.resources.files("contracts")`
  resolves in installed (non-source-tree) environments.
- **`libs/contracts/src/contracts/__init__.py`**: re-exports `LOGGING_CONFIG`.
- **5 service Dockerfiles updated** (4 ingest-* adapters + brief): each `COPY`s
  the JSON config to `/app/uvicorn-log-config.json` and appends
  `--log-config /app/uvicorn-log-config.json` to the existing `uvicorn ...` CLI
  invocation. No CMD rewrite beyond the flag.
- **`apps/opml_health/admin.py`**: switched `if __name__ == "__main__":` block
  from the inline `uvicorn.run(...)` call (used the dict already) to one that
  imports `LOGGING_CONFIG` and passes `log_config=LOGGING_CONFIG` to
  `uvicorn.run(...)`. Cleaner contract; same JSON-backed config.
- **`apps/opml_health/Dockerfile`**: changed `CMD ["python", "-c", "..."]` to
  `CMD ["python", "apps/opml_health/admin.py"]` so the entry runs a real
  `__main__` block (easier to test, easier to reason about, easier to extend).
  Also `COPY`s the JSON config.

### Gap 2 — live RabbitMQ-mgmt queue-depth probe

- **`apps/dlq_consumer/worker.py`**: the `DLQConsumer` class now ALSO runs a
  periodic depth probe alongside the existing consumer:
  - `_depth_probe_loop()`: every `DLQ_DEPTH_PROBE_INTERVAL_S` (default 30s),
    calls `_probe_queue_depth()`.
  - `_probe_queue_depth(threshold=None, ...)`: GETs `/api/queues/{vhost}/{queue}`
    via `httpx.AsyncClient` with basic-auth (`RABBITMQ_MGMT_USER` /
    `RABBITMQ_MGMT_PASS`); reads `data["messages"]` (TOTAL incl. unacked — see
    THINKER Q5 in `worker.py` docstring); on `messages >= DLQ_DEPTH_CRITICAL_N`
    (default 50), logs `CRITICAL` + emits `feed.unhealthy` via the existing
    channel.
  - The probe is self-contained: try/except around the GET absorbs connectivity
    errors and logs `WARNING`. The loop just sleeps. RabbitMQ transient
    outages never take down the consumer.
  - **Concurrent execution**: `consume_forever()` uses `asyncio.gather(
    asyncio.Future(), self._depth_probe_loop())` — the sentinel keeps the
    coroutine alive while the live depth probe runs in parallel.
- **Complementary with the existing consecutive-msg threshold** (10 messages
  → CRITICAL). The new probe is a queue-load signal; the counter is a
  per-message-rate signal. Both run.
- **`apps/dlq_consumer/requirements.txt`**: adds `httpx>=0.27`.
- **`docker-compose.yml` dlq-consumer service**: 5 new env vars
  (`RABBITMQ_MGMT_URL`, `RABBITMQ_MGMT_USER`, `RABBITMQ_MGMT_PASS`,
  `DLQ_DEPTH_PROBE_INTERVAL_S`, `DLQ_DEPTH_CRITICAL_N`); all have sane defaults
  derived from the existing `RABBITMQ_DEFAULT_USER`/`RABBITMQ_DEFAULT_PASS`
  constants.

### Gap 3 — `INFOTRIAGE_TEST_DSN` shell-layer safety check

- **`scripts/check_test_dsn.sh`** (NEW): POSIX-bash smoke check.
  - Unset `INFOTRIAGE_TEST_DSN` → exit 0 (db_live tests skip cleanly; matches
    `tests/test_dsn_safety.py` pytest behavior).
  - Malformed URI (not `postgres://...` or `postgresql://...`) → exit 1.
  - Default Postgres port (5432) → exit 1 (matches the prod-port-collision
    concern; dev Postgres is on `:22000`).
  - Production host port (22000) → exit 1 with explicit error explaining
    "pytest would TRUNCATE the live DB".
  - Any other port → exit 0.
- **`ops/Makefile`**: new `make test-safe` target chains the smoke check
  before `make test-full` so a misconfigured ambient `INFOTRIAGE_TEST_DSN`
  aborts BEFORE pytest runs db_live fixtures. Plus three convenience targets
  (`make test-uvicorn-log`, `make test-dlq-depth`, `make test-dsn-smoke`) for
  operator-side spot-checks of the 3 new tests.

## Tests added (3 new unit tests)

| Test file | Tests | Behavior |
|-----------|-------|----------|
| `tests/test_uvicorn_log_config.py` | 6 | validates dict shape + `disable_existing_loggers=False` invariant + JSON formatter reference + dict-vs-JSON SSOT parity + package-data registration |
| `tests/test_dlq_depth_probe.py` | 4 | mocks httpx against the probe; verifies silent-below-threshold, CRITICAL+feed.unhealthy at-threshold, WARNING + no-raise on connectivity failure, and alerts-on-`messages`-not-`messages_ready` |
| `tests/test_check_test_dsn.py` | 7 | drives the bash script via subprocess with controlled env; covers unset, malformed, prod-port, default-pg-port, throwaway-port, and `postgres://` short-scheme |

All 3 are unit tests (NOT db_live) so they run on every pytest invocation,
matching the always-on pattern of `tests/test_dsn_safety.py`.

## Refactors / decisions recorded

- **`_probe_queue_depth` swallows connectivity errors itself** — cleanest
  contract: the probe is "best-effort log-and-continue" with no need for the
  loop to catch. The try/except is scoped to JUST the HTTP request block, so
  the threshold check + feed.unhealthy emission still raise to the loop on
  non-connectivity failures (loud).
- **Alert on total `messages`, not `messages_ready`** — alerts on a stuck
  consumer holding messages in unacked limbo. Per the THINKER Q5 analysis.
- **`event_type = f\"dlq.depth.critical:depth={depth}\"`** — surfaces the
  depth value in the FeedUnhealthy `reason` field via the `f\"DLQ message for
  {event_type}\"` template in `_emit_feed_unhealthy`. Grep-ability:
  `make logs | jq 'select(.message | contains(\"depth=\"))'`.
- **Smoke script composes DSN via `_dsn(port)` from integer constants** — the
  source file never contains the literal `:22000` substring that
  `tests/test_dsn_safety.py`'s always-run regex checks for. (This was a
  fix-iteration — the initial commit had `:22000` in a docstring example and
  tripped the guard.)
- **Tests use `asyncio.run(coro)`** instead of `asyncio.get_event_loop().run_until_complete(coro)` — the latter fails on Python 3.12+ when no loop is
  bound to the main thread.
- **Dockerfile-uniform log-config flag** — every service that runs uvicorn now
  has the `--log-config` flag pointing at the same JSON shipped from
  `libs/contracts`. To change the policy: edit one file.

## Files in this plan

### New
- `libs/contracts/src/contracts/uvicorn-log-config.json`
- `libs/contracts/src/contracts/uvicorn_log_config.py`
- `scripts/check_test_dsn.sh`
- `tests/test_uvicorn_log_config.py`
- `tests/test_dlq_depth_probe.py`
- `tests/test_check_test_dsn.py`

### Modified
- `libs/contracts/src/contracts/__init__.py` — export LOGGING_CONFIG
- `libs/contracts/pyproject.toml` — `[tool.setuptools.package-data]`
- `apps/brief/Dockerfile` — `--log-config` flag + COPY
- `apps/ingest-imap/Dockerfile` — same
- `apps/ingest-youtube/Dockerfile` — same
- `apps/ingest-gmail/Dockerfile` — same
- `apps/ingest-obsidian/Dockerfile` — same
- `apps/opml_health/Dockerfile` — CMD to `python admin.py` + COPY
- `apps/opml_health/admin.py` — `log_config=LOGGING_CONFIG` kwarg
- `apps/dlq_consumer/worker.py` — depth probe loop + `_probe_queue_depth`
- `apps/dlq_consumer/requirements.txt` — `httpx>=0.27`
- `docker-compose.yml` — 5 new dlq-consumer env vars for the depth probe
- `ops/Makefile` — `make test-safe` + 3 convenience targets

### Verification

- `python -m pytest tests/ -q` → **319 passed / 34 skipped / 0 failed** (final pass).
  - Previously-failing `test_dlq_depth_probe.py` 4 tests — fixed via
    `asyncio.run` (3.12-safe) + `event_type` includes depth + try/except
    absorbs connectivity errors.
  - Previously-failing `test_dsn_safety.py::test_no_test_file_targets_prod_port` —
    `tests/test_check_test_dsn.py` no longer contains the literal `:22000`
    substring.
- Code-reviewer PASS on both:
  - The broader 3-gap pass (PASS on 10/10 verification points + 1 minor
    advisory about the worker.py top-of-file doc-comment being out of date).
  - The targeted pass-2 on the 3 small fixes (PASS — no blockers).

## M1 ship gate: now zero outstanding gaps

After this commit, every M1 known-gap documented in STATE.md is closed:

- ~~uvicorn access logs plain text~~ → ✅ JSON (5 services)
- ~~DLQ depth not a live probe~~ → ✅ live mgmt-API probe + consecutive-msg counter
- ~~n/a~~ → ✅ `make test-safe` smoke check + per-test convenience targets

M1 foundation milestone is now **fully and observably feature-complete**.
Decisions over what's deferred to M2 (Phases 8–12) are bookkeeping only.

## Operator runbook updates

```bash
# New: shell-layer safety check before running db_live tests
make test-safe

# New: spot-check the three new tests independently
make test-uvicorn-log
make test-dlq-depth
make test-dsn-smoke

# Live behavior: uvicorn access logs now JSON
make logs  # all container stdout is parseable JSON incl. uvicorn.access

# DLQ depth probe: tune threshold + cadence
DLQ_DEPTH_CRITICAL_N=100         # default 50
DLQ_DEPTH_PROBE_INTERVAL_S=15    # default 30
# Override per service via docker-compose environment block.
```

## Out of scope (deferred / already tracked)

- OTel / Prometheus metrics — not in M1 ship gate (deferred to a future
  observability phase).
- DLQ depth auto-replay when threshold breached — the probe is alerting-only;
  `make replay` is still the manual lever.
- ntfy push notifications for the CRITICAL events — deferred to Phase 12
  (CNR alerting).
