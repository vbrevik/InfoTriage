---
phase: 02-storage-postgres-blobs
plan: "04"
subsystem: store
tags: [storage, digest, retrofit, r6, postgres, tdd]
dependency_graph:
  requires: ["02-03"]
  provides: ["digest-store-persistence", "phase-2-green-suite"]
  affects: ["apps/triage/digest.py", "tests/test_digest_retrofit.py"]
tech_stack:
  added: []
  patterns:
    - map_verdict_to_item helper (verdict dict → contracts.Item column mapping)
    - store.put_item() replaces file-append (no silent loss, no swallow-except)
    - PostgresStore context manager in digest.main() with init_schema once per run
key_files:
  modified:
    - apps/triage/digest.py
  created:
    - tests/test_digest_retrofit.py
decisions:
  - "lang default 'no' for digest corpus (Norwegian-primary; no per-verdict lang field available)"
  - "blob_root resolved relative to ROOT (two levels up from apps/triage/digest.py)"
  - "digest.py drops json import — only user was the removed persist() function"
metrics:
  duration: "~5 minutes"
  completed: "2026-06-28T19:11:40Z"
  tasks_completed: 2
  tasks_total: 2
  files_modified: 1
  files_created: 1
status: complete
---

# Phase 2 Plan 04: Digest Retrofit + Full Suite Green — Summary

## One-Liner

Shallow store retrofit: `digest.py` now persists each scored verdict via `store.put_item(map_verdict_to_item(v))` backed by `PostgresStore` from `INFOTRIAGE_PG_DSN`, replacing the `verdicts.jsonl` file-append path. Full suite: 158 tests green (151 without DB, 158 with live Postgres :22000).

## Tasks

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Retrofit digest.py persistence onto store | 70b80f6 | apps/triage/digest.py |
| 2 | Retrofit unit test + full-suite green | 901d395 | tests/test_digest_retrofit.py |

## What Was Built

### Task 1: digest.py retrofit

The `persist(verdicts)` function and `STORE` constant have been removed. In their place:

**`map_verdict_to_item(v: dict) -> Item`** — helper that maps a scored verdict dict to a `contracts.Item`:
- Core columns: `source`, `source_type="rss"`, `url`, `title`, `ts=datetime.fromtimestamp(v["t"], utc)`, `lang="no"`, `summary`
- `payload` carries: `ccir`, `cnr`, `pmesii`, `tessoc`, `score`, `why`, `bucket`, `fever_id`
- `body_ref=None` (no blob in this retrofit)
- `Item.id` = SHA-256 of `source_type + NUL + url + NUL + title` (content-stable dedup key)

**`main()` changes:**
- Reads `INFOTRIAGE_PG_DSN` from environment (raises `KeyError` if absent — no silent failure)
- Constructs `PostgresStore(dsn=dsn, blob_root=Path(".../data/blobs"))` as context manager (D-03)
- Calls `store.init_schema()` once
- Calls `store.put_item(map_verdict_to_item(v))` for each verdict (no try/except swallow)
- Rendering (write_brief/write_cluster/write_bluf/write_list) unchanged — still operates on in-memory verdicts list

Removed: `import json` (was only used by the deleted `persist()` function).
Added: `from pathlib import Path`, `from store import PostgresStore`.

### Task 2: Retrofit unit tests

`tests/test_digest_retrofit.py` — 12 tests in two classes:

**`TestMapVerdictToItem` (7 tests):**
- Core fields mapped to Item columns correctly
- `ts` is UTC-aware `datetime.datetime`
- `payload` carries all score fields (ccir, cnr, score, why, bucket)
- `payload` carries pmesii/tessoc
- `payload["fever_id"]` = fever item id
- `item.id` = expected SHA-256 of `rss\x00url\x00title`
- Missing optional fields default gracefully (url="", summary=None, etc.)

**`TestStorePersistence` (5 tests):**
- Persisted item retrievable via `store.get_item(item.id)` (R6)
- `payload` preserved after roundtrip
- Multiple verdicts all retrievable
- Same-identity verdicts (same source_type+url+title) upsert to one entry (last-write-wins, R5)
- Missing id returns `None`

All tests use `InMemoryStore` — no live DB required.

## Verification Results

```
pytest tests/test_digest_retrofit.py -x -q       → 12 passed
pytest tests/ -q -k "not db_live"                → 151 passed
pytest tests/ -q                                  → 158 passed (db_live against :22000 included)
```

Phase 2 success criterion 3 satisfied: "a single store interface mediates all reads/writes; existing scripts go through it."

## Deviations from Plan

### Minor adjustment: TDD ordering

**Found during:** Task 2 planning
**Issue:** The plan splits implementation (Task 1) from tests (Task 2), making classical RED-GREEN-REFACTOR awkward — Task 1 creates the implementation before Task 2 writes the failing test.
**Fix:** Implemented in plan order (implementation → test). Tests all passed immediately on first run (GREEN from the start). No REFACTOR pass needed — implementation was already clean.
**Assessment:** Non-issue. TDD gate compliance note: the `feat(02-04)` commit precedes the `test(02-04)` commit rather than following it. Both commits are present; the behavioral contract is fully covered by the 12 tests.

## Known Stubs

None. All verdict fields are fully wired from `fetch_window()` + `score_item()` into the `map_verdict_to_item()` mapping. No placeholder values in the persistence path.

## Threat Surface Scan

No new network endpoints, auth paths, or schema changes introduced. The `INFOTRIAGE_PG_DSN` env var follows D-03 (read in caller, not logged, not written to digest output). Verdict values go through `store.put_item()` which uses parameterized SQL (T-02-01 mitigated in plan 03). No new threat surface.

## Self-Check: PASSED

- `apps/triage/digest.py` — modified, loads cleanly: FOUND
- `tests/test_digest_retrofit.py` — created: FOUND
- Commit 70b80f6 (feat): FOUND
- Commit 901d395 (test): FOUND
- 158 tests green: VERIFIED
