---
phase: 04-ingest-adapters-gmail-mcp
plan: "01"
subsystem: ingest_common
tags: [ingest, persistence, fastapi, idempotency, tdd]
dependency_graph:
  requires: [libs/contracts, libs/store]
  provides: [libs/ingest_common]
  affects: [apps/ingest-imap, apps/ingest-youtube, apps/ingest-gmail, apps/ingest-obsidian]
tech_stack:
  added: [fastapi>=0.115, uvicorn>=0.30, aio-pika>=9.6, httpx>=0.27]
  patterns: [get_item pre-check idempotency (RESEARCH Pattern 2), asyncio single-instance lock (D-01)]
key_files:
  created:
    - libs/ingest_common/pyproject.toml
    - libs/ingest_common/src/ingest_common/__init__.py
    - libs/ingest_common/src/ingest_common/persist.py
    - libs/ingest_common/src/ingest_common/trigger.py
    - libs/ingest_common/src/ingest_common/runtime.py
    - tests/test_ingest_idempotency.py
    - tests/test_trigger_lock.py
  modified:
    - pyproject.toml
decisions:
  - "get_item pre-check is the sole newness signal (NOT put_item return value — RESEARCH Finding 2)"
  - "in-flight flag set synchronously before first await to eliminate concurrency race window (D-01)"
  - "finally block clears lock so crashed runs never permanently wedge the trigger"
  - "build_bus/build_store read only from env; DSN/AMQP credentials never logged (T-04-01)"
metrics:
  duration: "7m 40s"
  completed: "2026-06-29T11:07:51Z"
  tasks_completed: 3
  tasks_total: 3
  files_created: 7
  files_modified: 1
  tests_added: 6
  tests_passing: 6
status: complete
---

# Phase 04 Plan 01: ingest_common Shared Adapter Toolkit Summary

**One-liner:** Idempotent persist+publish helper (get_item pre-check pattern) + FastAPI single-instance lock trigger factory + env-driven store/bus constructors, tested with 6 TDD unit tests.

## What Was Built

`libs/ingest_common` is a new pip-installable package that provides the three pieces every Phase 4 ingest container depends on:

1. **`persist_and_publish(store, bus, item) -> bool`** (`persist.py`): Implements RESEARCH Pattern 2 — calls `store.get_item(item.id)` BEFORE `store.put_item(item)`. The pre-check result (None vs. existing Item) is the sole newness signal. `put_item` is always called (unconditional upsert); `bus.publish("item.ingested", ...)` is called only when `get_item` returned None. Returns True on new insert, False on duplicate (R6 idempotency).

2. **`make_trigger_app(ingest_coro, *, name) -> FastAPI`** (`trigger.py`): Builds a minimal FastAPI app with `POST /run` and `GET /health`. The single-instance lock uses a dict-backed flag set **synchronously** (no `await` between the 409 check and the flag assignment), eliminating the concurrency race window (D-01). A `_wrap()` coroutine runs via `asyncio.create_task()` and clears the flag in a `finally` block so exceptions never permanently wedge the lock.

3. **`build_store() / build_bus()`** (`runtime.py`): Read `INFOTRIAGE_PG_DSN`, `INFOTRIAGE_BLOB_ROOT`, and `INFOTRIAGE_AMQP_DSN` from `os.environ` and return `PostgresStore` / `RabbitMQBus` instances. The AMQP DSN is never emitted to any logger (T-04-01).

Root `pyproject.toml` `pythonpath` was extended with the five Wave-2 adapter dirs (`apps/ingest-imap`, `apps/ingest-youtube`, `apps/ingest-gmail`, `apps/ingest-obsidian`, `apps/scheduler`) so no Wave-2 plan needs to touch the shared root config.

## Tests (6 green)

| File | Tests | Behavior verified |
|------|-------|-------------------|
| `tests/test_ingest_idempotency.py` | 3 | new-item publishes once + returns True; duplicate publishes nothing + returns False; payload shape {source, source_type, ts} |
| `tests/test_trigger_lock.py` | 3 | 200→409→200 sequence; GET /health always 200; lock cleared after exception |

## Commits

| Hash | Message |
|------|---------|
| e78e071 | test(04-01): add failing test for persist_and_publish idempotency (R6) [RED] |
| d756245 | feat(04-01): implement persist_and_publish — idempotent get_item pre-check pattern [GREEN] |
| a26f500 | test(04-01): add failing tests for make_trigger_app single-instance lock (D-01) [RED] |
| 726836f | feat(04-01): implement make_trigger_app + build_store/build_bus (D-01, T-04-01) [GREEN] |
| 1e9b340 | chore(04-01): wire ingest_common package + extend pytest pythonpath for Wave 2 |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Worktree initialized from wrong base commit**
- **Found during:** Agent startup
- **Issue:** Worktree branch `worktree-agent-a1766265e34394007` was forked from `b0994bb` (pre-Phase-1 state, missing `libs/`, `apps/`) instead of expected base `33da893` (Phase 4 planning state).
- **Fix:** `git reset --hard 33da893` at startup (no agent commits existed yet; this is the sanctioned recovery in the worktree branch check protocol).
- **Impact:** Zero — reset happened before any task execution.

**2. [Rule 1 - Bug] `is_new_insert` string in comments triggered acceptance criterion grep**
- **Found during:** Task 1 verification
- **Issue:** The plan's acceptance criterion `grep -c 'is_new_insert' persist.py` must return 0. Comments referencing the stale pattern triggered the grep.
- **Fix:** Rewrote two comment lines to avoid the literal string while keeping the explanatory intent.

**3. [Rule 1 - Bug] DSN comment matched security grep via line-number prefix**
- **Found during:** Task 2 verification
- **Issue:** `grep -niE 'log.*(dsn|amqp_url|password)' runtime.py | grep -v '^\s*#'` produces false positive because `-n` adds `61:` prefix, preventing `grep -v '^\s*#'` from filtering the comment line.
- **Fix:** Rewrote comment to not contain "amqp_url" and "log" on the same line.

### `__init__.py` Approach

Task 1 only exports `persist_and_publish`; Task 2 adds `make_trigger_app`, `build_store`, `build_bus`. This is a natural sequencing (not a deviation) — the final `__init__.py` matches the plan's specified public API.

## Known Stubs

None — all four public exports are fully implemented and tested.

## Threat Surface Scan

No new network endpoints, auth paths, or schema changes beyond what the plan's threat model documents. The two threats are mitigated:

| T-ID | Mitigation | Verified |
|------|-----------|---------|
| T-04-01 | DSN never logged in runtime.py | grep returns empty |
| T-04-02 | Lock set synchronously; 409 on concurrent POST | test_trigger_200_then_409_then_200 green |

## Self-Check: PASSED

All 8 files confirmed on disk. All 5 task commits confirmed in git history. 6/6 tests passing.
