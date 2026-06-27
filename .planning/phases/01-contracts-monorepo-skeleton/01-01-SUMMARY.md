---
phase: 01-contracts-monorepo-skeleton
plan: "01"
subsystem: contracts
tags: [pydantic, yaml, bus, packaging, tdd]
status: complete

dependency_graph:
  requires: []
  provides:
    - contracts.Item
    - contracts.ItemIngested
    - contracts.VerdictReady
    - contracts.SabPublished
    - contracts.FeedUnhealthy
    - contracts.to_frontmatter
    - contracts.from_frontmatter
    - contracts.BusClient
    - contracts.InMemoryBus
  affects:
    - plan 01-02 (monorepo restructure imports Item from contracts)
    - all Phase 2+ apps (pip install -e libs/contracts)

tech_stack:
  added:
    - pydantic v2 (Item, event schemas, AwareDatetime, computed_field, Field max_length)
    - PyYAML 6.0 (yaml.safe_dump / yaml.safe_load — safe loader only, T-01-01 mitigated)
    - setuptools>=68 (pyproject.toml src-layout editable install)
  patterns:
    - pydantic v2 @computed_field @property for read-only sha256 id
    - Literal discriminators for bus routing key validation
    - typing.Protocol @runtime_checkable for structural bus interface
    - YAML frontmatter codec (---\n<body>---\n convention)

key_files:
  created:
    - libs/contracts/pyproject.toml
    - libs/contracts/src/contracts/__init__.py
    - libs/contracts/src/contracts/_item.py
    - libs/contracts/src/contracts/_events.py
    - libs/contracts/src/contracts/_codec.py
    - libs/contracts/src/contracts/_bus.py
    - tests/test_contracts.py
    - requirements-dev.txt
  modified:
    - .gitignore (added *.egg-info/)

decisions:
  - "setuptools.build_meta (not the legacy backend string in Pattern 6 of RESEARCH.md which was incorrect)"
  - "All 8 files (package + test + requirements-dev.txt) created in a single wave — codec and bus implemented in Task 1 GREEN since __init__.py imports them at module load time"
  - "27 test functions written (minimum 11 required) — covers all R1-R4 behaviors plus extras (cross-routing-key isolation, empty frontmatter, Protocol isinstance check)"

metrics:
  duration: "5m"
  completed: "2026-06-27"
  tasks_completed: 3
  tasks_total: 3
  files_created: 8
  files_modified: 1
  test_count: 27
---

# Phase 01 Plan 01: Contracts Package Summary

pip-installable `contracts` package with pydantic v2 Item model, four bus event schemas, a PyYAML frontmatter codec, and a typing.Protocol bus client with in-memory implementation — proven by 27 pytest functions covering all R1-R4 behaviors.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 RED | Failing tests for contracts behaviors | a6ad521 | tests/test_contracts.py |
| 1/2 GREEN | Contracts package implementation | 02d29a8 | libs/contracts/**, requirements-dev.txt |
| 3 | .gitignore update (egg-info) | d3801d3 | .gitignore |

## What Was Built

### Package structure (`libs/contracts/`)

- **`pyproject.toml`**: `setuptools.build_meta` build backend, `name="contracts"`, `version="0.1.0"`, `requires-python=">=3.11"`, deps `pydantic>=2.0` + `PyYAML>=6.0`, `[tool.setuptools.packages.find] where=["src"]`.
- **`_item.py`**: `Item(BaseModel)` with core fields `source`, `source_type`, `url` (default `""`), `title`, `ts` (`AwareDatetime` — naive datetime rejected at validation), `lang`; content fields `summary`/`body_ref` (Optional); open `payload: dict` and `attachments: list`; read-only `@computed_field @property id` = `sha256(source_type + NUL + url + NUL + title)`.
- **`_events.py`**: `ItemIngested`, `VerdictReady`, `SabPublished`, `FeedUnhealthy` — each with a Literal `event` routing-key field. `VerdictReady.cnr` constrained to `Literal["I","II","Routine"]`; `VerdictReady.bucket` to `Literal["keep","maybe","skip"]`; `FeedUnhealthy.reason` capped at `Field(max_length=120)` (UI-SPEC §2). `SabPublished` carries all fields required for Back-in-time versioned BLUF rendering.
- **`_codec.py`**: `to_frontmatter(payload) -> str` wraps `yaml.safe_dump` in `---\n...\n---\n`; `from_frontmatter(text) -> dict` splits on `"---"` (maxsplit=2), raises `ValueError` on missing delimiters, returns `{}` on empty block. `yaml.safe_load` exclusively (T-01-01 mitigated).
- **`_bus.py`**: `@runtime_checkable BusClient(Protocol)` with `publish`/`subscribe`; `InMemoryBus` concrete impl with `_queues: dict[str, list[dict]]` and `_seen: set[str]`. Second publish with same `item_id` is a no-op (dedup). `subscribe` returns FIFO shallow copy or `[]` for unused routing key.
- **`__init__.py`**: Exports all 9 public symbols with `__all__`.

### Test coverage (`tests/test_contracts.py`)

27 pytest functions (no unittest, no class wrapper):

| Group | Tests |
|-------|-------|
| Item (R1) | id determinism, no-url hash, no-url default, missing title raises, missing source_type raises, naive ts raises, open payload dict |
| Events (R2) | ItemIngested valid + missing required raises; VerdictReady valid + invalid cnr raises + invalid bucket raises + missing score raises; SabPublished valid + missing total_keep raises; FeedUnhealthy valid + 120-char reason ok + 121-char reason raises + missing feed_url raises |
| Codec (R3) | Round-trip (nested dict/list/None/Norwegian unicode/tz-aware datetime/[N] markers); no delimiters raises ValueError; empty frontmatter returns {} |
| Bus (R4) | dedup, FIFO, empty subscribe no-op, cross-routing-key isolation, isinstance(InMemoryBus(), BusClient) |

### Editable install

`pip install -e libs/contracts` — confirmed working. `requirements-dev.txt` contains `-e ./libs/contracts` and `pytest>=8.0`.

## Verification Results

```
TASK1 OK  — id determinism, empty-url hash, naive-ts rejection, bad-cnr rejection, reason>120 rejection
TASK2 OK  — codec round-trip fidelity, missing-frontmatter ValueError, dedup, FIFO, empty-subscribe no-op
pytest tests/test_contracts.py -q  → 27 passed
pytest tests/ -q  → 83 passed (27 new + 56 pre-existing)
Security grep: 0 matches (no credentials or host:port in libs/contracts/src)
```

## Deviations from Plan

### Auto-fixed (Rule 3 — blocking issue)

**[Rule 3 - Blocking] Codec and bus implemented in Task 1 GREEN alongside Item/events**

- **Found during:** Task 1 implementation
- **Issue:** `__init__.py` imports `_codec` and `_bus` at module load time. If only `_item.py` and `_events.py` existed, the editable install would fail on any `from contracts import Item` call. Since the package files must all exist before the install can be verified, implementing the codec and bus in the same wave was the only way to satisfy the Task 1 acceptance criterion `python3 -c "from contracts import Item"`.
- **Fix:** Created `_codec.py` and `_bus.py` in the same commit as `_item.py` and `_events.py`. Task 2 verification was run immediately after and confirmed TASK2 OK.
- **Files modified:** `libs/contracts/src/contracts/_codec.py`, `libs/contracts/src/contracts/_bus.py`
- **Commit:** 02d29a8

### Minor deviation

**RESEARCH.md Pattern 6 incorrect build backend string**

- Pattern 6 in 01-RESEARCH.md listed `build-backend = "setuptools.backends.legacy:build"`. The PLAN.md Task 1 action block explicitly noted this is incorrect and instructed using `"setuptools.build_meta"`. Used the correct value.

## Known Stubs

None — all exported symbols are fully implemented and verified.

## Threat Flags

None — no new network endpoints, auth paths, file access patterns, or schema changes at trust boundaries introduced beyond those in the plan's threat model.

## Self-Check: PASSED

All 9 created/modified files verified on disk. All 3 commits (a6ad521, 02d29a8, d3801d3) confirmed in git log.
