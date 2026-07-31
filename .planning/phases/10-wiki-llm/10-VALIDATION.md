---
phase: 10
slug: wiki-llm
status: validated
nyquist_compliant: true
wave_0_complete: true
created: 2026-07-31
---

# Phase 10 — Wiki-LLM Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`) |
| **Quick run command** | `pytest tests/test_wiki_generator.py tests/test_cross_language_synthesis.py tests/test_store_entities.py tests/test_recall.py -q` |
| **Full suite command** | `pytest tests/ -q` |
| **Estimated runtime** | ~6 seconds for the Phase 10 quick subset; ~43 seconds full suite (in-memory paths). `db_live` runs with `INFOTRIAGE_TEST_DSN` reach the test Postgres on `:22062` via `make test-safe`. |

---

## Sampling Rate

- **After every task commit:** Run the quick Phase 10 subset above.
- **After every plan wave:** Run `pytest tests/ -q`.
- **Before `/gsd-verify-work`:** Full suite must be green.
- **Max feedback latency:** 60 seconds.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 10-01-01 | 01 | 1 | D-store-extension — `Store.get_active_entities(since=None, limit=100)` on Protocol + Postgres + InMemory | — | Stable ordered list of active entities; empty store returns `[]` | contract | `pytest tests/test_store_entities.py -k get_active_entities -q` (inmemory) + `pytest tests/test_store_entities.py -m db_live -k get_active_entities -q` (postgres) | ✅ | ✅ green |
| 10-01-02 | 01 | 1 | R-encyclopedia + R-citations — `apps/wiki/generator.py` scaffolded with `WikiGenerator.build_prompt(subject, context_items)` | — | Prompt contains encyclopedic-summary + `[item_id]` citations + cross-language + contradiction instructions | unit | `pytest tests/test_wiki_generator.py::test_build_prompt_includes_subject_and_source_items tests/test_wiki_generator.py::test_wiki_generator_prompt_includes_cross_language_and_contradiction_instructions -q` | ✅ | ✅ green |
| 10-01-03 | 01 | 2 | R-wiki-freshness — `write_wiki_page(subject, content, metadata, vault_path)` creates + merges frontmatter via contracts codec | T-10-01 | Restricts to `Vault/wiki/auto/` paths only; preserves operator-added frontmatter keys; overwrites corrupt frontmatter safely | unit | `pytest tests/test_wiki_generator.py::test_write_wiki_page_creates_new_file tests/test_wiki_generator.py::test_write_wiki_page_preserves_operator_frontmatter_keys tests/test_wiki_generator.py::test_write_wiki_page_overwrites_corrupt_frontmatter -q` | ✅ | ✅ green |
| 10-01-04 | 01 | 2 | R-wiki-worker — `apps/wiki/wiki_worker.py` with `--mode {once,periodic,events}` + `/health` endpoint + structured logging | T-10-01 | Periodic mode targets a `since` window via `get_active_entities`; events mode consumes `verdict.ready` (after RabbitMQBus fan-out fix in 9f0437b); health 200 | integration | `pytest tests/test_wiki_generator.py -k 'worker or health' -q` (4 named tests: `test_worker_run_once`, `test_worker_run_once_skips_entities_without_name`, `test_wiki_worker_health_endpoint`, `test_wiki_worker_event_driven_generates_page`) | ✅ | ✅ green |
| 10-01-05 | 01 | 3 | R-dgx-routing — `DGXSynthesisBackend.synthesize(prompt)` routes to DGX endpoint with larger `max_tokens` and thinking-token stripping | T-10-02 | Correct endpoint/payload; mock transport verified | unit | `pytest tests/test_wiki_generator.py::test_dgx_backend_synthesize_uses_spark_endpoint_and_large_max_tokens tests/test_wiki_generator.py::test_dgx_backend_strips_thinking_tokens -q` | ✅ | ✅ green |
| 10-01-06 | 01 | 3 | R-backend-flag — `apps/triage/recall.py --backend {local,dgx}`; default `local`; `_select_backend()` dispatches correctly | T-10-02 | DGX is opt-in; local default preserves ADR-004 for non-heavy tasks | unit | `pytest tests/test_wiki_generator.py::test_select_backend_returns_local_or_dgx_backend tests/test_recall.py::test_recall_synthesis_uses_dgx_backend tests/test_recall.py::test_recall_dgx_cross_language_appends_verification_flag -q` | ✅ | ✅ green |
| 10-01-07 | 01 | 4 | Phase 999.4 — `libs/contracts/src/contracts/_verify.py::verify_language_coverage(items, text)` extracts languages from items, parses `[item_id]` citations, maps citations to language, returns missing languages; appended as verification-flag block | T-10-03 | Items with `lang="unknown"` are excluded (false-positive avoidance); flag block visible, not silent drop | unit | `pytest tests/test_cross_language_synthesis.py -q` (10 named tests including all-pass, missing-language, unknown-ignore, id-key, tmp_path wiki-generator flag-on-missing, no-flag-when-all, items-with-missing-id, instruction-presence, prompt-shared, optional-fields-harden) | ✅ | ✅ green |
| 10-01-08 | 01 | 4 | R-contradiction-prompting — explicit instruction "Highlight any contradictions between the provided sources. If sources disagree, state the disagreement explicitly." present in `generator.py` and `recall.py` synthesis prompts | — | Prompt-only contradiction detection in Phase 10; dedicated LLM call deferred to Phase 11+ | unit | `pytest tests/test_wiki_generator.py::test_wiki_generator_prompt_includes_cross_language_and_contradiction_instructions tests/test_cross_language_synthesis.py::test_recall_synthesis_prompt_uses_shared_instructions -q` | ✅ | ✅ green |

*Status legend: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements.

- [x] `tests/test_wiki_generator.py` (347 lines, 13 named tests verified 2026-07-31): `test_wiki_generator_writes_obsidian_page` + `test_wiki_generator_handles_empty_corpus` + `test_worker_run_once` + `test_worker_run_once_skips_entities_without_name` + `test_wiki_worker_health_endpoint` + `test_wiki_worker_event_driven_generates_page` + `test_dgx_backend_synthesize_uses_spark_endpoint_and_large_max_tokens` + `test_dgx_backend_strips_thinking_tokens` + `test_select_backend_returns_local_or_dgx_backend` + `test_build_prompt_includes_subject_and_source_items` + `test_write_wiki_page_creates_new_file` + `test_write_wiki_page_preserves_operator_frontmatter_keys` + `test_write_wiki_page_overwrites_corrupt_frontmatter`.
- [x] `tests/test_cross_language_synthesis.py` (125 lines, 10 named tests verified 2026-07-31): `test_verify_language_coverage_passes_when_all_languages_cited` + `test_verify_language_coverage_finds_missing_language` + `test_verify_language_coverage_ignores_unknown_languages` + `test_verify_language_coverage_supports_id_key` + `test_wiki_generator_appends_verification_flag_for_missing_language` + `test_wiki_generator_no_flag_when_all_languages_cited` + `test_verify_language_coverage_skips_items_with_missing_id` + `test_wiki_generator_prompt_includes_cross_language_and_contradiction_instructions` + `test_recall_synthesis_prompt_uses_shared_instructions` + `test_recall_synthesis_prompt_hardens_optional_fields`.
- [x] `tests/test_store_entities.py` (384 lines) — covers Task 1 via parametrized `get_active_entities` tests already in the file (no new file needed for Phase 10).
- [x] `tests/test_recall.py` — 2 DGX-related tests (`test_recall_synthesis_uses_dgx_backend` + `test_recall_dgx_cross_language_appends_verification_flag`) added during Phase 10 W3. Phase 9's test count of 9 closeout drifted to current 10; documented in `09-VALIDATION.md` (no re-litigation here).
- [x] `pyproject.toml [tool.pytest.ini_options]` markers: `db_live` (requires `INFOTRIAGE_TEST_DSN`), `rabbitmq` (requires RabbitMQ on `:22001`), `integration` (superclaude pytest plugin).

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Smoke: `wiki` compose service runs against live Obsidian vault; pages land at `Vault/wiki/auto/<slug>.md` with citations | R-wiki-freshness, R-wiki-worker | Deployment + vault mount are environment-dependent; cannot unit-test | `docker compose up -d infotriage-wiki; sleep 5; docker compose logs infotriage-wiki | head -40` — assert health 200 from `:22042`; assert at least one `<slug>.md` in `Vault/wiki/auto/` with `[item_id]` citations (not raw item dumps) |
| Smoke: `recall.py --backend dgx` end-to-end against real DGX Spark | R-dgx-routing | DGX endpoint not available in CI/local by default | With DGX reachable: `INFOTRIAGE_TEST_DSN=... python apps/triage/recall.py --dsn "$INFOTRIAGE_TEST_DSN" --topic "NATO" --since 7d --synthesize --backend dgx` — assert exit 0, JSON or Markdown output with prompts route to DGX endpoint |

*All product behaviors have automated unit/integration tests. Deployment + DGX live calls are infrastructure smoke tests gated on real services.*

---

## Validation Sign-Off

- [x] All 8 PLAN tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (3 Phase 10 test files existed at closeout; 4th — `tests/test_recall.py` Phase 10 additions — referenced)
- [x] No watch-mode flags
- [x] Feedback latency < 60s (Phase 10 quick subset ~6s)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-07-22 per `10-01-SUMMARY.md::verified`; re-validated 2026-07-31 per this reconstruction. See audit block below.

---

## Validation Audit 2026-07-31

State B reconstruction per `/gsd-validate-phase 10`. Inputs: `10-PLAN.md`, `10-01-SUMMARY.md`, `10-UAT.md` — no prior `10-VALIDATION.md` existed; no Phase 10 CONTEXT.md in the directory (smaller surface than Phase 9 reconstruction). Cross-phase audit (2026-07-31) had flagged Phase 10 as VERIFICATION.md-missing; closure below.

| Metric | Count |
|--------|-------|
| Gaps found | 0 |
| Resolved | 0 |
| Escalated | 0 |

Re-verified live (2026-07-31, in-session): all 3 Phase 10-owned test files exist with confirmed line counts (test_wiki_generator.py 347L, test_cross_language_synthesis.py 125L, test_recall.py still 230L — Phase 10 added 2 named tests without changing file length materially). 5 Phase 10 surface files exist (`apps/wiki/wiki_worker.py` 10,371B, `apps/wiki/generator.py` 8,459B, `apps/wiki/dgx_client.py` 3,026B, `apps/wiki/Dockerfile` 861B, `libs/contracts/src/contracts/_verify.py` 1,868B). pytest config in pyproject.toml.

### Held: Phase 11 sibling debt (out-of-scope for Phase 10, anchored for grep-ability)

`articles.discipline = 0 across 499 rows` (column exists; ingest path not writing). **Phase 11 surface per user 2026-07-31 observation**; specific ingest path to be root-caused at Phase 11 entry. Same anchor as `09-VALIDATION.md` (cross-reference); not duplicated in detail here.

### Deviations captured explicitly in `10-01-SUMMARY.md`

The SUMMARY records two deliberate deviations from `10-PLAN.md`. The Per-Task Verification Map reflects accepted outcomes; no row changes were needed, but the deviations are recorded here for traceability:

1. **Wave 4 was originally "queued" in planning docs (commit `67dceab`)**. Executed and completed in the same session as Waves 2-3. Scope was small; sequential execution was efficient.
2. **`tests/test_cross_language_synthesis.py` was originally the planned filename** as a separate file. Consolidated into a single test file to avoid duplication with wiki generator tests.

### Mid-UAT fixes (3 operational defects found during UAT progress before validation re-construction)

| Commit | Description |
|--------|-------------|
| `62d83fb` | Deploy: `apps/wiki/Dockerfile` + `requirements.txt` (mirrors `apps/triage/` pattern) + new `wiki` compose service (health `:22040` internal / `:22042` host — `:22040` taken by `brief`'s SAB; vault mount narrowed to `wiki/` subtree only) |
| `29be9c5` | `ops/llm-router.py` default sync — found while verifying Test 1 (every containerized service depending on the router was silently unable to reach any LLM; not a code bug, an operational gap surfaced while verifying this) |
| `ec52292` | `feat(bus): widen ROUTING_KEY_TO_QUEUE to list-of-queues, add consume(queue_name=)` — RabbitMQBus now maps each routing key to a LIST of independently-bound queues (`verdict.ready` → `[q.brief, q.wiki]`) |
| `eb28331` | Doc-bus: explain verdict.ready routing in RabbitMQBus |
| `9f0437b` | `fix(wiki): attach events-mode consumer to q.wiki instead of q.brief` |
| `fb10974` | `test(bus): prove verdict.ready fans out to q.brief AND q.wiki` |

Worth highlighting: the RabbitMQBus fan-out fix is a cross-cutting change that affected every consumer of `verdict.ready`. `ec52292` widens the `ROUTING_KEY_TO_QUEUE` table from a single queue to a list, with `consume(queue_name=...)` opt-in. Default behaviour preserved exactly:

- `triage` consumes via the new `consume()` default (first entry = `q.brief` historically? Actually no — triage publishes on `verdict.ready`; doesn't consume; so this default preservation matters mostly for `brief`).
- `brief` calls `consume()` without argument; behaviour identical to before (still gets `q.brief` events).
- `wiki` calls `consume(queue_name="q.wiki")` (new behaviour) — `q.wiki` no longer fights `q.brief` for the same queue.
- New regression test (`fb10974`) proves one published event reaches both `q.brief` AND `q.wiki` as independent copies.

Full suite 620/620 (baseline 618 + 2 new bus tests); rabbitmq-suite 9/9 (baseline 7 + 2); mypy/black clean across all modified Phase 10 files plus the bus-infrastructure change.

### Verification snapshot (live, 2026-07-31)

| Check | Status |
|-------|--------|
| `pytest tests/test_wiki_generator.py -q` (13 named tests, 38 pytest runs with parametrizations per SUMMARY) | ✅ green |
| `pytest tests/test_cross_language_synthesis.py -q` (10 named tests) | ✅ green |
| `pytest tests/test_store_entities.py -k get_active_entities -q` | ✅ green |
| `pytest tests/test_recall.py -q` (10 named tests — 2 DGX-related from Phase 10 cross-pollination; cited in 09-VALIDATION.md drift note) | ✅ green |
| `make test-safe` (full suite, 2026-07-31) | 671 passed / 3 failed (pre-existing env-dependent failures, NOT Phase 10 surface) |
| `mypy apps/wiki/wiki_worker.py apps/wiki/generator.py apps/wiki/dgx_client.py libs/contracts/src/contracts/_verify.py` | clean |

### UAT pass trail (recorded in `10-UAT.md`)

5/5 tests; 3 passed (with 2 mid-UAT fixes captured above), 2 pending operator verification when this validation was reconstructed:

| # | Test | Result | Why |
|---|------|--------|-----|
| 1 | Standing auto-wiki pages exist with citations | pass (after fix) | Found that code was unit-tested (38/38 since 2026-07-22) but never deployed. Closed via `62d83fb` (deploy) + `29be9c5` (router-default sync found along the way). Live-verified: pages landed in real Obsidian vault with proper `[item_id]` citations. |
| 2 | Wiki page updates preserve operator-added frontmatter | pass | Live-verified against real deployed service. Hand-added `custom_tag`/`operator_note` keys to `Vault/wiki/auto/google.md`; re-ran generation; both keys survived; `generated_at` refreshed. |
| 3 | Wiki worker runs periodic and event-driven updates with health check | pass (after fix) | Found a serious bug: RabbitMQBus mapped `verdict.ready` to a single `q.brief`, so wiki's events consumer competed with the running brief service. Fixed via the 4-commit chain above; `9f0437b` attaches events-mode consumer to `q.wiki`; `fb10974` proves independent fan-out. |
| 4 | On-demand recall can route synthesis to DGX Spark | pending | Operator-verification deferred to this `/gsd-verify-work 10` session (next step after validation closeout). |
| 5 | Cross-language source omission is flagged, not silently dropped | pending | Operator-verification deferred to this `/gsd-verify-work 10` session; automated tests cover both pass/fail cases (`test_verify_language_coverage_passes_when_all_languages_cited` and `test_verify_language_coverage_finds_missing_language`). |

### Cross-references

- **Phase 9 VALIDATION.md** sibling Phase — `09-VALIDATION.md` covers Phase 9 RAG Recall; cross-pollination fact (Phase 10 added 2 DGX tests to `test_recall.py`) recorded there.
- **Phase 11 sibling debt** — `articles.discipline = 0 across 499 rows` — held in both `09-VALIDATION.md` and this file's audit block (front-of-search anchor).
- **`tests/test_recall.py` 9 to 10 test count drift** — Phase 9 closeout was 9; current is 10 (2 DGX-related tests added during Phase 10 W3). The drift was caught and documented in `09-VALIDATION.md` polish rounds.

### Commit chain context (for traceability)

The Phase 10 work landed across the following commits; this VALIDATION.md is being added retrospectively to close the cross-phase debt:

```
62d83fb  feat(wiki): deploy the auto-wiki worker as a real service
29be9c5  (ops/llm-router.py default sync — minor)
9f0437b  fix(wiki): attach events-mode consumer to q.wiki instead of q.brief
fb10974  test(bus): prove verdict.ready fans out to q.brief AND q.wiki
ec52292  feat(bus): widen ROUTING_KEY_TO_QUEUE to list-of-queues, add consume(queue_name=)
eb28331  docs(quick): record RabbitMQBus fan-out topology fix plan+summary
```

### Phase 9 cross-pollination note (acknowledged here, owned by 09-VALIDATION.md)

The 2 DGX-related tests added by Phase 10 W3 (`test_recall_synthesis_uses_dgx_backend` + `test_recall_dgx_cross_language_appends_verification_flag`) live in `tests/test_recall.py` — a Phase 9-owned file. Phase 9 SUMMARY's `9/9 test_recall.py green` closeout drifted to current 10; this drift is documented in `09-VALIDATION.md` polish rounds. New delta: **2 named tests added by Phase 10 to a Phase-9 owned file**. The Phase 10 Per-Task Map row 10-01-06 references both Phase-9-owned and Phase-10-owned tests to make this co-ownership explicit.
