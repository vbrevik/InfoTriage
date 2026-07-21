---
phase: 11-socmint
plan: 01
type: execute
wave: 2
depends_on:
  - 04-ingest-mcp-pattern
  - 08-entity-resolution
  - 10-wiki-llm
files_modified:
  - libs/contracts/src/contracts/_item.py
  - libs/store/src/store/_protocol.py
  - libs/store/src/store/_postgres.py
  - libs/store/src/store/_inmemory.py
  - apps/ingest-telegram/telegram_ingest.py
  - apps/ingest-telegram/main.py
  - apps/ingest-telegram/Dockerfile
  - apps/ingest-telegram/requirements.txt
  - apps/ingest-barentswatch/barentswatch_ingest.py
  - apps/ingest-barentswatch/main.py
  - apps/ingest-barentswatch/Dockerfile
  - apps/ingest-barentswatch/requirements.txt
  - apps/ingest-youtube/youtube_ingest.py
  - apps/brief/vault_writer.py
  - apps/brief/renderer.py
  - tests/test_ingest_telegram.py
  - tests/test_ingest_barentswatch.py
  - tests/test_translation_on_demand.py
  - docs/adr/ADR-014-socmint-legal-and-tos.md
autonomous: true
requirements: [ADR-003, ADR-004, ADR-006, spec §Obsidian, Phase-999.1-backlog]

must_haves:
  truths:
    - "SOCMINT and authoritative Arctic data are ingested via the MCP adapter pattern"
    - "All new collection sources carry discipline tags and Admiralty reliability ratings"
    - "On-demand translation (Phase 999.1 backlog) is available for non-no/en reading surfaces"
    - "ACLED data is gated by a paid-license check and is not fed to the local LLM"
    - "SOCMINT legal/ToS posture is documented and reviewed"
    - "Local-only LLM/transcription constraints from ADR-004 are respected"
  artifacts:
    - libs/contracts/src/contracts/_item.py (Item schema extension for discipline + reliability)
    - libs/store/src/store/_protocol.py + backends (schema support for reliability/discipline)
    - apps/ingest-telegram/ (Telethon MCP adapter)
    - apps/ingest-barentswatch/ (AIS MCP adapter)
    - apps/ingest-youtube/youtube_ingest.py (transcription upgrade)
    - apps/brief/vault_writer.py / renderer.py (translation surface hooks)
    - docs/adr/ADR-014-socmint-legal-and-tos.md
    - tests/test_ingest_telegram.py
    - tests/test_ingest_barentswatch.py
    - tests/test_translation_on_demand.py
  key_links:
    - "Follows the MCP adapter pattern from Phase 4"
    - "Uses Phase 8 entity resolution for Telegram/BarentsWatch actors and vessels"
    - "Feeds Phase 9/10 recall and wiki synthesis pipelines"
  prohibitions:
    - statement: "MUST NOT send unlicensed ACLED data to the local LLM"
      status: open
      verification: "Hard block in ACLED adapter and ingestion pipeline"
    - statement: "MUST NOT use cloud translation/transcription APIs"
      status: open
      verification: "Translation and transcription routed through local Qwen36/Whisper only"

---

<objective>
Phase 11 rounds out the InfoTriage collection picture by integrating SOCMINT and authoritative Arctic data using the MCP adapter pattern, and closes the Phase 999.1 backlog item (on-demand translation for non-Norwegian/English source items).

1. **Doctrine & Schema Foundation**: Extend the `Item` schema and store layer with discipline tags (OSINT, SOCMINT, MASINT/AIS, etc.) and Admiralty reliability ratings (A-F, 1-6) so every corpus item carries explicit provenance and reliability metadata.
2. **MCP Adapters**: Build `ingest-telegram` (Telethon) and `ingest-barentswatch` (AIS) services following the Phase 4 MCP adapter pattern, including containerization and health endpoints.
3. **Translation on Demand (Phase 999.1 backlog)**: Provide local-LLM translation in the Obsidian vault and SAB reading surfaces for Russian/German/Spanish source items, without sending source data to cloud APIs.
4. **Advanced Media**: Upgrade the existing `ingest-youtube` pipeline with local audio transcription for richer source content.
</objective>

<execution_context>
@$HOME/.claude/gsd-core/workflows/execute-plan.md
@$HOME/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/phases/04-ingest-mcp-pattern/04-PLAN.md
@.planning/phases/999.1-translation-on-demand-per-item-ru-de-es-to-no-en/.gitkeep
@docs/adr/ADR-003-mcp-adapter-pattern.md
@docs/adr/ADR-004-local-only-llm.md
@docs/adr/ADR-006-microservice-architecture-entity-resolution.md
</context>

<downstream_consumer>
Plans consume:
- Frontmatter (wave, depends_on, files_modified, autonomous)
- Tasks in XML format with read_first and acceptance_criteria
- Verification criteria
</downstream_consumer>

## Artifacts this plan produces

| Artifact | Purpose |
|----------|---------|
| `libs/contracts/src/contracts/_item.py` | `Item` schema with `discipline` and `admiralty_reliability` fields |
| `libs/store/src/store/_protocol.py` (+ backends) | Storage support for new provenance metadata |
| `apps/ingest-telegram/` | Telethon-based Telegram MCP adapter |
| `apps/ingest-barentswatch/` | BarentsWatch AIS MCP adapter |
| `apps/ingest-youtube/youtube_ingest.py` | Local transcription upgrade for YouTube |
| `apps/brief/vault_writer.py` / `renderer.py` | On-demand translation reading-surface hooks |
| `docs/adr/ADR-014-socmint-legal-and-tos.md` | SOCMINT legal/ToS posture + ACLED restriction |
| `tests/test_ingest_telegram.py` | Unit tests for Telegram adapter |
| `tests/test_ingest_barentswatch.py` | Unit tests for AIS adapter |
| `tests/test_translation_on_demand.py` | Translation-on-demand tests |

<tasks>

## Wave 1: Doctrine & Schema Foundation

### Task 1: Document SOCMINT legal/ToS posture

**Files:** `docs/adr/ADR-014-socmint-legal-and-tos.md`

**Read first:**
- Existing ADRs in `docs/adr/` for style
- Public Telegram/Telethon Terms of Service
- BarentsWatch data terms
- ACLED licensing terms

**Action:**
1. Draft ADR-014 covering:
   - Legal basis for collecting public Telegram channels and AIS data.
   - ACLED restriction: ingestion only when a valid paid license is present.
   - Operator responsibility for channel selection and export compliance.
   - Prohibition on cloud translation/transcription APIs (ADR-004 alignment).
2. Get review and commit the ADR.

**Acceptance Criteria:**
- ADR-014 exists and is referenced from ROADMAP.md.
- ACLED restriction is explicit and tied to a configuration/env-var check.

**Status:** ✅ COMPLETE

### Task 2: Extend `Item` schema with discipline and reliability metadata

**Files:** `libs/contracts/src/contracts/_item.py`, `libs/store/src/store/_protocol.py`, `libs/store/src/store/_postgres.py`, `libs/store/src/store/_inmemory.py`

**Read first:**
- `libs/contracts/src/contracts/_item.py`
- `libs/store/src/store/_protocol.py` (`put_item`, `get_item`)
- `libs/store/src/store/_postgres.py` (table schema)

**Action:**
1. Add to `Item`:
   - `discipline: str | None` (OSINT, SOCMINT, MASINT/AIS, GEOINT, etc.)
   - `admiralty_reliability: str | None` (A-F + 1-6, e.g. "A1")
2. Update Postgres schema (migration) to store the new columns with sensible defaults.
3. Update InMemory store.
4. Add tests in `tests/test_store_contract.py` or new `tests/test_store_item_metadata.py`.

**Acceptance Criteria:**
- `Item` round-trips with discipline and Admiralty reliability.
- Migration is backward-compatible (existing rows default to `NULL`).

**Status:** ✅ COMPLETE

## Wave 2: Validation, ACLED Gate & Compose Wiring

### Task 3: Add adapter-level validation and ACLED license gate stub

**Files:** `libs/contracts/src/contracts/_item.py`, `libs/contracts/src/contracts/__init__.py`, optional stub `apps/ingest-acled/`

**Read first:**
- ADR-014 ACLED section
- Existing `Item` model and validators

**Action:**
1. ✅ Add Pydantic validation ensuring `discipline` and `admiralty_reliability` match allowed patterns.
2. Add a stub `ingest-acled` adapter or `contracts` helper that refuses to run unless `ACLED_LICENSE_KEY` is present and non-empty.
3. Add tests proving the gate blocks ingestion when the license is missing.

**Acceptance Criteria:**
- ✅ `Item` rejects invalid `discipline` and `admiralty_reliability` values at the schema level.
- ACLED gate raises/ exits non-zero without a valid `ACLED_LICENSE_KEY`.
- No real ACLED data is ingested in tests.

**Status:** ✅ COMPLETE

### Task 4: Wire `ingest-telegram` and `ingest-barentswatch` into docker-compose

**Files:** `docker-compose.yml`, `.env.example`

**Read first:**
- Phase 4 docker-compose service definitions
- Existing ingest services

**Action:**
1. Add `ingest-telegram` and `ingest-barentswatch` services to `docker-compose.yml` with health checks, restart policy, and required environment variables.
2. Update `.env.example` with new environment variables (`TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `BARENTSWATCH_CLIENT_ID`, `ACLED_LICENSE_KEY`, etc.).
3. Verify `docker compose config` parses without errors.

**Acceptance Criteria:**
- `docker compose up -d ingest-telegram ingest-barentswatch` starts both services.
- `/health` endpoints return 200.

**Status:** ✅ COMPLETE

## Wave 3: MCP Adapters — Telegram & BarentsWatch

### Task 5: Scaffold `ingest-telegram` core adapter

**Files:** `apps/ingest-telegram/telegram_ingest.py`, `tests/test_ingest_telegram.py`

**Read first:**
- `apps/ingest-imap/imap_ingest.py` and `apps/ingest-youtube/youtube_ingest.py` for MCP adapter pattern
- `libs/ingest_common/` for shared ingestion helpers
- Telethon documentation for channel/listen patterns

**Action:**
1. Create `telegram_ingest.py` with functions to:
   - Read Telegram channels/chats by list of IDs/usernames.
   - Fetch messages within a configurable time window.
   - Emit `Item` records with `source_type="telegram"`, `discipline="SOCMINT"`, and a default `admiralty_reliability`.
2. Add `--since`, `--channel`, and `--dry-run` CLI arguments.
3. Add unit tests mocking Telethon client calls and verifying emitted `Item` shape.

**Acceptance Criteria:**
- Unit tests mock Telethon and verify emitted `Item` shape.
- Adapter rejects private-channel IDs or missing credentials.

**Status:** ✅ COMPLETE

### Task 6: Containerize `ingest-telegram`

**Files:** `apps/ingest-telegram/main.py`, `apps/ingest-telegram/Dockerfile`, `apps/ingest-telegram/requirements.txt`

**Read first:**
- Phase 4 containerization pattern
- `apps/ingest-imap/Dockerfile` and `main.py`

**Action:**
1. Add `main.py` with a FastAPI/health endpoint and periodic runner.
2. Create `Dockerfile` and `requirements.txt`.
3. Wire the container into `docker-compose.yml` (covered in Task 4).

**Acceptance Criteria:**
- `docker compose up -d ingest-telegram` starts and reports healthy.
- Container runs the adapter on schedule or on demand.

**Status:** ✅ COMPLETE

### Task 7: Scaffold `ingest-barentswatch`

**Files:** `apps/ingest-barentswatch/barentswatch_ingest.py`, `apps/ingest-barentswatch/main.py`, `apps/ingest-barentswatch/Dockerfile`, `apps/ingest-barentswatch/requirements.txt`

**Read first:**
- BarentsWatch/AIS public API documentation
- Existing ingest adapters for polling patterns

**Action:**
1. Create `barentswatch_ingest.py` to poll AIS data for a configurable area/ship list.
2. Emit `Item` records with `source_type="ais"`, `discipline="MASINT/AIS"`, and `admiralty_reliability`.
3. Containerize and add health endpoint.
4. Add tests in `tests/test_ingest_barentswatch.py`.

**Acceptance Criteria:**
- AIS adapter emits structured items with position/metadata fields.
- Mock API tests pass without real credentials.

**Status:** ✅ COMPLETE

## Wave 4: Translation on Demand (Phase 999.1 backlog)

### Task 8: Add local-LLM translation helper

**Files:** `libs/contracts/src/contracts/_translation.py`, `apps/brief/vault_writer.py`, `apps/brief/renderer.py`

**Read first:**
- `apps/triage/triage_score.py` (local LLM call pattern)
- `apps/brief/vault_writer.py` (Obsidian note writing)
- `libs/contracts/src/contracts/_verify.py` (shared utility location)

**Action:**
1. Create `libs/contracts/src/contracts/_translation.py` with:
   - `translate_to(text: str, target_lang: str, source_lang: str | None = None) -> str`
   - Local LLM prompt asking the model to translate while preserving meaning and named entities.
2. Cache translations keyed by `(text_hash, target_lang)` in Postgres to avoid repeated LLM calls.
3. Export `translate_to` from `contracts.__init__`.

**Acceptance Criteria:**
- `translate_to` works without network calls to cloud APIs.
- Caching is tested.

**Status:** ✅ COMPLETE

### Task 9: Surface translation in the Obsidian vault / SAB brief

**Files:** `apps/brief/vault_writer.py`, `apps/brief/renderer.py`, `apps/brief/html_renderer.py`

**Read first:**
- `apps/brief/vault_writer.py` and `renderer.py` current output format
- `libs/contracts/src/contracts/_codec.py` (frontmatter)

**Action:**
1. When an item's `lang` is not `en` or `no`, optionally append or display a translated title/summary.
2. Add `translation_enabled` / `translation_target_lang` configuration.
3. Add tests in `tests/test_translation_on_demand.py`.

**Acceptance Criteria:**
- Russian source item shows an English/Norwegian translation in the vault/brief.
- Translations are cached and not re-requested for the same text.

## Wave 5: Advanced Media — YouTube Transcription

### Task 10: Add local audio transcription to `ingest-youtube`

**Files:** `apps/ingest-youtube/youtube_ingest.py`, `apps/ingest-youtube/Dockerfile`, `apps/ingest-youtube/requirements.txt`

**Read first:**
- Current `youtube_ingest.py` pipeline
- Local Whisper / faster-whisper options

**Action:**
1. Optionally download audio and run a local transcription model (Whisper-compatible) when `--transcribe` is set.
2. Store transcript as a blob via `store.put_blob` and link via `body_ref`.
3. Respect ADR-004: no cloud transcription APIs.
4. Make the feature opt-in via env var or flag.

**Acceptance Criteria:**
- `--transcribe` produces a transcript for a downloaded video.
- Transcript is retrievable via the store blob path.

## Wave 6: Closeout

### Task 11: Update ROADMAP/STATE and close backlog item

**Files:** `.planning/ROADMAP.md`, `.planning/STATE.md`, `.planning/phases/999.1-translation-on-demand-per-item-ru-de-es-to-no-en/.gitkeep`

**Action:**
1. Mark Phase 11 complete in `ROADMAP.md` and `STATE.md`.
2. Delete or archive the 999.1 backlog placeholder.
3. Create `.planning/phases/11-socmint/11-01-SUMMARY.md`.

**Acceptance Criteria:**
- Planning docs reflect Phase 11 completion.
- Phase 999.1 backlog item is closed/removed.
- Summary artifact exists.

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Telegram API | Credentials scoped to read-only public channels; no message sending. |
| BarentsWatch API | Read-only AIS polling; no write access. |
| Local LLM | Translation and transcription must not leak source text to cloud APIs. |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-11-01 | Info Disclosure | Telegram channel selection | Medium | Mitigate | Document operator responsibility in ADR-014; restrict to public channels. |
| T-11-02 | Legal/Compliance | ACLED ingestion | High | Mitigate | Paid-license gate; block ingestion and LLM feeding if unlicensed. |
| T-11-03 | Information Quality | Unverified SOCMINT | Medium | Mitigate | Admiralty reliability ratings and discipline tags surface source trust. |
| T-11-04 | Tampering | Transcript storage | Low | Mitigate | Store transcripts as write-once blobs with hash verification. |
</threat_model>

<verification>
- `pytest tests/test_ingest_telegram.py -x` green
- `pytest tests/test_ingest_barentswatch.py -x` green
- `pytest tests/test_translation_on_demand.py -x` green
- `pytest tests/test_store_contract.py -x` green (metadata round-trip)
- `black --check` passes on all new/changed files
- `mypy` clean on `apps/ingest-telegram/`, `apps/ingest-barentswatch/`, `apps/ingest-youtube/`, `libs/contracts/src/contracts/_translation.py`
- End-to-end smoke: run `docker compose up -d ingest-telegram ingest-barentswatch` and verify `/health` returns 200
</verification>

<success_criteria>
From `.planning/ROADMAP.md` §Phase 11:

1. `ingest-telegram`, `ingest-barentswatch`, and upgraded `ingest-youtube` are running as containerized MCP adapters.
2. New items carry discipline tags and Admiralty reliability ratings.
3. On-demand translation is available in the vault/brief reading surface for non-no/en items (Phase 999.1 closed).
4. ACLED data is gated by a paid-license check and never reaches the local LLM without one.
5. SOCMINT legal/ToS posture is documented in ADR-014.
</success_criteria>

<output>
Create `.planning/phases/11-socmint/11-01-SUMMARY.md` when done
</output>
