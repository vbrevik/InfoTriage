---
phase: 02-storage-postgres-blobs
plan: "02"
subsystem: storage
status: complete
tags: [blob-store, protocol, inmemory, atom-projection, feedgen, stdlib, tdd, r4, r5, r7]

dependency_graph:
  requires:
    - 02-01 (libs/store package, editable install, db_live marker)
  provides:
    - libs/store/src/store/_blob.py (content-addressed blob store, R4)
    - libs/store/src/store/_protocol.py (Store @runtime_checkable Protocol, R5)
    - libs/store/src/store/_inmemory.py (dict-backed InMemoryStore fake, R5)
    - libs/store/src/store/_atom.py (pull-on-demand Atom projection, R7)
    - libs/store/src/store/__init__.py (exports Store, InMemoryStore, render_atom)
    - tests/test_store_blob.py (15 blob unit tests)
    - tests/test_store_contract.py (12 contract tests parametrized over inmemory+postgres)
    - tests/test_atom_projection.py (13 Atom projection unit tests)
  affects:
    - 02-03 (PostgresStore will satisfy the same Store Protocol + same contract tests)
    - 02-04 (digest.py retrofit will call store.put_item)

tech_stack:
  added:
    - feedgen 1.0.0 (already installed, now used in _atom.py)
    - defusedxml 0.7.1 (XXE-safe XML parsing in tests, T-00-01-XXE project mandate)
  patterns:
    - TDD: RED (test fails) → GREEN (impl passes) → commit for each of 3 tasks
    - Store Protocol mirrors BusClient from libs/contracts (same @runtime_checkable, same docstring style)
    - InMemoryStore mirrors InMemoryBus (dict-backed, no thread-safety for single-process scope)
    - _blob.py stdlib-only: hashlib + os.replace + re.fullmatch (no third-party imports)
    - 2-level shard path: root/<h[:2]>/<h[2:4]>/<h> (R4 SPEC)
    - Atomic blob write: tmp-sibling + os.replace; cleanup + re-raise on any failure (must-NOT)
    - Traversal guard: re.fullmatch(r'[0-9a-f]{64}', blob_hash) before any filesystem access (T-02-02)
    - Contract test parametrized over [inmemory, postgres]; postgres branch lazy-imports PostgresStore so file collects without plan-03

key_files:
  created:
    - libs/store/src/store/_blob.py
    - libs/store/src/store/_protocol.py
    - libs/store/src/store/_inmemory.py
    - libs/store/src/store/_atom.py
    - tests/test_store_blob.py
    - tests/test_store_contract.py
    - tests/test_atom_projection.py
  modified:
    - libs/store/src/store/__init__.py (exports Store, InMemoryStore, render_atom)

decisions:
  - "D-01a confirmed: put_blob/get_blob on the single Store Protocol interface; no separate BlobStore class"
  - "InMemoryStore blob ops delegate to _blob helpers against a filesystem tmp_path (not an in-memory dict) — tests actual shard path logic (A1 confirmed)"
  - "render_atom uses fixed epoch for feed header timestamp (deterministic R7 idempotency); caller can override if live updated needed"
  - "defusedxml.ElementTree used in all tests that parse XML, per T-00-01-XXE project mandate"

metrics:
  duration: "~7 minutes"
  completed: "2026-06-28"
  tasks_completed: 3
  tasks_total: 3
  files_created: 7
  files_modified: 1
---

# Phase 02 Plan 02: Store Core — Blob, Protocol, InMemoryStore, Atom Summary

One-liner: stdlib-only content-addressed blob store with atomicity and traversal guard, @runtime_checkable Store Protocol with dict-backed InMemoryStore fake, and pull-on-demand feedgen Atom projection filtering to RSS/YouTube only — all locked by 40 new unit tests across 3 test files.

## Summary

This plan builds the pure-Python behavioral core of the `store` package — no live database required.

**Task 1: Content-addressed blob store** (`_blob.py`) — stdlib-only module with `put_blob`/`get_blob`. Shard path is `root/<h[:2]>/<h[2:4]>/<h>` (R4). Writes are atomic via tmp-sibling + `os.replace()` (POSIX rename). Any write failure cleans up the temp file and re-raises — fail loud, never silent data loss (must-NOT prohibition). Path-traversal guard `_validate_hash` rejects any hash not matching `[0-9a-f]{64}` before any filesystem access (T-02-02). Duplicate put of identical bytes returns the hash immediately (dedup no-op, R4 idempotency). 15 tests covering all behaviors.

**Task 2: Store Protocol + InMemoryStore + contract tests** (`_protocol.py`, `_inmemory.py`, `__init__.py`, `test_store_contract.py`) — `@runtime_checkable` `Store` Protocol mirrors `BusClient` from Phase 1. `InMemoryStore` is a dict-backed fake that delegates blob ops to the `_blob` helpers (D-01a — same code path as PostgresStore will use). 12 contract tests parametrized over `[inmemory, postgres]`; the postgres param is auto-skipped when `:22000` is unreachable. Lazy import of `PostgresStore` inside the postgres fixture branch means the file collects cleanly before plan 03 creates `_postgres.py`.

**Task 3: Atom projection** (`_atom.py`) — `render_atom(store, limit=50) -> bytes` uses feedgen `FeedGenerator` (D-04b). Pulls from `store.list_items(source_type_in=["rss","yt"], limit=limit)` (D-04a — email excluded). Deterministic: fixed epoch in the feed header so identical store state → identical bytes (R7 idempotency). 13 tests covering rss/yt inclusion, imap exclusion, valid XML, determinism, empty store, and per-entry url/summary content.

All 87 prior tests remain green. Total after plan: 127 passed + 12 skipped (postgres contract test params).

## Task Results

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Content-addressed blob store with atomicity and traversal guard | f528cd1 | libs/store/src/store/_blob.py, tests/test_store_blob.py |
| 2 | Store Protocol + InMemoryStore + shared parametrized contract test | 36baf26 | _protocol.py, _inmemory.py, __init__.py, tests/test_store_contract.py |
| 3 | Pull-on-demand Atom projection + projection tests | fffb8b0 | libs/store/src/store/_atom.py, __init__.py, tests/test_atom_projection.py |

## Verification Results

```
pytest tests/test_store_blob.py tests/test_store_contract.py tests/test_atom_projection.py -q
40 passed, 12 skipped (postgres params, auto-skipped — no DB)

pytest tests/ -q
127 passed, 12 skipped — all prior tests green, no regressions
```

Protocol check:
```
from store import Store, InMemoryStore, render_atom
isinstance(InMemoryStore(blob_root=tmp), Store)  → True
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Upsert test updated `summary` instead of `title`**
- **Found during:** Task 2 (TDD GREEN — test failed)
- **Issue:** `test_put_item_upsert_last_write_wins` used `model_copy(update={"title": "Updated Title"})` to test last-write-wins. But `Item.id` is a `@computed_field` derived from `source_type + url + title` — changing the title changes the id, so the second `put_item` inserts a new entry rather than updating the existing one. The upsert never fired.
- **Fix:** Changed the upsert test to update `summary` (a non-id field), which preserves the item's id across both writes. Added an assertion `assert original.id == updated.id` to make the intent explicit.
- **Files modified:** tests/test_store_contract.py
- **No separate commit** — fixed in the same Task 2 GREEN phase before committing.

**2. [Rule 2 - Security] Used defusedxml.ElementTree in test XML parsing**
- **Found during:** Task 3 (writing test_atom_projection.py)
- **Issue:** Initial draft used `import xml.etree.ElementTree as ET` (stdlib). A security hook flagged XXE risk; the project has an existing mandate for `defusedxml` (T-00-01-XXE) for all XML parsing.
- **Fix:** Replaced with `import defusedxml.ElementTree as ET`. Although the XML being parsed is our own feedgen output (not untrusted network input), the project-wide mandate applies.
- **Files modified:** tests/test_atom_projection.py

## Known Stubs

None. All plan objectives fully implemented and verified by tests.

## Threat Flags

No new threat surface introduced. All threat mitigations from the plan's threat model are implemented:
- T-02-02: `_validate_hash` rejects non-64-char-hex before path construction (verified by test_traversal_guard_*)
- T-02-05: `list_items` and `render_atom` both carry `limit` parameters (200 / 50 defaults)

## Self-Check: PASSED
