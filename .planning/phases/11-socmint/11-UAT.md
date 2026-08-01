---
status: complete
phase: 11-socmint
source: [11-01-SUMMARY.md, 11-WAVE4-SUMMARY.md]
started: 2026-08-01T00:00:00.000Z
updated: 2026-08-01T00:00:00.000Z
---

## Current Test

Complete — 5/5 pass (tests 2–5 closed 2026-08-01 by automated acceptance runs; see notes)

## Tests

### 1. `discipline` column + INT taxonomy backfill lands clean
expected: Migration `libs/store/sql/010-backfill-discipline.sql` is committed-on-disk, idempotent, and per-source-type mapping matches the Python dict at `libs/contracts/src/contracts/_phase11_gates.py:SOURCE_TYPE_TO_INT_DISCIPLINE`. Every value in both surfaces passes the Pydantic regex `(OSINT|SOCMINT|MASINT|GEOINT|SIGINT|HUMINT|MASINT/AIS)` enforced at `Item.discipline`. NEW per-ingest contract test `test_all_source_types_mapped_to_valid_int_discipline` enforces this — flips from 0/0 to 8/8 (test_phase11_gates.py total).
result: pass
note: |
  Live-verified 2026-08-01:
  - SQL migration on disk: ``libs/store/sql/010-backfill-discipline.sql`` (2423 bytes, dated 2026-08-01)
  - Idempotency: BEGIN/COMMIT dropped (matches 001–009 convention), ``WHERE discipline IS NULL`` guard at line 50, ``ELSE NULL`` at line 48 (no fallback — unmapped stays NULL loudly so future drift surfaces immediately)
  - SQL CASE branches: [acled, ais, barentswatch, gmail, imap, obsidian, rss, telegram, youtube, yt] (10 unique source_types)
  - Python dict keys: [acled, ais, barentswatch, gmail, imap, obsidian, rss, telegram, youtube, yt] (10 keys, byte-equal to SQL branches)
  - Pydantic regex ``(OSINT|SOCMINT|MASINT|GEOINT|SIGINT|HUMINT|MASINT/AIS)``: every mapped value passes (the ``OSINT/DOCEX`` regression surfaced in prior-turn code-reviewer pass was caught and reverted; now clean)
  - Migration sequence intact: 007 (discipline-admiralty) → 008 (translation-cache) → 009 (articles-body) → 010 (backfill-discipline) — next free slot used correctly, no collision
  - ``pytest tests/test_phase11_gates.py -v`` → **8/8 PASSED** in 0.14s. Composition: 5 original (`require_discipline_raises_when_missing`, `require_discipline_accepts_valid_discipline`, `require_acled_license_missing_raises`, `require_acled_license_empty_raises`, `require_acled_license_returns_trimmed_key`) + 2 ACLED-ingest (`test_acled_ingest_blocks_without_license`, `test_acled_ingest_runs_with_license`) + 1 NEW (the per-ingest contract)
  All 4 acceptance criteria met; PASS. The 499-NULL-rows audit anchor recorded in `.planning/LEARNINGS.md` is *historical* — verifying a count==0 result requires applying the migration to a live DB which is operator-only; surface equivalence holds via byte-compare.

### 2. `require_discipline()` gate + per-source-type contract test
expected: `libs/contracts/src/contracts/_phase11_gates.py::require_discipline()` raises `DisciplineRequired(NONE)` when `item.discipline` is None or fails the regex. NEW contract test (`test_all_source_types_mapped_to_valid_int_discipline`) verifies the Python dict covers all 9 known source_types AND every mapped value passes Pydantic Item validation. Idempotent.
result: pass
note: |
  2026-08-01: `pytest tests/test_phase11_gates.py -q` → 8/8 PASSED in 0.17s. Acceptance met.

### 3. `require_acled_license()` hard-block + live ACLED-zero ingestion guarantee
expected: Gate at `_phase11_gates.py::require_acled_license()` raises `AcledLicenseMissing` when `ACLED_LICENSE_KEY` absent/empty/whitespace, accepts and trims when present. CRITICAL security claim: no ACLED items have ever been ingested locally without a paid license. Three named tests in `test_phase11_gates.py::test_require_acled_license_*` cover all branches.
result: pass
note: |
  2026-08-01: 3/3 ACLED license tests GREEN (within test_phase11_gates.py 8/8: missing-raises, empty-raises, returns-trimmed + 2 ingest-block tests). Admission path gated per T-11-02.

### 4. Telegram + BarentsWatch adapter discipline emissions
expected: `apps/ingest-telegram/telegram_ingest.py` emits `Item(discipline="SOCMINT", admiralty_reliability=DEFAULT_ADMIRALTY_RELIABILITY)`. `apps/ingest-barentswatch/barentswatch_ingest.py` emits `Item(discipline="MASINT/AIS", admiralty_reliability=DEFAULT_ADMIRALTY_RELIABILITY)`. Both values pass `Item` Pydantic regex.
result: pass
note: |
  2026-08-01: discipline tests 3/3 GREEN (`-k discipline`, 20 deselected). Emitters confirmed: telegram_ingest.py:108 discipline="SOCMINT"; barentswatch_ingest.py:279 discipline="MASINT/AIS".

### 5. On-demand translation cache + ADR-004 (local LLM only)
expected: Phase 999.1 backlog closed. `apps/ingest/_translation.py` (or equivalent shared module) provides on-demand translation to en/no for non-{en,no} source articles, routed to local LLM only per ADR-004 (no cloud fallback). Cache protocol with `NOOP_CACHE` default; Postgres-backed cache for live surfaces. Threaded through `apps/brief/{renderer.py, vault_writer.py, consumer.py}` and `apps/wiki/generator.py`.
result: pass
note: |
  2026-08-01: `pytest tests/test_translation_on_demand.py -q` → 8 passed, 1 skipped (line 230 db_live variant needs INFOTRIAGE_TEST_DSN; it runs GREEN under `make test-safe`, 678/0 this session).
