---
phase: 09-rag-recall
verified: 2026-08-01T00:00:00Z
status: passed
score: 2/2
behavior_unverified: 0
overrides_applied: 0
re_verification: true  # retroactive backfill: Phase 9 closed 2026-07-21 with no VERIFICATION.md; gap surfaced by the 2026-07-31 cross-phase audit and by 09-VALIDATION.md §Validation Audit
deferred:
  - truth: "Pre-filter actually cuts LLM caller volume on the live corpus (the efficacy half of the ROADMAP Phase 9 goal statement)"
    addressed_in: "Phase 999.2 (backlog)"
    evidence: "apps/triage/worker.py:182-184 — 'A functional recalibration (larger corpus + synthetic negative controls, or relative/rank-based scoring instead of an absolute cosine cutoff) is tracked as backlog phase 999.2 and is out of scope here.' Cross-referenced in 09-VALIDATION.md §Pre-filter threshold calibration and STATE.md (commit b77468d). NOTE: the ROADMAP §Phase 999.2 entry is still worded for *dedup* threshold calibration only — it should be widened to name the CCIR pre-filter τ explicitly, or the pre-filter recalibration risks being lost when 999.2 is promoted."
---

# Phase 09: RAG Recall — Verification Report

**Phase Goal:** Cut LLM caller volume via a CCIR pre-filter and enable thematic recall over the durable corpus.

**Verified:** 2026-08-01 (retroactive backfill — Phase 9 shipped 2026-07-21 without a VERIFICATION.md)
**Status:** PASSED (2/2 ROADMAP success criteria) — with one accepted, documented limitation (see Known Limitation below)
**Re-verification:** Yes — this file closes the artifact gap flagged by the 2026-07-31 cross-phase audit and recorded in `09-VALIDATION.md §Validation Audit 2026-07-31`. Evidence is a fresh goal-backward pass over the codebase (file:line citations below), cross-checked against `09-01-SUMMARY.md`, `09-UAT.md` (5/5), and `09-VALIDATION.md` (status: validated).

---

## Goal Achievement

### Success Criteria (ROADMAP §Phase 9)

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| SC-1 | Clearly off-topic items skip the LLM (`cosine(article, ccir.vector) < τ`), logged in `audit`. | **MET (mechanism)** — see Known Limitation for live efficacy | Gate lives in `apps/triage/worker.py:185-218` (τ read from `INFOTRIAGE_PREFILTER_THRESHOLD`, default `0.70`) with the skip enrichment at `worker.py:259-268` (`bucket=skip`, `why="pre-filter: max_cosine=… < threshold"`) and the audit row at `worker.py:274-291` (`op="pre_filter_skip"`, `details={max_similarity, threshold, best_ccir}`). Behaviorally pinned by `tests/test_prefilter.py:65-97` which asserts `score_calls == []` (LLM never invoked), `bucket == "skip"`, one published verdict, and the audit row with `details["best_ccir"]`. |
| SC-2 | A thematic recall (`recall.py --topic … --since …`) cites `articles.id`/`url` per claim; heavy synthesis may run on DGX. | **MET** | `apps/triage/recall.py:164-189` defines the CLI (`--topic` required, `--since`, `--ccir`, `--bucket`, `--limit`, `--json`, `--obsidian`, `--synthesize`, `--backend {local,dgx}`, `--include-body`). Per-claim citation: synthesis prompt emits `[item_id: …]` refs at `recall.py:119`; Markdown output renders `[title](url)` at `recall.py:141`. The ids/urls are real `articles` columns — `libs/store/src/store/_postgres.py:780` selects `a.id AS item_id, a.title, a.source, a.url`. DGX path: `recall.py:82-87` `_select_backend()` returns `DGXSynthesisBackend()` for `--backend dgx` (imported from `apps/wiki/dgx_client.py` via the `sys.path` insert at `recall.py:21`). |

**Score:** 2/2.

### Observable Truths (derived from 09-PLAN.md `must_haves.truths`)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | One vector per CCIR in `infotriage.ccir_vectors` (D-01, D-02) | ✓ VERIFIED | Table + HNSW index at `libs/store/sql/003-vectors.sql:51-60`. Upsert (`ON CONFLICT (ccir_id) DO UPDATE`) at `_postgres.py:704-719`. Populated by `scripts/build_ccir_vectors.py:105-106`. |
| 2 | τ configurable via `INFOTRIAGE_PREFILTER_THRESHOLD`; `find_similar_ccir` returns the raw nearest match, worker applies τ (D-04, D-05) | ✓ VERIFIED | `_postgres.py:721-739` returns `{ccir_id, similarity}` with no threshold logic; worker applies it at `worker.py:200-204`. Env override behaviorally tested in `tests/test_prefilter.py:184` and `:221`. Default pinned into the bracket `(0.69, 0.71]` by `tests/test_prefilter.py:299` and `:326`. |
| 3 | Pre-filter runs after embedding, before `score_item()` (D-07) | ✓ VERIFIED | Embedding at `worker.py:169`; gate at `worker.py:185-218`; dedup + `score()` guarded behind `if pre_filter_passes:` at `worker.py:221-258`. |
| 4 | Skip writes enrichment with `ccir=none`, `bucket=skip` (D-08) | ✓ VERIFIED | `worker.py:259-268`, persisted at `worker.py:271-272`. Asserted in `tests/test_prefilter.py:91`. |
| 5 | Audit pre-filter skips with `details` JSONB (D-11, D-12) | ✓ VERIFIED | Column added by `libs/store/sql/004-audit.sql:13` (`ADD COLUMN IF NOT EXISTS details JSONB`, non-breaking). Written by `_postgres.py:807-819`. Called at `worker.py:277-287`. Asserted at `tests/test_prefilter.py:95-97`. |
| 6 | Pre-filter failure / empty CCIR table falls through to the LLM — never a silent drop (D-10, T-09-02) | ✓ VERIFIED | `worker.py:188-204`: `ccir_lookup_failed` and `best_ccir is None` both force `pre_filter_passes = True`. Two dedicated tests: `tests/test_prefilter.py:130` (`test_prefilter_no_ccir_vectors_falls_through`) and `:155` (`test_prefilter_db_failure_falls_through_to_llm`). |
| 7 | Entity resolution (Phase 8) still runs on pre-filter-skipped items | ✓ VERIFIED | Entity block at `worker.py:293-298` sits after the shared `put_enrichment`/`put_embedding` and outside the `pre_filter_passes` branch, so it executes on both paths. Test `tests/test_prefilter.py:259` (`test_prefilter_entity_resolution_still_runs`) — corrected in commit `97ba50c` from a bogus `cosine=1.0` fixture (which always *passed* the gate) to `cosine=0.60` with `score_calls == 0`, so it now genuinely exercises the skip path. |
| 8 | Recall searches item embeddings by vector similarity to the topic (D-14, D-15) | ✓ VERIFIED | `_postgres.py:741-803` joins `enrichment → articles → embeddings`, orders by `emb.embedding <=> query_vector`, returns `similarity = 1.0 - dist`. Topic embedded with the `query:` prefix via `recall.py:36-50`. |
| 9 | Markdown by default; `--json`, `--obsidian`, `--synthesize` (D-18, D-19, D-20) | ✓ VERIFIED | `_markdown_output` `recall.py:131`, `_obsidian_output` `recall.py:148`, JSON branch `recall.py:223`. Covered by `tests/test_recall.py:76, :85, :236`. |
| 10 | JSON output never leaks full article body | ✓ VERIFIED | `recall.py:223` builds `safe_results` by dropping `body` unconditionally, before any JSON emission — so `--json --include-body` also stays clean. Test `tests/test_recall.py:94` (`test_recall_json_include_body_strips_body`). |
| 11 | Local qwen36 only for synthesis (ADR-004) | ✓ VERIFIED | `recall.py:53-80`: `LLM_BASE_URL` defaults to `http://127.0.0.1:8000/v1` (local oMLX), `LLM_MODEL` defaults to `qwen36-ud-4bit`. Embeddings likewise local (`recall.py:36-50`, `scripts/build_ccir_vectors.py:31`). No cloud endpoint anywhere in the Phase 9 surface. |
| 12 | Reuse `infotriage.embeddings` for items; `ccir_vectors` for CCIRs (D-24, D-25) | ✓ VERIFIED | Recall joins the pre-existing `infotriage.embeddings` (`_postgres.py:784`); the new table is used only by `find_similar_ccir` (`_postgres.py:730`). |

**Score:** 12/12 plan truths verified, 0 behavior-unverified.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `libs/store/sql/003-vectors.sql` | `ccir_vectors` table + HNSW index | ✓ VERIFIED | Lines 51-60. `vector(1024)`, `hnsw (embedding vector_cosine_ops) WITH (m=16, ef_construction=64)`. |
| `libs/store/sql/004-audit.sql` | `details JSONB` on audit | ✓ VERIFIED | Line 13, `IF NOT EXISTS` — non-breaking. |
| `libs/store/src/store/_protocol.py` | `put_ccir_vector`, `find_similar_ccir`, `recall_items` | ✓ VERIFIED | Lines 248, 255, 271. |
| `libs/store/src/store/_postgres.py` | Postgres impls | ✓ VERIFIED | Lines 704, 721, 741, 807. `recall_items` uses `psycopg.sql` composables + `Placeholder()` — no f-string SQL (`_postgres.py:755-790`). |
| `libs/store/src/store/_inmemory.py` | InMemory impls | ✓ VERIFIED | Lines 386, 390, 406 — keeps the store contract testable without Postgres. |
| `scripts/build_ccir_vectors.py` | Parse `ccir.md` → embed → upsert | ✓ VERIFIED | 3.6K. `_extract_sections` at line 47, 2048-char truncate at line 87, `query: ` prefix at line 105, `store.put_ccir_vector` at line 106, `--dsn` required at line 93. |
| `apps/triage/worker.py` | Pre-filter integration | ✓ VERIFIED | Lines 171-291. |
| `apps/triage/recall.py` | Thematic recall CLI | ✓ VERIFIED | 9.4K, all 10 flags present (`recall.py:168-189`). |
| `tests/test_ccir_vectors.py` | Vector store contract | ✓ VERIFIED | 11 test functions. |
| `tests/test_build_ccir_vectors.py` | Parser tests | ✓ VERIFIED | 3 test functions. |
| `tests/test_prefilter.py` | Pre-filter integration | ✓ VERIFIED | 9 test functions (names listed in the truths table above). |
| `tests/test_recall.py` | Recall CLI | ✓ VERIFIED | 10 test functions — the 2 DGX-tagged ones (`test_recall_synthesis_uses_dgx_backend:151`, `test_recall_dgx_cross_language_appends_verification_flag:168`) landed post-closeout via Phase 10 cross-pollination; co-tracked in `09-VALIDATION.md`. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `apps/triage/worker.py` | `Store.find_similar_ccir` | `asyncio.to_thread(store.find_similar_ccir, vec)` | WIRED | `worker.py:191`, inside try/except that sets the fall-through flag. |
| `apps/triage/worker.py` | `infotriage.audit` | `store.audit_write(op="pre_filter_skip", details=…)` | WIRED | `worker.py:277-287` → `_postgres.py:807-819` → SQL column from `004-audit.sql:13`. |
| `apps/triage/recall.py` | `Store.recall_items` | `PostgresStore` + `recall_items(query_vector, since, ccir, bucket, limit)` | WIRED | Import `recall.py:29`; store call reaches `_postgres.py:741`. |
| `apps/triage/recall.py` | `apps/wiki/dgx_client.py` | `sys.path` insert + `from dgx_client import DGXSynthesisBackend, RecallBackend` | WIRED | `recall.py:21` + `recall.py:30`; selected at `recall.py:82-87`. Path-insert import rather than a package dependency — works, but brittle if `apps/wiki` moves (see Anti-Patterns). |
| `scripts/build_ccir_vectors.py` | `infotriage.ccir_vectors` | `store.put_ccir_vector(ccir_id, vec)` | WIRED | Line 106 → `_postgres.py:704`. |
| `apps/triage/recall.py` | `contracts` verification helpers | `verify_language_coverage`, `CITATION_INSTRUCTION` | WIRED | `recall.py:23-28` — closes Phase 999.4's cross-language silent-omission mode on the recall path too. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `recall.py` results table | `results` | `store.recall_items()` → live JOIN over `enrichment`/`articles`/`embeddings` (`_postgres.py:779-792`) | Yes | ✓ FLOWING — UAT Test 2 returned live production hits (Arctic Council/Tromsø, NATO Ankara, Barents Sea exercise) with real `item_id`/`url`. |
| `worker.py` pre-filter decision | `best_ccir` | `store.find_similar_ccir()` → HNSW nearest neighbour over `ccir_vectors` | Yes | ✓ FLOWING — production logs show 1254+ real similarity values in the 0.743-0.848 band on 2026-07-24, i.e. the lookup returns genuine vectors, not a stub. |
| `worker.py` skip enrichment | `fields` / audit `details` | Computed from live `_prefilter_sim` / `_prefilter_threshold` | Yes (path never taken live) | ⚠️ STATIC-IN-PRODUCTION — the values are computed, not hardcoded, but no live item has ever traversed this branch. See Known Limitation. |

### Behavioral Spot-Checks

Per instruction, the test suite was **not** re-run in this pass. Cited results are the recorded ones.

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full repo suite green at HEAD | `make -f ops/Makefile test-safe` | **678 passed / 0 failed** in 35.31s (live run 2026-08-01 this session; prior recorded baseline 677/0 at `63b8da2`, +1 from `bb5420e` per-ingest contract test) | ✓ PASS |
| Recall CLI coverage | `pytest tests/test_recall.py -q` | 10/10 test functions present and green per `09-VALIDATION.md §Verification snapshot` | ✓ PASS (recorded) |
| Pre-filter coverage | `pytest tests/test_prefilter.py -q` | 9/9 green, incl. the `97ba50c` skip-path correction | ✓ PASS (recorded) |
| CCIR build smoke | `python scripts/build_ccir_vectors.py --dsn "$INFOTRIAGE_TEST_DSN"` | 12 CCIR vectors built (`09-01-SUMMARY.md`) | ✓ PASS (recorded, manual-only per `09-VALIDATION.md §Manual-Only Verifications`) |
| Recall live smoke | `python apps/triage/recall.py --dsn … --topic "Arctic security" --since 7d --json --limit 5` | exit 0, ranked JSON with `item_id/url/ccir/score/similarity` | ✓ PASS (recorded; independently re-confirmed against the production corpus in UAT Test 2) |

*Discrepancy note (reconciled 2026-08-01):* STATE.md's 677/0 baseline predates `bb5420e` (adds one per-ingest contract test). Live `make test-safe` run this session: **678 passed / 0 failed**. STATE.md baseline bumped to match.

### Probe Execution

Not applicable — this repo has no `scripts/*/tests/probe-*.sh` convention, and neither `09-PLAN.md` nor `09-01-SUMMARY.md` declares probes. Verification is pytest-based.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| R1 | 09-PLAN | Triage pipeline delivers scored, bucketed items | SATISFIED | Pre-filter is transparent on the pass path — `score()` output is untouched (`worker.py:246-258`); `tests/test_prefilter.py:100` pins it. |
| ADR-001 | 09-PLAN | Postgres canonical store | SATISFIED | All new state is Postgres (`003-vectors.sql`, `004-audit.sql`); no sidecar store introduced. |
| ADR-004 | 09-PLAN | Local LLM only | SATISFIED | Embeddings and synthesis both default to `127.0.0.1:8000` oMLX (`recall.py:36-58`, `build_ccir_vectors.py:31`). |
| ADR-006 | 09-PLAN | Microservice architecture / entity resolution | SATISFIED | Entity resolution preserved on both pre-filter branches (`worker.py:293-298`). |

No orphaned requirements: `.planning/REQUIREMENTS.md` maps no Phase 9 IDs beyond those declared in `09-PLAN.md`.

### Prohibitions (09-PLAN `must_haves.prohibitions`)

| Prohibition | Status | Evidence |
|-------------|--------|----------|
| MUST NOT use cloud LLM or embedding for pre-filter or recall | ✓ HELD | Only `LLM_BASE_URL`/`OMLX` localhost defaults present; grep of the Phase 9 surface finds no external endpoint. |
| MUST NOT add a SAB `/recall` HTTP endpoint in Phase 9 | ✓ HELD | `recall.py` is argparse/CLI only (`main()` at `recall.py:164`); no route registration. The `RecallBackend` protocol keeps a future HTTP wrap cheap. |
| MUST NOT modify `score_item()` output for items that pass the pre-filter | ✓ HELD | Pass path at `worker.py:221-258` is the original dedup+score flow, unchanged; `tests/test_prefilter.py:100` asserts the LLM verdict is used verbatim. |

All three are judgment-tier and resolved by direct code inspection above — none are silently passed.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | `TODO`/`FIXME`/`XXX`/`HACK`/`PLACEHOLDER` scan across `recall.py`, `build_ccir_vectors.py`, `worker.py`, `_postgres.py`, `_inmemory.py` | — | **Clean, zero matches.** No unreferenced debt markers; the debt-marker gate does not fire. |
| `apps/triage/recall.py` | 20-21 | Cross-app import via `sys.path.insert` (`apps/wiki` for `dgx_client`) | ℹ️ INFO | Works today, but couples `apps/triage` to `apps/wiki`'s filesystem location outside the packaging system. Would break on a container that ships only the triage app. Not a Phase 9 regression — Phase 10 introduced the DGX import on this path. |
| `ccir.md` | headings | `ccir.md` currently defines 11 CCIRs (PIR-1..6, FFIR-1..4, SIR-1) | ℹ️ INFO | `09-01-SUMMARY.md` records 12 built and `worker.py:176` narrates 13 topic vectors — the file has drifted since Phase 9 closeout. Harmless (the build script re-derives from `ccir.md` every run) but the counts in the docs are now stale. |

### Known Limitation — the pre-filter does not filter anything today

This is the one thing a reader of `09-01-SUMMARY.md`'s green checkmarks would miss, so it is stated plainly:

**The CCIR pre-filter gate is correct, wired, and regression-proof, but it has never skipped a single item in production.** The phase goal's first clause — "cut LLM caller volume" — is delivered at 0% reduction.

- Original τ=0.50 was chosen at design time with zero corpus calibration. Live evidence (`09-UAT.md` Test 1): 0 `pre_filter_skip` audit rows ever, 0 `enrichment.why LIKE 'pre-filter:%'` rows ever, and 1254+ "pre-filter PASS" / 0 "SKIP" on 2026-07-24 alone.
- Measurement over 423 live items found the entire corpus — genuine signal and structural junk alike — clustered in **0.743-0.848**, with the two **interleaving** (lowest genuine CCIR match 0.7452 sits *below* junk at 0.7485). There is no safe absolute cosine cut point in that band today.
- The `3acbc45` fix raised the default to **τ=0.70**, an evidence-anchored floor strictly below every observed similarity. It deliberately preserves today's behavior (no filtering) while preventing drift back to the uncalibrated 0.50; `b9aebae` synced `docker-compose.yml:177` to the same default.
- Real recalibration (larger corpus + synthetic negative controls, or rank-relative scoring instead of an absolute cutoff) is deferred — see the `deferred` block in the frontmatter.

The operator accepted this explicitly when closing UAT Test 1 as "pass (after fix)". SC-1 is therefore scored MET on the mechanism, which is what the criterion words ("items *below τ* skip the LLM, logged in audit") and what the behavioral test at `tests/test_prefilter.py:65-97` proves. Efficacy is tracked as deferred, not claimed.

**Action for whoever promotes backlog 999.2:** its ROADMAP goal text still reads *dedup* threshold calibration only. Widen it to name the CCIR pre-filter τ, or this recalibration will be dropped on promotion.

### Human Verification Required

None outstanding. Phase 9 already completed a full human UAT pass on 2026-07-25/26 — `09-UAT.md`, **5/5 tests passed** (2 of them "pass (after fix)", with the fixes landed as `3acbc45`, `b77468d`, `97ba50c`). Two of the five were verified live against the production corpus rather than fixtures (Test 2 recall citations, Test 5 JSON body hygiene). No new human-verifiable items surfaced in this backfill.

### Gaps Summary

No blocking gaps. Both ROADMAP success criteria are met with code-level and test-level evidence, and the phase carries a completed 5/5 UAT plus a `validated` VALIDATION.md.

One accepted, well-documented limitation (pre-filter is inert against the current corpus — see above) is recorded as deferred to backlog 999.2 rather than as a gap, because it was measured, root-caused, operator-accepted at UAT, and pinned against regression by two bracket tests. Three informational anti-patterns (cross-app `sys.path` import, stale CCIR counts in prose, and the 677-vs-678 suite-count discrepancy) are noted for hygiene and block nothing.

---

_Verified: 2026-08-01 — retroactive backfill_
_Verifier: Claude (gsd-verifier). Codebase evidence gathered by direct Read/Grep at HEAD `63b8da2`; test results cited from `.planning/STATE.md`, `09-VALIDATION.md`, and `09-UAT.md` (suite not re-run in this pass, per instruction)._
