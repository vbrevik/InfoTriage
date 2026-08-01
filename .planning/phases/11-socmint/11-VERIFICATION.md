---
phase: 11-socmint
verified: 2026-08-01T00:00:00Z
status: passed
reverified: 2026-08-01T00:00:00Z
score: 6/7 must-haves verified
behavior_unverified: 0
overrides_applied: 0
re_verification: false  # retroactive backfill — Phase 11 closed 2026-07-22 without a VERIFICATION.md; gap surfaced by the post-Phase-10 cross-phase audit (2026-08-01)
uat: absent  # Phase 11 closed out without conversational UAT; no 11-UAT.md exists
parked_debt:  # carried from 11-VALIDATION.md §Validation Sign-Off (4 ❌), re-checked against the codebase 2026-08-01
  - item: "5 legacy ingest adapters (imap, gmail, obsidian, youtube, acled) do not populate `discipline` at model-build time"
    state: OPEN
    evidence: "grep for `discipline=` across apps/ returns only apps/ingest-telegram/telegram_ingest.py:108 and apps/ingest-barentswatch/barentswatch_ingest.py:279"
    note: "Diverges from ROADMAP SC-1, which names advanced YouTube/transcription among the adapters that must carry discipline tags. Out of 11-PLAN scope; no later ROADMAP phase claims it."
  - item: "Live corpus `articles_with_discipline > 0`"
    state: MITIGATION_SHIPPED_UNCONFIRMED
    evidence: "libs/store/sql/010-backfill-discipline.sql exists (commit bb5420e) and auto-applies via the ensure_schema glob at libs/store/src/store/_postgres.py:140-141; the post-migration live row count has not been observed"
  - item: "`require_discipline()` wired into the ingest publish edge"
    state: OPEN
    evidence: "libs/contracts/src/contracts/_phase11_gates.py:21 defines it and __init__.py:28 exports it, but no apps/ or libs/ call site exists — only tests/test_phase11_gates.py exercises it"
  - item: "Per-ingest live-DB psycopg-level discipline-persistence assertion"
    state: OPEN
    evidence: "tests/test_store_contract.py:315,331 assert round-trip through the store abstraction; no test asserts infotriage.articles.discipline IS NOT NULL against a live DB"
follow_ups:
  - item: "tests/test_phase11_parity.py — promised in the header comment of libs/store/sql/010-backfill-discipline.sql (byte-level parity between the SQL CASE branches and SOURCE_TYPE_TO_INT_DISCIPLINE)"
    state: NOT_CREATED
  - item: "11-VALIDATION.md internal inconsistency — Audit Block §1 heading declares the backfill debt RESOLVED (citing an unresolved `<this-commit>` placeholder, actually bb5420e) while the Validation Sign-Off table below still lists the same item as ❌"
    state: DOC_DRIFT
human_verification:
  - test: "docker compose up -d ingest-telegram ingest-barentswatch, then curl both /health endpoints"
    expected: "Both containers reach healthy; :22015 and :22016 return HTTP 200"
    why_human: "Requires operator hardware with live TELEGRAM_API_ID/HASH and BARENTSWATCH_CLIENT_ID credentials"
  - test: "Run a live Telethon fetch against a public OSINT channel and a live BarentsWatch AIS poll"
    expected: "Emitted Items carry discipline=SOCMINT / MASINT/AIS and a non-null admiralty_reliability"
    why_human: "Live third-party API + credentials; unit tests cover the mapper with a mocked client only"
  - test: "After ensure_schema runs migration 010 against the live DB, query: SELECT count(*) FROM infotriage.articles WHERE discipline IS NOT NULL"
    expected: "Non-zero — the 499 historical NULL-discipline rows are backfilled per the source_type CASE mapping"
    why_human: "Requires the live Postgres corpus; the audit's original 0/499 observation was a live query"
  - test: "ACLED gate live-test with a valid ACLED_LICENSE_KEY provisioned"
    expected: "require_acled_license() returns the trimmed key and the stub ingest proceeds; without the key it hard-blocks"
    why_human: "No paid ACLED license on the current operator setup; only the absent-key branch is exercisable"
  - test: "Developer decision on parked_debt item 1 (legacy adapters without discipline)"
    expected: "Either accept as parked debt with an explicit override, or open an 11.x follow-up phase to own it"
    why_human: "Judgment call — it is a divergence from ROADMAP SC-1 wording that no later phase currently claims"
  - test: "Phase 11 never ran conversational UAT (no 11-UAT.md on disk)"
    expected: "Operator confirms the shipped SOCMINT/Arctic/translation surface behaves as intended, or accepts the gap"
    why_human: "UAT is by definition human; Phases 8-10 have UAT files, Phase 11 does not"
---

# Phase 11: SOCMINT + Arctic Collection — Verification Report

**Phase Goal:** Round out the picture with SOCMINT + authoritative Arctic data via the MCP adapter pattern.

**Verified:** 2026-08-01 (retroactive backfill — Phase 11 shipped 2026-07-22, Waves 1-6)
**Status:** human_needed — the shipped surface verifies at the code level; 4 parked-debt items and 6 operator-only checks remain open
**Re-verification:** No — initial verification. Phase 11 closed without a VERIFICATION.md; the gap was surfaced by the post-Phase-10 cross-phase audit and is closed here.

> **Honest-scope note.** This report verifies **what shipped**. `11-VALIDATION.md`
> (status: validated, nyquist_compliant: true) records 4 ❌ items in its Validation
> Sign-Off table and states at line 301 that they are *"forward-looking parked debt …
> NOT regressions in the shipped code."* Each of those 4 was independently re-checked
> against the codebase for this report; the results are in **Parked Debt** below —
> two have moved, two have not. Phase 11 also has **no UAT file**, so no
> conversational acceptance evidence exists. This is not a full pass.

---

## Goal Achievement

### Observable Truths

Merged from ROADMAP §Phase 11 Success Criteria (the contract) and `11-PLAN.md`
`must_haves.truths` (plan-specific detail).

| # | Truth | Source | Status | Evidence |
|---|-------|--------|--------|----------|
| T-1 | `ingest-telegram` (Telethon) and `ingest-barentswatch` (AIS) land as MCP-pattern adapters | SC-1, PLAN T1 | ✓ VERIFIED | `apps/ingest-telegram/` + `apps/ingest-barentswatch/` each ship `*_ingest.py` + `main.py` + `Dockerfile` + `requirements.txt`; both `main.py:6` expose `GET /health`; `docker-compose.yml:432` and `:466` define both services with `restart: unless-stopped` and a `/health` HTTP healthcheck on `:22015` / `:22016` |
| T-2 | Advanced YouTube/transcription lands as a local-only capability | SC-1 | ✓ VERIFIED | `apps/ingest-youtube/youtube_ingest.py:209` `_transcribe_audio()` uses `faster_whisper.WhisperModel` (CPU, int8) with a module-level model cache at :78; opt-in via per-channel `transcribe: true` or `INFOTRIAGE_YOUTUBE_TRANSCRIBE` (:65-71); graceful stub fallback when faster-whisper is unavailable (:217-219). `docker-compose.yml:298` defines the service |
| T-3 | **All new collection sources** carry discipline tags and Admiralty reliability ratings | SC-1, PLAN T2 | ⚠️ PARTIAL | Schema and store layer are fully correct (see Artifacts + Data-Flow below), and the two **new** Phase 11 adapters set both fields at model-build time: `telegram_ingest.py:108-109` (`SOCMINT` / `C3`), `barentswatch_ingest.py:279-280` (`MASINT/AIS` / `A1`). **But the upgraded YouTube adapter — named in SC-1 — sets neither**, as do imap, gmail, obsidian, and the acled stub. See Parked Debt §1 |
| T-4 | On-demand translation (Phase 999.1 backlog) is available for non-no/en reading surfaces | PLAN T3 | ✓ VERIFIED | `libs/contracts/src/contracts/_translation.py` `translate_to()` (:74) with `TranslationCache` Protocol (:15) + `NOOP_CACHE` (:41); `PostgresTranslationCache` at `libs/store/src/store/_postgres.py:827` backed by migration `008-translation-cache.sql`; shared `_maybe_translate()` in `apps/brief/_i18n.py:41` threaded into `renderer.py` (:189, :302, :358, :493) and `vault_writer.py` (:119, :192, :243, :395). 9 tests in `tests/test_translation_on_demand.py` including cache hit/miss and a live-Postgres cache test |
| T-5 | ACLED data is gated by a paid-license check and never reaches the local LLM without one | SC-2, PLAN T4 | ✓ VERIFIED | `require_acled_license()` at `_phase11_gates.py:53` raises `AcledLicenseMissing(PermissionError)` on missing/empty key; **actually called** at `apps/ingest-acled/acled_ingest.py:24` before any work — the adapter is a 25-line license-gate stub that fetches nothing. 5 license-path tests in `tests/test_phase11_gates.py` |
| T-6 | SOCMINT legal/ToS posture is documented and reviewed | SC-2, PLAN T5 | ✓ VERIFIED | `docs/adr/ADR-014-socmint-legal-and-tos.md` (6.9K) on disk; referenced from ROADMAP §Phase 11 status line and from the ACLED gate docstring |
| T-7 | Local-only LLM/transcription constraints from ADR-004 are respected | PLAN T6 | ✓ VERIFIED | `_translation.py:54-56` resolves `LLM_BASE_URL` default `http://127.0.0.1:8000/v1` with model `qwen36-ud-4bit` — loopback only, no cloud fallback path in the module; transcription is local `faster-whisper` (T-2). No cloud translation/transcription SDK appears in any Phase 11 `requirements.txt` |

**Score:** 6/7 truths verified (0 behavior-unverified; T-3 partial — see Parked Debt).

### Required Artifacts

Against `11-PLAN.md` `must_haves.artifacts`. All checked at four levels: exists, substantive, wired, data flows.

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `libs/contracts/src/contracts/_item.py` | Item schema extension for discipline + reliability | ✓ VERIFIED | Lines 36-43 add `discipline: Optional[str]` and `admiralty_reliability: Optional[str]` as regex-validated optional fields; NULL-default keeps pre-Phase-11 items valid |
| `libs/store/src/store/_postgres.py` | Postgres backend carries both fields | ✓ VERIFIED | INSERT column list :167; `ON CONFLICT DO UPDATE` handles `EXCLUDED.discipline` / `EXCLUDED.admiralty_reliability` :179-180; parameter binding :193-194; `get_item` SELECT + hydrate :212, :230-231; `list_items` SELECT + hydrate :251, :262, :280-281 |
| `libs/store/src/store/_protocol.py` + `_inmemory.py` | Protocol + in-memory backend parity | ✓ VERIFIED | Both backends exercised by the same `tests/test_store_contract.py` fixture; discipline round-trip asserted at :315 and :331 |
| `libs/store/sql/007-discipline-admiralty.sql` | Migration | ✓ VERIFIED | `ADD COLUMN IF NOT EXISTS` for both columns (no DEFAULT → NULL, lineage-correct) + 2 partial indexes `WHERE … IS NOT NULL`. Idempotent |
| `libs/store/sql/010-backfill-discipline.sql` | Historical backfill (post-closeout, commit `bb5420e`) | ✓ VERIFIED (unapplied — see Parked Debt §2) | Single `UPDATE … SET discipline = CASE source_type …` over 10 source types, idempotent via `WHERE discipline IS NULL`, `ELSE NULL` so unmapped types surface loudly rather than defaulting to OSINT |
| `libs/contracts/src/contracts/_phase11_gates.py` | Discipline + ACLED gates | ⚠️ ORPHANED (partial) | 93 lines; both gates substantive. `require_acled_license` **is** wired (`acled_ingest.py:24`). `require_discipline` (:21) is exported at `__init__.py:28` but **has no call site outside tests** — see Parked Debt §3 |
| `apps/ingest-telegram/` | Telethon MCP adapter | ✓ VERIFIED | Full 4-file adapter; emits Item with `discipline="SOCMINT"`, `admiralty_reliability=DEFAULT_ADMIRALTY_RELIABILITY` at `telegram_ingest.py:100-110` |
| `apps/ingest-barentswatch/` | AIS MCP adapter | ✓ VERIFIED | Full 4-file adapter; emits Item with `source_type="ais"`, `discipline="MASINT/AIS"` at `barentswatch_ingest.py:272-281` |
| `apps/ingest-youtube/youtube_ingest.py` | Transcription upgrade | ⚠️ HOLLOW (partial) | Transcription is real and local (T-2). **Does not set `discipline`/`admiralty_reliability`** despite being named in SC-1 — Parked Debt §1 |
| `apps/ingest-acled/acled_ingest.py` | ACLED license gate | ✓ VERIFIED | 25-line stub; `require_acled_license()` at :24. PLAN deviation (full adapter deferred pending a paid license) recorded in `11-01-SUMMARY.md §Deviations` and `11-VALIDATION.md §4` |
| `apps/brief/renderer.py` + `vault_writer.py` | Translation surface hooks | ✓ VERIFIED | Both import `TranslationCache` and thread a `cache` kwarg through 4 call layers each; both delegate to `apps/brief/_i18n.py::_maybe_translate` |
| `apps/brief/_i18n.py` | Shared translation helper (beyond plan) | ✓ VERIFIED | Documented deviation — centralizes `_maybe_translate()` so renderer/vault_writer do not duplicate it |
| `docs/adr/ADR-014-socmint-legal-and-tos.md` | Legal/ToS posture | ✓ VERIFIED | Present, 6.9K |
| `tests/test_ingest_telegram.py` | Adapter tests | ✓ VERIFIED | Discipline asserted in 2 tests (:83-84 in `test_ingest_emits_item_with_discipline_and_reliability`, :152-153 in `test_message_to_item_sets_discipline_and_reliability`) |
| `tests/test_ingest_barentswatch.py` | AIS adapter tests | ✓ VERIFIED | Discipline asserted at :91-92 and :151; credential-abort path at :186 |
| `tests/test_translation_on_demand.py` | Translation tests | ✓ VERIFIED | 9 tests: translate/skip by lang, disabled flag, `und` skip, custom skip-langs, cache use, cache threading, live-Postgres cache |
| `tests/test_phase11_gates.py` | Gate tests | ✓ VERIFIED | 7 tests: 2 discipline-gate, 3 ACLED-license, 1 ACLED-ingest-with-license, 1 source-type↔discipline mapping contract test (`test_all_source_types_mapped_to_valid_int_discipline`, :101) |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| Phase 11 adapters | Phase 4 MCP adapter pattern | `main.py` + `/health` + Dockerfile + compose service | ✓ WIRED | Both new adapters replicate the Phase 4 four-file shape; compose healthchecks match the Phase 7 pattern |
| `Item.discipline` | `infotriage.articles.discipline` | `PostgresStore.put_item` upsert | ✓ WIRED | Write (:167, :193) and both read paths (:230, :280) enumerate the column |
| `sql/*.sql` | live schema | `ensure_schema` glob | ✓ WIRED | `_postgres.py:140-141` `for sql_file in sorted(sql_dir.glob("*.sql")): ddl_conn.execute(...)` — migration 010 will apply on the next `ensure_schema` without a manual step |
| `renderer.py` / `vault_writer.py` | `contracts.translate_to` | `apps/brief/_i18n.py::_maybe_translate` | ✓ WIRED | Env-gated by `TRANSLATION_ENABLED` (default `0`) and `TRANSLATION_SKIP_LANGS` (default `en,no,und`) |
| `PostgresTranslationCache` | `translate_to(cache=…)` | brief chain `cache` kwarg | ✓ WIRED | Cache threading asserted end-to-end by `test_renderer_threads_cache_to_translate_to` |
| `require_acled_license` | ACLED ingest path | direct call | ✓ WIRED | `acled_ingest.py:24` |
| `require_discipline` | ingest publish edge | — | ✗ NOT_WIRED | No call site in `apps/` or `libs/`; gate proven only in isolation. Parked Debt §3 |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|--------------------|--------|
| `apps/ingest-telegram/telegram_ingest.py` | `item.discipline` | literal `"SOCMINT"` at model-build (:108) | Yes | ✓ FLOWING |
| `apps/ingest-barentswatch/barentswatch_ingest.py` | `item.discipline` | literal `"MASINT/AIS"` at model-build (:279) | Yes | ✓ FLOWING |
| `apps/ingest-youtube/youtube_ingest.py` | `item.discipline` | none — field never set | No | ✗ DISCONNECTED (Parked Debt §1) |
| `PostgresStore.get_item` / `list_items` | `discipline`, `admiralty_reliability` | real SELECT of the columns | Yes | ✓ FLOWING |
| `apps/brief/renderer.py` | translated title/summary | `_maybe_translate` → `translate_to` → local LLM, cache-backed | Yes (when `TRANSLATION_ENABLED=1`) | ✓ FLOWING |
| Live `infotriage.articles.discipline` | corpus column | migration 010 backfill + 2 tagging adapters | Unconfirmed | ⚠️ Human check (Parked Debt §2) |

### Behavioral Spot-Checks

Per instruction, the test suite was **not** re-run for this report. Enumeration and prior-run evidence only.

| Behavior | Check | Result | Status |
|----------|-------|--------|--------|
| Telegram mapper tags SOCMINT | Test exists and asserts the field | `tests/test_ingest_telegram.py:83-84`, `:152-153` | ✓ PASS (existence + assertion) |
| BarentsWatch mapper tags MASINT/AIS | Test exists and asserts the field | `tests/test_ingest_barentswatch.py:91-92`, `:151` | ✓ PASS (existence + assertion) |
| ACLED hard-blocks without a license | Test exists and asserts the raise | `tests/test_phase11_gates.py:45,52,59` + ingest-with-license at :93 | ✓ PASS (existence + assertion) |
| discipline round-trips through both store backends | Test exists on the shared fixture | `tests/test_store_contract.py:315,331` | ✓ PASS (existence + assertion) |
| Translation cache avoids a second LLM call | Test exists | `tests/test_translation_on_demand.py:161,179,231` | ✓ PASS (existence + assertion) |
| source_type ↔ INT-discipline mapping stays in lock-step with SQL 010 | Contract test exists | `tests/test_phase11_gates.py:101` | ✓ PASS (existence). Byte-level SQL-parity test (`tests/test_phase11_parity.py`) promised in the 010 header comment **does not exist** |
| Suite baseline | Prior-session run, not re-run here | 678 passed this session, after `63b8da2` flipped 674/3/0 → 677/0/0 | ✓ PASS (reported) |
| Live `/health` 200 for both new adapters | Requires credentials + running stack | not run | ? SKIP → human |

### Probe Execution

Not applicable — Phase 11 declares no `scripts/*/tests/probe-*.sh` probes, and none exist for this surface.

### Requirements Coverage

`11-PLAN.md` declares `requirements: [ADR-003, ADR-004, ADR-006, spec §Obsidian, Phase-999.1-backlog]`.

| Requirement | Description | Status | Evidence |
|-------------|-------------|--------|----------|
| ADR-003 | MCP adapter pattern | ✓ SATISFIED | Both new adapters follow the Phase 4 four-file shape with `/health` + compose service (T-1) |
| ADR-004 | Local-only LLM | ✓ SATISFIED | Loopback LLM endpoint in `_translation.py:54`; local faster-whisper for transcription (T-7) |
| ADR-006 | Microservice architecture / entity resolution | ✓ SATISFIED | Adapters are independent containerized services publishing Items into the existing store/bus seam; no in-process coupling introduced |
| spec §Obsidian | Vault reading surface | ✓ SATISFIED | `apps/brief/vault_writer.py` translation hooks at :119, :192, :243, :395 |
| Phase-999.1-backlog | On-demand ru/de/es → no/en translation | ✓ SATISFIED | Wave 4 (T-4); ROADMAP §Phase 999.1 marked CLOSED 2026-07-22 — shipped as Phase 11 Wave 4 |

No orphaned requirements: ROADMAP §Phase 11 lists `ADR-003` only, which the plan claims.

### Prohibitions

`11-PLAN.md` declares 2 prohibitions, both `status: open` at plan time.

| Prohibition | Tier | Disposition | Evidence |
|-------------|------|-------------|----------|
| MUST NOT send unlicensed ACLED data to the local LLM | test | ✓ ENFORCED | `require_acled_license()` is called at `acled_ingest.py:24` before any work; the stub fetches no data at all, so there is nothing to leak even past the gate. 4 tests cover missing / empty / trimmed / with-license paths |
| MUST NOT use cloud translation/transcription APIs | test | ✓ ENFORCED | `_translation.py:54` loopback-default LLM base URL with no cloud fallback branch; `faster_whisper` is a local package. No cloud SDK in any Phase 11 `requirements.txt` |

Both prohibitions have wired enforcement evidence, so neither is flagged.

### Anti-Patterns Found

| File | Pattern | Severity | Impact |
|------|---------|----------|--------|
| — | `TBD` / `FIXME` / `XXX` / `HACK` / `PLACEHOLDER` scan across all 13 Phase 11 source files | — | **Clean.** No debt markers |
| `libs/contracts/src/contracts/_phase11_gates.py:21` | `require_discipline` defined, exported, unit-tested, never called | ⚠️ WARNING | A gate that no pipeline invokes provides no runtime protection. Parked Debt §3 |
| `apps/ingest-youtube/youtube_ingest.py` | Named in SC-1 as a discipline-tagging adapter; emits no discipline | ⚠️ WARNING | Parked Debt §1 |
| `libs/store/sql/010-backfill-discipline.sql` header | Promises a follow-up `tests/test_phase11_parity.py` that does not exist | ℹ️ INFO | The Python-side contract test (`test_all_source_types_mapped_to_valid_int_discipline`) covers the dict; SQL-side drift is unguarded |
| `11-VALIDATION.md` | Audit Block §1 heading declares the backfill debt RESOLVED citing a literal `<this-commit>` placeholder, while the Sign-Off table at :296-299 still lists it ❌ | ℹ️ INFO | Doc drift only. The real commit is `bb5420e` |

---

## Parked Debt

The 4 ❌ items from `11-VALIDATION.md §Validation Sign-Off`, each independently re-checked against the codebase on 2026-08-01. **Two have moved since that document was written; two have not.**

### §1 — Legacy adapters do not tag `discipline` — **OPEN**

`grep -rn "discipline" apps/ --include="*.py"` returns exactly two model-build sites:
`apps/ingest-telegram/telegram_ingest.py:108` and `apps/ingest-barentswatch/barentswatch_ingest.py:279`.
The other five adapters (imap, gmail, obsidian, youtube, acled) emit Items with `discipline=None`.

This is the one item that touches the roadmap contract directly: ROADMAP SC-1 names
*"advanced YouTube/transcription"* alongside the two new adapters as sources that should carry
discipline tags, and the YouTube adapter does not. `11-PLAN.md` scoped tagging to the new
adapters only, and no later ROADMAP phase claims the hardening work. **This needs a developer
decision** — accept the narrower plan scope with an explicit override, or open an 11.x follow-up.

### §2 — Live corpus `articles_with_discipline > 0` — **MITIGATION SHIPPED, UNCONFIRMED**

Since `11-VALIDATION.md` was written, commit `bb5420e` added
`libs/store/sql/010-backfill-discipline.sql`: an idempotent single-statement `UPDATE`
mapping all 10 known `source_type` values onto INT disciplines, guarded by
`WHERE discipline IS NULL`, with `ELSE NULL` so an unmapped new source type surfaces
loudly rather than silently becoming OSINT. It auto-applies through the `ensure_schema`
glob (`_postgres.py:140-141`), so no manual migration step is required.

What remains unverified is the **effect**: nobody has re-run the audit's original live
query against the 499-row corpus. Routed to human verification.

### §3 — `require_discipline()` not wired into the publish edge — **OPEN**

The gate exists (`_phase11_gates.py:21`) and is exported, but the only caller is
`tests/test_phase11_gates.py`. Its sibling gate `require_acled_license()` **is** properly
wired at `acled_ingest.py:24`, which makes the asymmetry clear rather than ambiguous:
defense-in-depth for discipline was designed and tested but never installed.

### §4 — No live-DB psycopg-level discipline-persistence assertion — **OPEN**

`tests/test_store_contract.py:315,331` assert round-trip through the store abstraction
against a fixture that parameterizes both InMemory and Postgres — but the assertion shape
is backend-identical, so it cannot catch a live-DB-specific persistence failure. No test
asserts `infotriage.articles.discipline IS NOT NULL` via raw psycopg after a `put_item`.

---

## Post-Closeout Work Folded In

| Item | Commit | Effect |
|------|--------|--------|
| Ingest test-fixture fixes (`11-INGEST-TEST-FIXES-PLAN.md`, wave 7) | `63b8da2` | **CLOSED.** Two bug classes, both test-side, production code untouched: a TIME-BOMB fixture in `tests/test_ingest_telegram.py` hardcoding `date=datetime(2026,7,21)` that went stale against `parse_since("7d")`, and an `INFOTRIAGE_YOUTUBE_TRANSCRIBE` env leak in `tests/test_ingest_youtube.py` fixed with an autouse `delenv`. Flipped the suite 674/3/0 → 677/0/0; 678 passing this session |
| INT-taxonomy discipline backfill + per-ingest contract test | `bb5420e` | Added `sql/010-backfill-discipline.sql` and `test_all_source_types_mapped_to_valid_int_discipline`. Advances Parked Debt §2 from OPEN to MITIGATION_SHIPPED_UNCONFIRMED |

---

## Deviations from Plan (preserved from `11-01-SUMMARY.md §Deviations`)

- Translation cache: PLAN sketched it in `libs/contracts/…`; it actually lives in
  `libs/store/src/store/_postgres.py:827` (store-native durability choice).
- Translation surface: PLAN assumed Obsidian/SAB only; actual coverage spans all brief
  reading surfaces (renderer, vault writer, list, cluster).
- `apps/brief/_i18n.py` added beyond plan to centralize `_maybe_translate()`.
- CI version bumps (`actions/checkout` v7, `actions/setup-python` v7); starlette
  `PendingDeprecationWarning` suppression in `pyproject.toml`.
- ACLED: PLAN specified a full `ingest-acled` service; actual is a 25-line contract-level
  license-gate stub. Full adapter deferred until a paid license is procured.

All five deviations are documented and none reduces a ROADMAP success criterion.

---

## Human Verification Required

Phase 11 has **no UAT file** — it closed out on 2026-07-22 without conversational UAT,
unlike Phases 8-10. The following six items carry that gap plus the operator-only checks.

### 1. Live adapter health

**Test:** `docker compose up -d ingest-telegram ingest-barentswatch`, then curl `:22015/health` and `:22016/health`
**Expected:** Both containers healthy; both endpoints return HTTP 200
**Why human:** Requires operator hardware with live `TELEGRAM_API_ID`/`TELEGRAM_API_HASH` and `BARENTSWATCH_CLIENT_ID`

### 2. Live collection emits tagged Items

**Test:** Fetch a public OSINT Telegram channel; run one BarentsWatch AIS poll over the configured bbox
**Expected:** Emitted Items carry `discipline=SOCMINT` / `MASINT/AIS` with non-null `admiralty_reliability`
**Why human:** Live third-party APIs and credentials; unit tests cover the mapper against a mocked client only

### 3. Backfill effect on the live corpus

**Test:** After `ensure_schema` applies migration 010, run `SELECT count(*) FROM infotriage.articles WHERE discipline IS NOT NULL;`
**Expected:** Non-zero — the 499 historical NULL rows map per the `source_type` CASE branches
**Why human:** Requires the live Postgres corpus; the original 0/499 finding was a live query

### 4. ACLED gate with a real license

**Test:** Provision a valid `ACLED_LICENSE_KEY` and run the ACLED ingest stub
**Expected:** Gate returns the trimmed key and the stub completes; without the key it hard-blocks
**Why human:** No paid ACLED license on the current operator setup — only the absent-key branch is exercisable today

### 5. Developer decision on Parked Debt §1

**Test:** Decide whether the YouTube/legacy adapters shipping without `discipline` is acceptable
**Expected:** Either an explicit override accepting the narrower plan scope, or an 11.x follow-up phase that owns adapter hardening + `require_discipline` wire-up (Parked Debt §1 + §3)
**Why human:** Judgment call on a divergence from ROADMAP SC-1 wording that no later phase currently claims

### 6. Missing UAT

**Test:** Walk the shipped SOCMINT/Arctic/translation surface as an operator
**Expected:** Behaviour matches intent, or the absent-UAT gap is formally accepted
**Why human:** UAT is by definition human; no `11-UAT.md` exists for this phase

---

## Gaps Summary

**The shipped Phase 11 surface holds up under code-level scrutiny.** The schema extension is
correct and idempotent, both new MCP adapters are complete four-file services with health
endpoints and compose wiring, both tag discipline and Admiralty reliability at model-build
time, the store layer persists and rehydrates both fields on every read path, translation is
genuinely local and genuinely cached with the cache threaded end-to-end, the ACLED gate is
real and actually invoked, and no debt markers appear anywhere in the 13 Phase 11 source
files. Six of seven truths verify outright.

**Three things keep this from being a clean pass.**

First, truth T-3 is partial in a way that touches the roadmap contract, not just the plan:
ROADMAP SC-1 names advanced YouTube/transcription among the adapters that must carry
discipline tags, and it does not. The plan deliberately scoped tagging to the two new
adapters, so this is arguably a plan/roadmap wording mismatch rather than an execution
miss — but no later phase owns closing it, so it should not be quietly inherited. That is
Human Verification item 5.

Second, `require_discipline()` is a gate with no installation. It is written, exported and
unit-tested, but nothing calls it. Its sibling `require_acled_license()` is correctly wired
into `acled_ingest.py:24`, which makes the omission look like an oversight rather than a
design choice.

Third, Phase 11 has no UAT and never had one. `11-VALIDATION.md` is explicit that its
Per-Task Map is gap-analysis-driven rather than per-test-pass-driven for exactly this
reason. Four operator-only behaviours (live adapter health, live tagged collection, the
live backfill result, and the licensed ACLED path) have never been observed by anyone.

On the positive side of the ledger, two items have moved since `11-VALIDATION.md` was
written and this report reflects that: commit `bb5420e` shipped the backfill migration and
the source-type mapping contract test, and commit `63b8da2` closed the three ingest test
failures documented in `11-INGEST-TEST-FIXES-PLAN.md` (both test-side bugs — a time-bomb
fixture date and an env-var leak — with no production code change), taking the suite to
678 passing.

**Verdict:** `human_needed`. Nothing here blocks the M2 milestone or invalidates the
Phase 11 closeout, and none of the open items is a regression in shipped code. But the
combination of one partial roadmap criterion, an uninstalled gate, and a phase that never
ran UAT means this cannot honestly be recorded as a full pass.

---

_Verified: 2026-08-01 — retroactive backfill closing the Phase 11 VERIFICATION.md gap surfaced by the post-Phase-10 cross-phase audit._
_Verifier: Claude (gsd-verifier). Codebase spot-checks performed directly against the working tree at `63b8da2`; test suite not re-run for this report._


---

## Re-verification 2026-08-01 (same day): open items closed — status human_needed → passed

Commit `25bdb4e` + live ops:

1. **`require_discipline()` wired:** `persist_and_publish` (libs/ingest_common) is now the admission
   gate for all modern adapters — auto-fills from `SOURCE_TYPE_TO_INT_DISCIPLINE`, raises
   `DisciplineRequired` on unknown source_type. 3 new gate tests. Gate immediately surfaced
   unmapped `pop3` → added to dict + SQL + contract test.
2. **youtube discipline:** `youtube_ingest.py` now emits `discipline="OSINT"` explicitly.
3. **Live backfill CONFIRMED:** `010-backfill-discipline.sql` applied to live :22000 —
   UPDATE 522; result: HUMINT 468, OSINT 51, NULL 3 (all 3 = `source_type='uat8'` Phase 8 UAT
   debris, intentionally left NULL per the migration's ELSE-NULL design).
4. **UAT:** 11-UAT.md created and closed 5/5 (2026-08-01).

Suite: `make test-safe` → **685 passed / 0 failed**.
