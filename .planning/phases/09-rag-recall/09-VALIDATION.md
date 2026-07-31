---
phase: 09
slug: rag-recall
status: validated
nyquist_compliant: true
wave_0_complete: true
created: 2026-07-31
---

# Phase 09 — RAG Recall Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`) |
| **Quick run command** | `pytest tests/test_ccir_vectors.py tests/test_build_ccir_vectors.py tests/test_prefilter.py tests/test_recall.py tests/test_store_integration.py tests/test_triage_worker.py -q` |
| **Full suite command** | `pytest tests/ -q` |
| **Estimated runtime** | ~6 seconds (Phase 9 quick subset); ~43 seconds full suite (in-memory paths). `db_live` runs with `INFOTRIAGE_TEST_DSN` reach the test Postgres on `:22062` via `make test-safe`. |

---

## Sampling Rate

- **After every task commit:** Run the quick Phase 9 subset above.
- **After every plan wave:** Run `pytest tests/ -q`.
- **Before `/gsd-verify-work`:** Full suite must be green.
- **Max feedback latency:** 60 seconds.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 09-01-01 | 01 | 1 | D-01, D-02, D-11 — `infotriage.ccir_vectors` table + HNSW index + `infotriage.audit.details` JSONB column | — | Schema migration is non-breaking: `details` is nullable JSONB, existing audit rows untouched | contract | `pytest tests/test_store_integration.py -q`; live `docker exec infotriage-postgres psql -c '\\d infotriage.ccir_vectors'` | ✅ | ✅ green |
| 09-01-02 | 01 | 1 | D-04, D-14, D-15, D-16, D-17 — `Store.find_similar_ccir()` + `Store.recall_items()` declared on Protocol + Postgres + InMemory | T-09-04 | Recall is local CLI only (Information Disclosure — accept); no network-facing surface | contract | `pytest tests/test_ccir_vectors.py -q` (inmemory) + `pytest tests/test_ccir_vectors.py -m db_live -q` (postgres) | ✅ | ✅ green |
| 09-01-03 | 01 | 2 | D-01, D-25 — `scripts/build_ccir_vectors.py` parses `ccir.md`, embeds each CCIR section with `query:` prefix, upserts into `ccir_vectors` | — | Script is runnable standalone with `--dsn`; uses local oMLX embeddings only (ADR-004); DGX deferred (D-22, D-23) | unit + smoke | `pytest tests/test_build_ccir_vectors.py -q` (parser) + `python scripts/build_ccir_vectors.py --dsn "$INFOTRIAGE_TEST_DSN"` (smoke, manual-only) | ✅ | ✅ green |
| 09-01-04 | 01 | 2 | D-02, D-24, D-26 — CCIR vector storage round-trip + HNSW index verification | — | Idempotent upsert (`ON CONFLICT`); HNSW index used for nearest-neighbour recall | contract + db_live | `pytest tests/test_ccir_vectors.py -q` + `pytest tests/test_ccir_vectors.py -m db_live -q` | ✅ | ✅ green |
| 09-01-05 | 01 | 3 | D-04, D-05, D-07, D-08, D-09, D-10, D-12 — pre-filter integration in `apps/triage/worker.py` between embedding compute and `score_item()`; skip → `bucket=skip` + audit row | T-09-01, T-09-02 | τ=0.70 evidence-anchored default (was 0.50; fixed in commit `3acbc45`); fall-through on `find_similar_ccir` failure — no silent data drops; D-10 explicit | integration | `pytest tests/test_prefilter.py -q` | ✅ | ✅ green |
| 09-01-06 | 01 | 3 | D-04, D-08, D-10, D-12 — pre-filter skip/pass/fallback/threshold/audit/entity-resolution coverage | T-09-01, T-09-02 | TDD regression tests pin τ in bracket `(0.69, 0.71]`; no CCIR vectors + DB error fall-through paths covered; `97ba50c` test-quality fix on skip-path assertion (was `cosine=1.0` always-passing — corrected to `cosine=0.60<τ`). Full calibration narrative: see audit-block Pre-filter Threshold Calibration table. | unit + integration | `pytest tests/test_prefilter.py -q` (9 named tests verified 2026-07-31, listed in Wave 0 Requirements) | ✅ | ✅ green |
| 09-01-07 | 01 | 4 | D-14, D-15, D-17, D-18, D-19, D-20, D-21, D-22 — `apps/triage/recall.py` CLI with `--topic`, `--since`, `--ccir`, `--bucket`, `--limit`, `--json`, `--obsidian`, `--synthesize`, `--include-body` | T-09-03 | Synthesis prompt restricts model to cite only from provided article context with `[item_id]` tags; local qwen36 only (ADR-004; DGX deferred D-22/D-23) | unit + smoke | `pytest tests/test_recall.py -q` (10 named tests verified 2026-07-31, listed in Wave 0 Requirements; SUMMARY's 9-figure closeout predates 2 DGX-related cross-pollination tests) + `INFOTRIAGE_TEST_DSN=... python apps/triage/recall.py --dsn "$INFOTRIAGE_TEST_DSN" --topic "Arctic security" --since 7d --json --limit 5` (smoke, manual-only) | ✅ | ✅ green |
| 09-01-08 | 01 | 4 | D-18, D-19, D-20, D-21 — recall output modes (Markdown default, `--json`, `--obsidian`, `--synthesize`); JSON output content hygiene | T-09-03 | `--json` strips `body` field unconditionally (commit `09-01`), keeps `summary` + metadata; reduces content over-disclosure surface even when paired with `--include-body` | unit | `pytest tests/test_recall.py -q` | ✅ | ✅ green |
| 09-01-09 | 01 | 5 | All 8 above + mypy + live smoke | — | Full suite baseline 479/0/0 (per original SUMMARY); 617/617 post-`3acbc45` + `97ba50c`; current `make test-safe` shows 671/3 across the whole repo (the 3 failures are env-dependent `test_ingest_telegram.py::test_ingest_emits_item_with_discipline_and_reliability`, `tests/test_ingest_telegram.py::test_ingest_dry_run_does_not_persist`, `tests/test_ingest_youtube.py::test_ingest_r2_dual_output` — pre-existing, NOT Phase 9 surface; flagged separately in `08-VALIDATION.md` 2026-07-31 audit block) | full suite | `pytest tests/ -q` + `mypy apps/triage/worker.py apps/triage/recall.py scripts/build_ccir_vectors.py` | ✅ | ✅ green (Phase 9 contributing subset) |

*Status legend: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements.

- [x] `tests/test_ccir_vectors.py` (259 lines) — CCIR vector store/retrieval contract (inmemory + db_live Markers per pyproject.toml)
- [x] `tests/test_build_ccir_vectors.py` (76 lines) — CCIR parser + script-structure tests
- [x] `tests/test_prefilter.py` (351 lines, **9 named tests verified 2026-07-31** via `grep -E '^(def\|async def) test_'`): `test_prefilter_skip_calls_no_llm` + `test_prefilter_pass_calls_llm` + `test_prefilter_no_ccir_vectors_falls_through` + `test_prefilter_db_failure_falls_through_to_llm` + `test_prefilter_threshold_configurable` + `test_prefilter_threshold_above_similarity_skips` + `test_prefilter_entity_resolution_still_runs` + `test_prefilter_default_threshold_skips_below_070` + `test_prefilter_default_threshold_passes_at_071`. The last two are the τ-bracket regression tests added in commits `3acbc45`/`b77468d`.
- [x] `tests/test_recall.py` (230 lines, **10 named tests verified 2026-07-31** — 2 more than SUMMARY's 9-figure closeout due to post-Phase-9 cross-pollination with Phase 10 DGX routes; the 9 in SUMMARY are still valid for the Phase 9 surface): `test_recall_default_markdown_output` + `test_recall_json_output` + `test_recall_json_include_body_strips_body` + `test_recall_filter_arguments` + `test_recall_no_results` + `test_recall_synthesis_calls_llm` + `test_recall_synthesis_uses_dgx_backend` + `test_recall_dgx_cross_language_appends_verification_flag` + `test_recall_since_relative` + `test_recall_obsidian_output`. The last two DGX-tagged tests landed after Phase 9 closeout but live in the Phase-9-owned file; coverage is co-tracked with Phase 10.
- [x] `tests/test_store_integration.py` (408 lines) — extended to expect `infotriage.ccir_vectors` as part of the schema inventory
- [x] `tests/test_triage_worker.py` (592 lines) — pre-existing worker regression tests (Phase 5–8 surface); pre-filter integration confirmed by `tests/test_prefilter.py` not duplicating
- [x] `pyproject.toml [tool.pytest.ini_options]` markers: `db_live` (requires `INFOTRIAGE_TEST_DSN`), `rabbitmq` (requires RabbitMQ on `:22001`), `integration` (superclaude pytest plugin)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Smoke: `build_ccir_vectors.py` runs end-to-end against live Postgres with 12 CCIRs from `ccir.md` | D-01, D-02 | The script requires live oMLX endpoint + live DSN; CI host has only `INFOTRIAGE_TEST_DSN` and the runner boots the test Postgres via `make test-safe` | `INFOTRIAGE_TEST_DSN=postgresql://infotriage:infotriage@127.0.0.1:22062/infotriage?application_name=build_ccir_vectors python scripts/build_ccir_vectors.py --dsn "$INFOTRIAGE_TEST_DSN"` — assert output `"Built N CCIR vectors: M new, N-M updated"` with N=12 (PIR-1..6, FFIR-1..3, SIR-1..3) |
| Smoke: `recall.py --json` against live test corpus returns exit 0 with ranked results | D-14, D-19 | Live vector search requires oMLX + Postgres; no fixture sufficient | `INFOTRIAGE_TEST_DSN=... python apps/triage/recall.py --dsn "$INFOTRIAGE_TEST_DSN" --topic "Arctic security" --since 7d --json --limit 5` — assert exit 0, JSON array with 5 entries containing `item_id/url/title/source/ccir/score/similarity` keys |

*All product behaviors have automated unit/integration tests; these two are infrastructure smoke tests gated on the live test DB + oMLX.*

---

## Validation Sign-Off

- [x] All 9 PLAN tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (5 Phase 9 test files existed at closeout)
- [x] No watch-mode flags
- [x] Feedback latency < 60s (Phase 9 quick subset ~6s)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-07-21 per `09-01-SUMMARY.md::verified`; re-validated 2026-07-31 per this reconstruction. See audit block below.

---

## Validation Audit 2026-07-31

State B reconstruction per `/gsd-validate-phase 9`. Inputs: `09-PLAN.md`, `09-01-SUMMARY.md`, `09-UAT.md`, `09-CONTEXT.md` — no prior `09-VALIDATION.md` existed. Cross-phase audit (2026-07-31) had flagged Phase 9 as VERIFICATION.md-missing; closure below.

| Metric | Count |
|--------|-------|
| Gaps found | 0 |
| Resolved | 0 |
| Escalated | 0 |

### Held: Phase 11 sibling debt (anchored here for grep-ability; not Phase 9 work)

`articles.discipline = 0 across 499 rows` (column exists; ingest path not writing). **Phase 11 surface per user 2026-07-31 observation**; specific ingest path to be root-caused at Phase 11 entry. Anchor duplicated near the top of this audit block so future readers can find it without scrolling through the τ calibration narrative below. Held for `/gsd-validate-phase 11` or `/gsd-verify-work 11`.

Re-verified live (2026-07-31, in-session): all 5 Phase 9 test files exist with the expected line counts (test_ccir_vectors.py 259L, test_build_ccir_vectors.py 76L, test_prefilter.py 351L, test_recall.py 230L, test_store_integration.py 408L); `apps/triage/recall.py` and `scripts/build_ccir_vectors.py` exist (9612B + 3699B respectively); pyproject.toml pytest config in place.

### Deviations captured explicitly in `09-01-SUMMARY.md`

The SUMMARY records five deliberate deviations from `09-PLAN.md`. The Per-Task Verification Map above reflects accepted outcomes; no row changes were needed, but the deviations are recorded here for traceability:

1. **`find_similar_ccir` returns the raw nearest match; caller applies τ** (cleaner separation: store method is reusable for recall/debugging, has no hidden threshold policy).
2. **`recall_items` uses `psycopg.sql` composable SQL** (safer WHERE-clause assembly; protection against f-string concatenation drift).
3. **`tests/test_store_integration.py` updated to expect `infotriage.ccir_vectors`** (schema inventory reflects actual state).
4. **`get_all_entities` uses `ARRAY_AGG ... FILTER (WHERE mention IS NOT NULL AND lang IS NOT NULL)`** to avoid `[None]` aliases (concurrent Phase 8 fix during Phase 9 closeout).
5. **`--json` strips `body` field unconditionally** (preserves `summary` + metadata; reduces content over-disclosure surface even when paired with `--include-body`).

### Pre-filter threshold calibration (commits + backlog 999.2)

Two mid-UAT fixes pinned the CCIR pre-filter threshold at τ=0.70:

| Commit | Description |
|--------|-------------|
| `3acbc45` | `fix(triage): anchor CCIR pre-filter threshold to corpus evidence (0.50 → 0.70)` — default raised from 0.50 to 0.70 |
| `b77468d` | `chore(planning): note pre-filter threshold miscalibration alongside 999.2 backlog` — STATE.md cross-reference to backlog 999.2 |
| `97ba50c` | `fix(tests): correct mislabeled pre-filter entity-resolution test` — test-quality fix: `test_prefilter_entity_resolution_still_runs` used `cosine=1.0` which always passes the gate; corrected to `cosine=0.60<τ` so the assertion actually exercises the skip path |
| `b9aebae` (Phase 9 closeout) | `fix(ops): sync docker-compose's CCIR pre-filter default with worker.py (0.50 → 0.70)` — operator-side default sync |

τ=0.70 is anchored to the **lowest live observed similarity against the 13 CCIR topic vectors** for this corpus. Per `09-UAT.md::Test 1`: "*deliberately does NOT change production filtering behavior today (no safe cut point yet)*" — the gate remains structurally a no-op against current corpus range (0.74–0.85), but the regression-proof default prevents future drift back to the uncalibrated 0.50.

The TDD bracket-pin regression tests added in `3acbc45` confirm `INFOTRIAGE_PREFILTER_THRESHOLD ∈ (0.69, 0.71]` at the import level — RED against the old 0.50 default, GREEN post-fix.

Backlog 999.2 tracks the proper future recalibration: larger corpus + synthetic negative controls. Today's state is **regression-proof, not actively filtering** — those are distinct observations.

### Verification snapshot (live, 2026-07-31)

| Check | Status |
|-------|--------|
| `pytest tests/test_ccir_vectors.py -q` | ✅ green |
| `pytest tests/test_build_ccir_vectors.py -q` | ✅ green |
| `pytest tests/test_prefilter.py -q` (9 named tests) | ✅ green (including `97ba50c` skip-path test-quality fix) |
| `pytest tests/test_recall.py -q` (9 named tests) | ✅ green (with `--json` body-stripping verified) |
| `pytest tests/test_store_integration.py -q` (extended for `ccir_vectors`) | ✅ green |
| `make test-safe` (full suite, 2026-07-31) | 671 passed / 3 failed (pre-existing env-dependent failures, NOT Phase 9 surface) |
| `mypy apps/triage/worker.py apps/triage/recall.py scripts/build_ccir_vectors.py` | clean |

### UAT pass trail (recorded in `09-UAT.md`)

5/5 tests passed in 2026-07-25 → 2026-07-26 session:

| # | Test | Result | Why |
|---|------|--------|-----|
| 1 | CCIR pre-filter gate skips off-topic items | pass (after fix) | Discovered a real mid-UAT issue (τ=0.50 uncalibrated; gate structurally inert against observed 0.74–0.85 corpus range). Fixed via `3acbc45` + `b77468d` + `97ba50c`. 9 new + edited regression tests pin the threshold and the skip-path assertion. |
| 2 | Thematic recall CLI returns cited results | pass | Verified live against production corpus ("Arctic security", 30d) — JSON ranked results + `--synthesize` per-claim `[item_id]` citations via local qwen36. |
| 3 | Pre-filter failures fall through to normal scoring | pass | Both fall-through paths have dedicated regression tests (no-CCIR-vectors + DB failure). |
| 4 | Entity resolution still runs on pre-filter-skipped items | pass (after fix) | Verified with real skip scenario (`cosine=0.60 < τ=0.70`, `score_calls=0` confirming skip). Plus `97ba50c` test-quality fix on the underlying test. |
| 5 | Recall JSON output doesn't leak full article bodies | pass | `--json` strips `body` unconditionally; `--json --include-body` together also strip body (verified in code + live). |

*(The original bottom-of-block duplicated "### Held: Phase 11 sibling debt" section was relocated to the top of this audit block for grep-ability. Calibrated reference: see "### Held: Phase 11 sibling debt" right after the metric table.)*
