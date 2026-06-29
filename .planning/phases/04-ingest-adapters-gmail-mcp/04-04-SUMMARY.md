---
phase: 04-ingest-adapters-gmail-mcp
plan: "04"
subsystem: ingest-obsidian
tags: [obsidian, ingest, fastapi, tdd, adapter, read-only-vault, D-09]
status: complete

dependency_graph:
  requires:
    - 04-01  # ingest_common: persist_and_publish, make_trigger_app, build_store, build_bus
    - libs/contracts  # Item, from_frontmatter (yaml.safe_load codec)
    - libs/store      # InMemoryStore (tests), PostgresStore (production)
  provides:
    - apps/ingest-obsidian/obsidian_ingest.py  # ingest() coroutine, fetch_items, item_from_obsidian_clip, _infer_lang
    - apps/ingest-obsidian/main.py             # FastAPI trigger app
    - apps/ingest-obsidian/Dockerfile          # python:3.12-slim container
    - apps/ingest-obsidian/requirements.txt
    - tests/test_ingest_obsidian.py
  affects:
    - apps/ingest-obsidian/  # greenfield directory created

tech_stack:
  added:
    - obsidian_ingest.py uses: glob, re, os, datetime, contracts.from_frontmatter, contracts.Item
    - ingest_common.persist_and_publish (get_item pre-check idempotency pattern)
    - ingest_common.make_trigger_app (POST /run D-01 single-instance lock)
    - ingest_common.build_store / build_bus (env-driven runtime construction)
  patterns:
    - TDD: RED commit (510f96b) → GREEN commit (e3ab294)
    - D-09 field mapping via from_frontmatter (yaml.safe_load)
    - Read-only vault access pattern (no write/append/delete against vault)
    - Norwegian language inference (regex [æøåÆØÅ])
    - get_item pre-check idempotency (RESEARCH Pattern 2)

key_files:
  created:
    - apps/ingest-obsidian/obsidian_ingest.py
    - apps/ingest-obsidian/main.py
    - apps/ingest-obsidian/Dockerfile
    - apps/ingest-obsidian/requirements.txt
    - tests/test_ingest_obsidian.py
  modified: []

decisions:
  - "_infer_lang returns 'und' for empty/None title (not 'en') — empty title is indeterminate, not English"
  - "from_frontmatter ValueError caught in item_from_obsidian_clip → empty fm dict; clip still ingested"
  - "build_bus/build_store monkeypatched in tests; InMemoryBus has no close() so hasattr(bus, 'close') guard used in ingest()"
  - "ingest_common included in Dockerfile COPY+pip install --no-deps (beyond contracts/store) per plan action"

metrics:
  duration: "~5 minutes"
  completed: "2026-06-29T11:37:59Z"
  tasks_completed: 2
  tasks_total: 2
  files_created: 5
  files_modified: 0
  tests_added: 3
  tests_green: 3
  full_suite: "161 passed (not db_live and not rabbitmq)"
---

# Phase 04 Plan 04: ingest-obsidian Summary

**One-liner:** Obsidian Web Clipper adapter reading `articles-inbox/*.md` via `from_frontmatter()` YAML codec into Item with D-09 field mapping, Norwegian language inference, and read-only vault enforcement.

## What Was Built

Greenfield `apps/ingest-obsidian/` containerized ingest adapter:

- **`obsidian_ingest.py`** — core adapter module:
  - `_infer_lang(text)` — regex `[æøåÆØÅ]` → "no"; empty → "und"; else "en"
  - `item_from_obsidian_clip(path)` — reads `.md` file (read-only), calls `from_frontmatter()` (yaml.safe_load), maps D-09 fields; missing title/url/date → safe defaults + WARNING log; clip not rejected
  - `fetch_items(inbox_dir)` — globs `*.md`, returns sorted list of Items
  - `async def ingest()` — entry coroutine for `make_trigger_app`; reads `OBSIDIAN_VAULT_PATH`, calls `fetch_items`, persists and publishes each item via `persist_and_publish`

- **`main.py`** — `app = make_trigger_app(ingest, name="ingest-obsidian")` (POST /run + GET /health, D-01/D-02)

- **`Dockerfile`** — python:3.12-slim; COPY+`pip install --no-deps` contracts/store/ingest_common; uvicorn on port 8000; no credential ARG/ENV in image (D-10/D-11)

- **`requirements.txt`** — fastapi, uvicorn, aio-pika, psycopg[binary], pgvector, numpy, pydantic, PyYAML, httpx (no yt-dlp/whisper/google libs)

- **`tests/test_ingest_obsidian.py`** — 3 tests:
  1. `test_ingest_d09_field_mapping` — 2 clips; verifies title/url/site/description/date mapping and lang ("no" for Norwegian clip)
  2. `test_ingest_missing_fields_not_rejected` — empty frontmatter; verifies fallback defaults, warning logged, clip ingested (not rejected)
  3. `test_ingest_idempotency` — 2 runs over same clip; verifies 1 row + 1 bus event

## Verification Results

| Check | Result |
|-------|--------|
| `pytest tests/test_ingest_obsidian.py -x` | 3 passed |
| Read-only vault grep gate (no write/append) | PASS |
| Safe YAML gate (no yaml.load, no shutil.rmtree) | PASS |
| `source_type="obsidian"` in obsidian_ingest.py | PASS |
| `from_frontmatter(` call in obsidian_ingest.py | PASS |
| Dockerfile FROM python:3.12-slim | PASS |
| Dockerfile pip install --no-deps contracts/store/ingest_common | PASS |
| CMD uvicorn main:app --port 8000 | PASS |
| No credential ARG/ENV in Dockerfile | PASS |
| Full suite `pytest tests/ -m "not db_live and not rabbitmq"` | 161 passed |

## TDD Gate Compliance

| Gate | Commit | Status |
|------|--------|--------|
| RED (test) | 510f96b | `test(04-04): add failing tests for ingest-obsidian D-09 mapping + idempotency (R4)` |
| GREEN (feat) | e3ab294 | `feat(04-04): implement ingest-obsidian — clip frontmatter → Item (D-09)` |
| REFACTOR | — | Not needed — implementation clean on first pass |

## Commits

| Hash | Type | Description |
|------|------|-------------|
| 510f96b | test | TDD RED: failing tests for D-09 mapping, missing-field fallback, idempotency |
| e3ab294 | feat | TDD GREEN: obsidian_ingest.py + main.py implementation |
| 14cbe92 | chore | Dockerfile + requirements.txt (D-10/D-11) |

## Deviations from Plan

None — plan executed exactly as written.

The `ingest_common` lib was added to the Dockerfile `COPY+pip install --no-deps` block (alongside contracts and store), as `obsidian_ingest.py` directly imports `persist_and_publish`, `make_trigger_app`, `build_store`, and `build_bus` from it. This is consistent with D-10 intent ("local libs") and matches the plan's `requirements.txt` description which excludes these from pip requirements.

## Threat Flags

No new threat surface beyond what the plan's `<threat_model>` covers:
- T-04-08 (YAML injection): mitigated — `from_frontmatter()` uses `yaml.safe_load`; no `yaml.load()` call
- T-04-09 (vault tampering): mitigated — vault files opened with `open(path, "r", ...)` only; no write/append/delete

## Known Stubs

None — all fields are wired. Production connections (Postgres + RabbitMQ) come from `build_store()`/`build_bus()` via env vars. Vault path comes from `OBSIDIAN_VAULT_PATH`. No placeholder data flows to any output.

## Self-Check: PASSED

All files created and all commits verified in git log.
