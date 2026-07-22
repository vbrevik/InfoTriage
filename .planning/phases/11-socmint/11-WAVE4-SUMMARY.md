---
phase: 11-socmint
plan: 01
wave: 4
status: complete
goal: On-demand local-LLM translation for non-no/en reading surfaces (Phase 999.1 backlog)
verified: 2026-07-22
verified_by: "pytest 513 passed / 61 skipped (default); 574 passed / 0 skipped (integration); mypy clean; black clean"
---

# 11-WAVE4-SUMMARY.md — Translation on Demand (complete)

Wave 4 closed the long-standing Phase 999.1 backlog item: on-demand translation of non-Norwegian/English source items for the Obsidian vault and SAB brief reading surfaces, using only the local LLM (ADR-004) and avoiding repeated LLM calls via a Postgres-backed translation cache.

## What shipped

### Translation helper & cache

- `libs/contracts/src/contracts/_translation.py`:
  - `translate_to(text, target_lang, source_lang=None, *, llm, cache=NOOP_CACHE)` — local-LLM translation helper.
  - `TranslationCache` protocol plus a `NOOP_CACHE` for callers that don't need persistence.
  - Translation result cached by `(text_hash, target_lang)` to avoid duplicate LLM work.
- `libs/store/src/store/_postgres.py`:
  - `PostgresTranslationCache` implementing `TranslationCache` with get/put backed by `infotriage.translation_cache`.
- `libs/store/sql/008-translation-cache.sql`:
  - DDL for `infotriage.translation_cache` keyed by `(text_hash, target_lang)`.
- `libs/store/src/store/__init__.py`:
  - Exported `PostgresTranslationCache`.

### Reading-surface integration

- `apps/brief/_i18n.py`:
  - `_maybe_translate()` helper used by renderer and vault writer.
- `apps/brief/renderer.py`:
  - `render_brief()`, `render_list()`, `render_cluster()` accept and thread an optional `TranslationCache`.
- `apps/brief/vault_writer.py`:
  - `write_item_obsidian()`, `write_sab_obsidian()`, `write_vault_digest()` thread the cache through translations.
- `apps/brief/consumer.py` / `apps/brief/main.py`:
  - Instantiate `PostgresTranslationCache(store)` and pass it down to rendering surfaces.

### Tests

- `tests/test_translation_on_demand.py`:
  - Unit tests for `translate_to()` caching behavior.
  - End-to-end test proving the cache is threaded through `render_brief()` and prevents duplicate LLM calls.
  - `db_live` test for `PostgresTranslationCache` persistence.
- `tests/test_store_integration.py`:
  - Updated expected tables list to include `translation_cache`.
- `tests/conftest.py`:
  - Added `translation_cache` to per-test `TRUNCATE` for isolation.

### CI / quality-of-life

- `.github/workflows/lint.yml`:
  - Bumped `actions/checkout` to v7 and `actions/setup-python` to v7 to silence Node.js 20 deprecation warnings.
- `pyproject.toml`:
  - Added `filterwarnings` entry to suppress the upstream `starlette.formparsers` `PendingDeprecationWarning`.

## Deviations from 11-PLAN.md

| Plan | Actual | Rationale |
|------|--------|-----------|
| Translation cache initially sketched in `libs/contracts/src/contracts/_translation.py`. | Postgres-backed cache lives in `libs/store/src/store/_postgres.py` as a store-native implementation. | A store-backed cache is more appropriate for a durable, shareable translation cache than a contracts-only module. |
| Plan did not anticipate a separate `_i18n.py` module. | Added `apps/brief/_i18n.py` to centralize translation logic shared by renderer and vault writer. | Cleaner separation; avoids duplicating `_maybe_translate()` logic. |
| Plan did not mention CI/version bumps. | Updated `lint.yml` action versions and suppressed upstream starlette warning. | Opportunities discovered during cleanup; keep CI green and test output clean. |
| Plan assumed only Obsidian/SAB surfaces. | Both `renderer.py` (SAB/list/cluster) and `vault_writer.py` (Obsidian notes) receive cache support. | All brief reading surfaces benefit from translation. |

## Decisions recorded

- **Local-only translation:** `translate_to()` routes through a configurable `llm` callable; no cloud translation APIs are used (ADR-004).
- **Cache key:** `(sha256(text).hexdigest(), target_lang)` — deterministic and stable across processes.
- **Cache is best-effort:** `NOOP_CACHE` allows callers to opt out without changing calling code.
- **Per-translation commit:** `PostgresTranslationCache.put()` commits immediately. This is durable but will also commit any pending transaction on the shared store connection. Known side effect; acceptable for current brief rendering pipeline.
- **Forward compatibility:** `TranslationCache` is a protocol, so alternate implementations (e.g., Redis, in-memory LRU) can be swapped in later.

## Tests / verification

- `pytest tests/test_translation_on_demand.py -q` — green
- `pytest tests/test_brief_renderer.py tests/test_vault_writer.py tests/test_brief_consumer.py -q` — green
- Full default suite: `pytest -q --tb=short` — **513 passed, 61 skipped, 0 failed**
- Full integration suite (`make -f ops/Makefile test-integration`) — **574 passed, 0 failed, 0 skipped**
- `mypy` on all modified Python files — clean
- `black --check apps/ libs/ tests/` — clean

## Files touched

### New
- `libs/store/sql/008-translation-cache.sql`
- `apps/brief/_i18n.py`
- `tests/test_translation_on_demand.py`

### Modified
- `libs/store/src/store/_postgres.py` — added `PostgresTranslationCache`
- `libs/store/src/store/__init__.py` — exported `PostgresTranslationCache`
- `apps/brief/renderer.py` — threaded `TranslationCache` through render functions
- `apps/brief/vault_writer.py` — threaded `TranslationCache` through vault writing functions
- `apps/brief/consumer.py` — instantiate and pass `PostgresTranslationCache`
- `apps/brief/main.py` — instantiate and pass `PostgresTranslationCache`
- `tests/test_store_integration.py` — expected tables include `translation_cache`
- `tests/conftest.py` — `TRUNCATE` includes `translation_cache`
- `.github/workflows/lint.yml` — bumped action versions to v7
- `pyproject.toml` — suppressed starlette `PendingDeprecationWarning`

### Planning docs
- `.planning/STATE.md` — Wave 4 marked complete
- `.planning/ROADMAP.md` — Phase 11 progress updated
- `.planning/phases/11-socmint/11-PLAN.md` — Wave 4 tasks marked complete

## Acceptance criteria

From 11-PLAN.md §Wave 4:

- [x] Russian source item shows an English/Norwegian translation in the vault/brief.
- [x] Translations are cached and not re-requested for the same text.
- [x] Translation helper uses the local LLM only (no cloud APIs).
- [x] Cache persistence is tested against Postgres.
- [x] Reading surfaces (renderer + vault writer) thread the cache end-to-end.

## Next

- Wave 5 (YouTube transcription) is unblocked and ready for execution.
- Phase 11 Wave 4 is functionally complete and committed to `origin/main`.
