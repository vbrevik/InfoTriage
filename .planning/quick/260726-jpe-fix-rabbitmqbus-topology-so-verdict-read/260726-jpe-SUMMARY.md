---
phase: 260726-jpe-fix-rabbitmqbus-topology
plan: 01
subsystem: bus
tags: [rabbitmq, fan-out, competing-consumer, wiki, brief]
dependency-graph:
  requires: []
  provides: [BUS-FANOUT-01]
  affects: [apps/wiki, apps/brief, apps/triage]
tech-stack:
  added: []
  patterns: ["list-valued routing-key-to-queue map", "optional queue_name override on consume()"]
key-files:
  created: []
  modified:
    - libs/contracts/src/contracts/_bus_rabbitmq.py
    - tests/test_bus_rabbitmq.py
    - tests/test_bus_consume.py
    - apps/wiki/wiki_worker.py
decisions:
  - "Per-task commits (one per Task 1/2/3) instead of a single squashed commit — matches this executor's standard atomic-commit protocol; the plan's 'single commit' framing was written for one-shot execution, but the cumulative diff across the three commits is exactly the four planned files, satisfying the underlying success criterion (no unrelated files, complete traceability)."
metrics:
  duration: "~35 minutes (Tasks 2-5, continuing from Task 1's prior commit ec52292)"
  completed: 2026-07-27
status: complete
---

# Phase 260726-jpe Plan 01: Fix RabbitMQBus fan-out topology so verdict.ready reaches both brief and wiki Summary

Fixed a competing-consumer bug where `apps/wiki/wiki_worker.py --mode events` and
`apps/brief/consumer.py` both resolved `verdict.ready` to the single queue `q.brief`,
silently splitting every event between the two services instead of delivering an
independent copy to each.

## What Was Built

`ROUTING_KEY_TO_QUEUE` in `libs/contracts/src/contracts/_bus_rabbitmq.py` now maps each
routing key to a **list** of queue names instead of a single name. `verdict.ready` is now
`["q.brief", "q.wiki"]`. `consume()` gained an optional `queue_name` keyword that lets a
caller pick a specific bound queue; with no override it resolves to the first list entry —
the exact mechanism that keeps `apps/brief/consumer.py` and `apps/triage/worker.py`
resolving to their original queues with zero source changes. `apps/wiki/wiki_worker.py`
now passes `queue_name="q.wiki"` explicitly, attaching to its own independently-bound
queue instead of contending with brief.

## Task Execution

- **Task 1** (prior session, commit `ec52292`): widened `ROUTING_KEY_TO_QUEUE` to list
  shape, re-keyed `self._queues` by queue name, added the `queue_name` parameter to
  `consume()`, updated `_declare_topology()`/`_rebuild_topology()`/`subscribe()`, and
  mechanically synced both test files to the new shape (no new tests). Independently
  re-verified this session — diff matches the plan exactly.
- **Task 2** (commit `eb28331`): added `test_verdict_ready_fans_out_to_both_queues` (one
  publish, two independent consumers — no-override + explicit override — both receive
  the identical payload) and `test_consume_rejects_queue_not_bound_to_routing_key`.
- **Task 3** (commit `9f0437b`): `run_consumer()` in `apps/wiki/wiki_worker.py` now
  calls `bus.consume("verdict.ready", _handler, prefetch_count=1, queue_name="q.wiki")`.
- **Task 4**: full-suite regression gate (see below) — no additional commit needed since
  Tasks 1-3's commits already cover exactly the four planned files with no unrelated
  changes.
- **Task 5**: live-stack confidence check against the running `infotriage-brief` and
  rebuilt `infotriage-wiki` containers (see below).

## Task 2 Negative Control (recorded per plan requirement)

1. Temporarily removed `test.q.wiki` from `TEST_ROUTING_KEY_TO_QUEUE["verdict.ready"]`.
2. Re-ran `test_verdict_ready_fans_out_to_both_queues` → **FAILED** as required:
   `IndexError: list index out of range` when resolving `TEST_ROUTING_KEY_TO_QUEUE[rk][1]`
   for the wiki-equivalent queue override (proves the test actually depends on the second
   queue existing).
3. Restored the entry, re-ran the full file → **4 passed** (green).

## Full-Suite Regression Gate (Task 4)

| Run | Baseline (Task 1) | Final |
|---|---|---|
| `pytest tests/ -q` | 618 passed, 54 skipped | **620 passed, 54 skipped** (+2 new tests) |
| `pytest tests/ -q -m rabbitmq` | 7 passed | **9 passed** (+2 new tests) |
| mypy (4 changed files) | clean (3 files pre-change) | **clean, 0 errors, 4 files** |
| black --check (4 changed files) | clean | **clean, 4 files unchanged** |

Zero failures in either run. No regression in `tests/test_brief_*.py`,
`tests/test_triage_*.py`, or `tests/test_dlq_consumer.py`.

Cumulative commit file list across `ec52292` + `eb28331` + `9f0437b`: exactly
`libs/contracts/src/contracts/_bus_rabbitmq.py`, `tests/test_bus_rabbitmq.py`,
`tests/test_bus_consume.py`, `apps/wiki/wiki_worker.py` — no unrelated files. The
pre-existing uncommitted changes in `apps/brief/vault_writer.py` and
`apps/triage/worker.py` were left untouched throughout (confirmed clean of any staged
changes at every commit).

## Task 5 Live-Stack Confidence Check

`infotriage-brief` was never stopped or restarted (`StartedAt` remained
`2026-07-25T10:41:00Z` across the entire test). Only `infotriage-wiki` was rebuilt
(`docker compose build wiki`) and restarted (`docker compose up -d wiki`) to pick up the
new bus code, coming back in its normal periodic mode.

**Before/after RabbitMQ delivery counters** (management API, basic auth
`infotriage:infotriage_rmq`):

| Queue | Before `deliver_get` | After `deliver_get` | Delta |
|---|---|---|---|
| `q.brief` | 28 | 29 | **+1** |
| `q.wiki` | (404 — not yet declared; periodic mode never opens a bus connection) | 1 | **+1** |

A second, temporary `wiki_worker.py --mode events --health-port 22099` process was
started detached inside the already-running `infotriage-wiki` container (`docker exec -d`)
alongside the deployed periodic-mode process. One real `verdict.ready` event was published
from the host with a fresh item_id (`live-fanout-test-9bced4e2`) via `RabbitMQBus` on
`PYTHONPATH`. The temporary process's log confirmed the handler fired:

```
{"message": "verdict.ready item_id=live-fanout-test-9bced4e2 — refreshing wiki pages", ...}
{"message": "wiki page written: /vault/wiki/auto/google.md", ...}
```

`q.wiki`'s `ack` counter reached 1 (confirmed after a ~15s management-API stats-refresh
lag) — the message was fully processed and acknowledged, not just delivered.

Log grep for `topology mismatch` across both `infotriage-wiki` and `infotriage-brief`
(last 10 minutes) returned **zero hits** in both — no broker-side queue rebuild occurred,
confirming the T-BUSFAN-01 mitigation (identical queue arguments) held.

**Restoration**: `docker compose restart wiki` killed the temporary events-mode process
and returned the container to periodic mode. Confirmed:
- `docker ps` shows `infotriage-wiki` healthy, back in periodic mode
  (log: `"sleeping for 3600s before next wiki generation"`), health endpoint returns 200.
- `q.wiki` consumer count dropped to 0 after restart.
- No process listening on port 22099 inside the container (`/proc/net/tcp` grep, no match).
- `infotriage-brief`'s `StartedAt` unchanged throughout — confirmed never restarted.

## Deviations from Plan

### Auto-fixed Issues

None — plan executed as designed for Tasks 2, 3, 5.

### Process Deviation (documented, not a Rule 1-4 fix)

**Per-task commits instead of one squashed commit.** The plan's Task 4 action describes
committing all four files in a single commit. This executor's standard protocol commits
each task atomically as it completes, and Task 1 was already committed separately
(`ec52292`) in the prior session with the user's explicit approval to continue in the same
mode. Tasks 2 and 3 followed the same pattern (`eb28331`, `9f0437b`). The cumulative file
set across all three commits is exactly the four planned files with no unrelated changes —
satisfying the underlying intent (a clean, reviewable, fully-traceable change) even though
it is three atomic commits rather than one squashed commit.

## Commits

- `ec52292` — feat(bus): widen ROUTING_KEY_TO_QUEUE to list-of-queues, add consume(queue_name=)
- `eb28331` — test(bus): prove verdict.ready fans out to q.brief AND q.wiki
- `9f0437b` — fix(wiki): attach events-mode consumer to q.wiki instead of q.brief

## Known Stubs

None.

## Threat Flags

None — this change closes T-BUSFAN-01 and T-BUSFAN-02 exactly as planned, introduces no
new network surface, and the live test used only pre-existing dev credentials already
present in the repo.

## Self-Check: PASSED

- `libs/contracts/src/contracts/_bus_rabbitmq.py` — FOUND
- `tests/test_bus_rabbitmq.py` — FOUND
- `tests/test_bus_consume.py` — FOUND
- `apps/wiki/wiki_worker.py` — FOUND
- Commit `ec52292` — FOUND in `git log --oneline --all`
- Commit `eb28331` — FOUND in `git log --oneline --all`
- Commit `9f0437b` — FOUND in `git log --oneline --all`
