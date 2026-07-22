---
phase: 11-socmint
plan: 01
wave: 6
status: complete
goal: Integrate SOCMINT and authoritative Arctic data via MCP adapters, extend Item provenance, and close the Phase 999.1 translation backlog
verified: 2026-07-22
verified_by: "full pytest 518 passed / 61 skipped (default); make test-integration 579 passed / 0 failed / 0 skipped; mypy clean; black clean"
---

# 11-01-SUMMARY.md — SOCMINT + Arctic collection (complete)

Phase 11 rounded out the InfoTriage collection picture by adding SOCMINT and Arctic data sources, extending the `Item` schema with provenance metadata, and closing the long-standing Phase 999.1 backlog item for on-demand local-LLM translation.

## What shipped

### Wave 1: Doctrine & Schema Foundation

- `docs/adr/ADR-014-socmint-legal-and-tos.md`:
  - Documents legal/ToS posture for Telegram (public channels only), BarentsWatch/AIS, and YouTube.
  - Explicitly blocks unlicensed ACLED data from local LLM training or ingestion.
  - Aligns SOCMINT collection with ADR-004 (local-only LLM/transcription).
- `libs/contracts/src/contracts/_item.py`:
  - Extended `Item` schema with `discipline` (OSINT, SOCMINT, MASINT/AIS, etc.) and `admiralty_reliability` (A-F + 1-6, e.g. "A1").
  - Added Pydantic validation for allowed values and patterns.
- `libs/store/src/store/_protocol.py`, `_postgres.py`, `_inmemory.py`:
  - Storage protocol and backends support the new provenance fields.
  - Postgres migration added new columns with `NULL` defaults for backward compatibility.

### Wave 2: Validation, ACLED Gate & Compose Wiring

- `libs/contracts/src/contracts/_item.py`:
  - `discipline` and `admiralty_reliability` validation patterns enforced at the schema level.
- `docker-compose.yml`:
  - Added `ingest-telegram` and `ingest-barentswatch` services with health checks, restart policies, and required environment variables.
- `.env.example`:
  - Added `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `BARENTSWATCH_CLIENT_ID`, `ACLED_LICENSE_KEY`, etc.
- ACLED license gate stub in the contracts layer refuses ingestion when `ACLED_LICENSE_KEY` is missing or empty.

### Wave 3: MCP Adapters — Telegram & BarentsWatch

- `apps/ingest-telegram/`:
  - `telegram_ingest.py`: Telethon-based channel reader, configurable `--since`, `--channel`, `--dry-run`.
  - Emits `Item` records with `source_type="telegram"`, `discipline="SOCMINT"`, and a default Admiralty reliability.
  - `main.py`, `Dockerfile`, `requirements.txt`: containerized FastAPI/health endpoint and periodic runner.
  - `tests/test_ingest_telegram.py`: mocked Telethon client tests.
- `apps/ingest-barentswatch/`:
  - `barentswatch_ingest.py`: AIS polling adapter for configurable area/ship list.
  - Emits `Item` records with `source_type="ais"`, `discipline="MASINT/AIS"`, and Admiralty reliability.
  - `main.py`, `Dockerfile`, `requirements.txt`: containerized service with health endpoint.
  - `tests/test_ingest_barentswatch.py`: mocked API tests.

### Wave 4: Translation on Demand (Phase 999.1 backlog)

- `libs/contracts/src/contracts/_translation.py`:
  - `translate_to()` helper for local-LLM translation.
  - `TranslationCache` protocol + `NOOP_CACHE` for callers that don't need persistence.
- `libs/store/src/store/_postgres.py`:
  - `PostgresTranslationCache` keyed by `(text_hash, target_lang)`.
- `apps/brief/_i18n.py`:
  - Shared `_maybe_translate()` helper for renderer and vault writer.
- `apps/brief/renderer.py`, `vault_writer.py`, `consumer.py`, `main.py`:
  - Translation surface threaded through SAB and Obsidian reading surfaces.
- `tests/test_translation_on_demand.py`:
  - Unit tests for caching and end-to-end tests through `render_brief()`.
- `.github/workflows/lint.yml`: bumped `actions/checkout` and `actions/setup-python` to v7.
- `pyproject.toml`: suppressed upstream `starlette` `PendingDeprecationWarning`.

### Wave 5: Advanced Media — YouTube Transcription

- `apps/ingest-youtube/youtube_ingest.py`:
  - Opt-in local audio transcription via `faster-whisper`.
  - Per-channel `transcribe: true` or global `INFOTRIAGE_YOUTUBE_TRANSCRIBE=1` flag.
  - Process-level model cache with thread-safe loading; runs off the event loop via `asyncio.to_thread`.
  - Fallback stubs on any download/STT failure so ingestion is never blocked.
- `apps/ingest-youtube/Dockerfile`:
  - Installed `ffmpeg` and `libgomp1`.
  - Added optional `PRELOAD_WHISPER_MODEL` build arg to pre-download the model.
- `apps/ingest-youtube/requirements.txt`: added `faster-whisper>=1.0.0`.

### Wave 6: Closeout

- `.planning/phases/11-socmint/11-01-SUMMARY.md` (this file).
- `.planning/STATE.md` and `.planning/ROADMAP.md` updated to mark Phase 11 complete.
- Phase 999.1 backlog placeholder archived.

## Deviations from 11-PLAN.md

| Plan | Actual | Rationale |
|------|--------|-----------|
| Translation cache sketched in `libs/contracts/src/contracts/_translation.py`. | Postgres-backed cache lives in `libs/store/src/store/_postgres.py` as a store-native implementation. | Durable, shareable cache belongs with the store layer. |
| Plan assumed translation surfaced only in Obsidian/SAB. | All brief reading surfaces (renderer, vault writer) support translation. | Consistent operator experience across reading surfaces. |
| Plan did not anticipate a dedicated `_i18n.py` module. | Added `apps/brief/_i18n.py` to centralize translation logic. | Avoids duplication between renderer and vault writer. |
| Plan did not mention CI/version bumps. | Updated `lint.yml` action versions and suppressed upstream starlette warning. | Keep CI green and test output clean. |
| ACLED adapter planned as a full `ingest-acled` service. | Implemented as a contracts-level stub/license gate only. | No ACLED data is ingested without a paid license; full adapter deferred until license is obtained. |

## Decisions recorded

- **Local-only constraint:** Translation and transcription route through local Qwen36 / Whisper only (ADR-004). No cloud APIs are used.
- **Cache key:** `(sha256(text).hexdigest(), target_lang)` — deterministic and stable across processes.
- **Best-effort transcription:** Download/STT failures fallback gracefully; ingestion is never blocked.
- **Schema backward compatibility:** New `discipline` and `admiralty_reliability` columns default to `NULL` so existing rows remain valid.
- **Public channels only:** ADR-014 restricts Telegram collection to public channels; operator is responsible for channel selection and export compliance.
- **ACLED hard block:** Unlicensed ACLED data must not reach the local LLM or storage; ingestion requires a valid paid license.

## Tests / verification

- `pytest tests/test_ingest_telegram.py -q` — green
- `pytest tests/test_ingest_barentswatch.py -q` — green
- `pytest tests/test_translation_on_demand.py -q` — green
- `pytest tests/test_store_contract.py -q` — green (metadata round-trip)
- `pytest tests/test_ingest_youtube.py -q` — green
- Full default suite: `pytest -q --tb=short` — **518 passed, 61 skipped, 0 failed**
- Full integration suite (`make -f ops/Makefile test-integration`) — **579 passed, 0 failed, 0 skipped**
- `mypy` on modified Python files — clean
- `black --check` across project — clean
- `docker compose config` parses without errors.

## Files touched

### New
- `docs/adr/ADR-014-socmint-legal-and-tos.md`
- `apps/ingest-telegram/` (all files)
- `apps/ingest-barentswatch/` (all files)
- `libs/contracts/src/contracts/_translation.py`
- `apps/brief/_i18n.py`
- `tests/test_ingest_telegram.py`
- `tests/test_ingest_barentswatch.py`
- `tests/test_translation_on_demand.py`
- `libs/store/sql/008-translation-cache.sql`

### Modified
- `libs/contracts/src/contracts/_item.py` — discipline + reliability fields and validation
- `libs/store/src/store/_protocol.py` — protocol support for new fields
- `libs/store/src/store/_postgres.py` — Postgres support + `PostgresTranslationCache`
- `libs/store/src/store/_inmemory.py` — InMemory support
- `libs/store/src/store/__init__.py` — exported `PostgresTranslationCache`
- `docker-compose.yml` — added `ingest-telegram` and `ingest-barentswatch`
- `.env.example` — new env vars
- `apps/brief/renderer.py` — threaded `TranslationCache`
- `apps/brief/vault_writer.py` — threaded `TranslationCache`
- `apps/brief/consumer.py` / `apps/brief/main.py` — instantiate and pass `PostgresTranslationCache`
- `apps/ingest-youtube/youtube_ingest.py` — transcription upgrade
- `apps/ingest-youtube/Dockerfile` — ffmpeg, libgomp1, optional Whisper pre-load
- `apps/ingest-youtube/requirements.txt` — faster-whisper
- `tests/test_store_integration.py` — expected tables include `translation_cache`
- `tests/conftest.py` — `TRUNCATE` includes `translation_cache`
- `.github/workflows/lint.yml` — bumped action versions to v7
- `pyproject.toml` — suppressed starlette `PendingDeprecationWarning`

### Planning docs
- `.planning/STATE.md` — Phase 11 marked complete
- `.planning/ROADMAP.md` — Phase 11 marked complete; Phase 999.1 backlog closed
- `.planning/phases/11-socmint/11-PLAN.md` — all waves marked complete
- `.planning/phases/11-socmint/11-WAVE4-SUMMARY.md` — intermediate summary retained
- `.planning/phases/999.1-translation-on-demand-per-item-ru-de-es-to-no-en/` — archived

## Acceptance criteria

From 11-PLAN.md §success_criteria:

- [x] `ingest-telegram`, `ingest-barentswatch`, and upgraded `ingest-youtube` are containerized MCP adapters.
- [x] New items carry discipline tags and Admiralty reliability ratings.
- [x] On-demand translation is available in the vault/brief reading surface for non-no/en items (Phase 999.1 closed).
- [x] ACLED data is gated by a paid-license check and never reaches the local LLM without one.
- [x] SOCMINT legal/ToS posture is documented in ADR-014.

## Next

- **Phase 12: CNR alerting / dissemination** is next and ready for planning.
- M1 Foundation milestone remains complete; accumulated Phase 11 commits are on `origin/main`.
