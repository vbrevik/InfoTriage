---
phase: 06-brief-app
verified: 2026-07-11T00:00:00Z
status: passed
score: 14/14 must-haves verified
behavior_unverified: 0
overrides_applied: 0
gaps: []
re_verification:
  previous_status: gaps_found
  previous_score: 1/3 roadmap must-haves verified (1 partial/failed, 2 failed)
  gaps_closed:
    - "brief (:22040) clusters via pgvector — consumer.py/main.py now LEFT JOIN infotriage.embeddings, renderer.py no longer defaults to [0.0]*4, CLUSTER_THRESHOLD wired end-to-end, live UAT confirms multi-item semantic clusters"
    - "A vault-writer emits high-value items + the SAB as Obsidian .md — apps/brief/vault_writer.py now exists, is wired into consumer.py (write_vault_digest) and main.py (/vault endpoint), live UAT confirms 24 .md files written with parseable front-matter"
    - "Email surfaces here (SAB + Obsidian) — Obsidian half now satisfied via vault_writer's default imap:// inclusion (VAULT_INCLUDE_EMAIL=1); SAB half unchanged/still passing"
  gaps_remaining: []
  regressions: []
---

# Phase 6: Brief app Verification Report

**Phase Goal:** SAB/digest become an event-driven product plus an Obsidian projection.
**Verified:** 2026-07-11
**Status:** passed
**Re-verification:** Yes — re-verification #2, supersedes the 2026-07-06 report (status: gaps_found) after gap-closure plans 06-03 (clustering data-flow), 06-04 (vault-writer), 06-05 (test-DSN safety), 06-06 (store txn hygiene), and completed human UAT (06-UAT.md, 9/9 pass, 2026-07-11).

## Goal Achievement

### Observable Truths (ROADMAP.md Success Criteria — the contract)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1a | `brief` subscribes `verdict.ready` | ✓ VERIFIED | `apps/brief/consumer.py::run_consumer()` calls `bus.consume("verdict.ready", _handler, prefetch_count=1)`; UAT test 7 republished `verdict.ready` live and observed 4 digest files atomically rewritten |
| 1b | ...clusters via pgvector | ✓ VERIFIED (was FAILED) | `apps/brief/consumer.py` `_SELECT` (lines 61-68) and `apps/brief/main.py` `_ENRICHMENT_SQL` (lines 67-75) now `LEFT JOIN infotriage.embeddings emb ON emb.item_id = e.item_id`; `renderer.py::_rows_to_enriched_items()` (line 102) uses `r.get("embedding")` with `None` pass-through — the `[0.0]*4` default is gone (grep clean). `apps/triage/sab_html.py::cluster()` (line 283) now delegates to `_group_by_cluster_idx()` whenever `_cluster_idx` metadata is present, which `html_renderer.py::_apply_semantic_clustering()` always sets before calling `sab_html.build_html()` — the keyword-overlap fallback (`_keyword_cluster()`) is no longer reachable on the live `/sab` path. UAT tests 3 and 8 confirm live multi-item clusters (`PIR-1: 4 saker · 1 klynger`, `(3 kilder)` tags) driven by real pgvector-sourced embeddings, and that dissimilar-embedding/keyword-overlapping items do NOT merge (proving semantic, not keyword, clustering is active) |
| 1c | ...renders the SAB served at :22040 | ✓ VERIFIED | UAT test 2: `GET /sab` → 200, full HTML with CNR/CCIR sections and "Since" timestamp; UAT test 1: `GET /health` → 200 on cold start |
| 1d | ...publishes `sab.published` | ✓ VERIFIED | `consumer.py::process_verdict()` builds `SabPublished` and calls `bus.publish("sab.published", ...)`; UAT test 7 confirms the consumer's write pipeline fires end-to-end (publish itself landed after the 60s test window due to LLM-call latency — wiring is correct, timing is a documented Phase 7 ops follow-up, not a functional gap) |
| **1 (compound)** | **SC1 overall** | **✓ VERIFIED** | All 4 sub-clauses now pass |
| 2 | A vault-writer emits high-value items + the SAB as Obsidian `.md` (front-matter, body summary, `[[entity]]` wikilinks) | ✓ VERIFIED (was FAILED) | `apps/brief/vault_writer.py` exists with `write_item_obsidian()`, `write_sab_obsidian()`, `write_vault_digest()`, `extract_entities()`, `render_wikilinked()`. Wired into `consumer.py::process_verdict()` (calls `write_vault_digest()` for default/COP/CIP views after digest write) and `main.py` (`/vault` endpoint serves `render_sab_obsidian()`). Front-matter uses `contracts.to_frontmatter()` (existing codec). UAT test 4: live run wrote 24 `.md` files to `/Users/vidarbrevik/Vault/brief-outbox` including `obsidian-sab.md`; 5 per-item files round-tripped through `contracts.from_frontmatter()` |
| 3 | Email surfaces here (SAB + Obsidian), not in FreshRSS | ✓ VERIFIED (was FAILED — partial) | SAB half: unchanged and still verified (`imap://` sourced items reach the enrichment query with no source-type filter; `grep` clean for `fever()`/`fever_key()` in `apps/brief/`). Obsidian half: `vault_writer.py::write_vault_digest()` includes `imap://` items by default (`VAULT_INCLUDE_EMAIL` defaults to `"1"`; filter only excludes when explicitly `"0"`). UAT test 5: fixture test confirms both directions (included by default, excluded when `VAULT_INCLUDE_EMAIL=0`); live DB had 0 `imap://` rows (gmail-ingest is down, out of Phase 6 scope) so the live-data check was vacuous but the code path is exercised and correct |

**Score:** 3/3 roadmap success criteria fully verified (all 4 sub-clauses of SC1 pass; SC2 passes; SC3 passes as a conjunction).

### PLAN-level must-haves (06-01, 06-02, 06-03, 06-04 — R1-R6 SPEC scope)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 4 | `SabPublished` event schema on ContractEvent | ✓ VERIFIED | Unchanged from prior verification — `consumer.py` constructs and publishes it |
| 5 | `render_brief()` — CNR first, CCIR in CCIR_ORDER, cluster metadata | ✓ VERIFIED | `tests/test_brief_renderer.py` passes (re-run this session as part of full suite); a renderer regression (dropped title/score via `digest.line()`) was caught and fixed during UAT re-run 2026-07-11, with a new regression test `TestRenderBriefIncludesAllItemFields` |
| 6 | `render_list()` — score >= 8, sorted desc | ✓ VERIFIED | Unchanged, tests pass |
| 7 | `render_bluf()` — [N] citations, LLM-local, placeholder on failure | ✓ VERIFIED | Unchanged, routes through `apps.triage.triage_score.llm()` |
| 8 | Clustering is per-CCIR — never merges across sections | ✓ VERIFIED (now also live) | Unit tests pass AND UAT test 8 live-confirms CCIR-boundary respect (PIR-2 item with keyword overlap but divergent embedding stayed a singleton while PIR-1 items with similar embeddings merged) |
| 9 | `CLUSTER_THRESHOLD` env var configurable (0.0–1.0), wired to clustering call | ✓ VERIFIED (was PARTIAL) | `main.py` lines 47-49 define+validate; `renderer.py::_cluster_rows()` (line 127) accepts `threshold: float \| None = None`, no hardcoded `0.75` at call sites (only as the function's own fallback default); `main.py` passes `cluster_threshold=CLUSTER_THRESHOLD` into `build_html()` (line 131) and `run_consumer()` (line 158), which threads into `consumer.py::process_verdict(cluster_threshold=...)` → `render_brief`/`render_cluster` calls. UAT tests 6 and 9: live-confirmed threshold changes cluster count (0.0 → 5 clusters, 0.99 → 7 clusters on identical rows) |
| 10 | All SQL uses `%s` bind params (never f-strings) | ✓ VERIFIED | Unchanged — new JOINs in consumer.py/main.py also use static SQL strings with `%s` placeholders |
| 11 | Atomic file writes (`.tmp` + `os.replace`) | ✓ VERIFIED | Confirmed in `consumer.py`, `main.py::_write_atomic`, and now also `vault_writer.py` (`write_item_obsidian`, `write_sab_obsidian` both use `.tmp` + `os.replace`) |
| 12 | Concurrent SAB writes don't produce partial reads (BACKSTOP) | ✓ VERIFIED (via human UAT) | Correct atomic idiom present in code (consumer.py, main.py, vault_writer.py). UAT test 1 (cold start) and test 7 (event-driven rewrite) exercised the live `.tmp` + `os.replace` pipeline against a running server; per orchestrator context, UAT evidence is accepted as satisfying this human-verification item — no reader observed a partial file across the UAT session |
| 13 | No FreshRSS/Fever reads in apps/brief/ | ✓ VERIFIED | `grep -rn "fever(\|fever_key(" apps/brief/` → empty |
| 14 | No copied `HTML_TEMPLATE` inline HTML | ✓ VERIFIED | `HTML_TEMPLATE` still only referenced via import in `html_renderer.py` |

**Score:** 14/14 must-haves verified (11 truths above + SC1/2/3 compound = the full re-checked set from the prior gap list, all closed).

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `apps/brief/consumer.py` | verdict.ready consumer, embeddings JOIN, vault write call | ✓ VERIFIED (substantive, wired) | `_SELECT` joins `infotriage.embeddings`; calls `write_vault_digest()` for default/cop/cip views |
| `apps/brief/main.py` | FastAPI :22040 server, embeddings JOIN, `/vault` endpoint | ✓ VERIFIED | `_ENRICHMENT_SQL` joins `infotriage.embeddings`; `CLUSTER_THRESHOLD` validated and threaded through; new `/vault` route added |
| `apps/brief/renderer.py` | render_brief/list/bluf/cluster, threshold-aware clustering | ✓ VERIFIED | `_rows_to_enriched_items()` no longer defaults embedding to `[0.0]*4`; `_cluster_rows()` accepts `threshold` param |
| `apps/brief/html_renderer.py` | HTML SAB via sab_html.build_html, semantic clustering pre-computed | ✓ VERIFIED | `_apply_semantic_clustering()` normalizes pgvector JSON-string embeddings and sets `_cluster_idx` metadata consumed by `sab_html.cluster()` |
| `apps/triage/sab_html.py` | cluster() prefers precomputed semantic clusters over keyword fallback | ✓ VERIFIED (anti-pattern resolved) | `cluster()` checks for `_cluster_idx` metadata first; `_keyword_cluster()` is now unreachable on the live `/sab`/`/vault` path (only used when no embeddings exist at all, e.g. `_semantic_cluster()`'s own internal fallback) |
| `apps/brief/vault_writer.py` | Emits high-value items + SAB as Obsidian `.md` w/ wikilinks | ✓ VERIFIED (was MISSING) | New module; `write_item_obsidian`, `write_sab_obsidian`, `write_vault_digest`, `extract_entities`, `render_wikilinked` all present and tested |
| `apps/brief/clustering.py` | pgvector-sourced embeddings feed in-memory clustering | ✓ VERIFIED (data-flow now connected) | `cluster_items_in_memory()` now receives real embeddings from the JOIN; the SQL-side `cluster_items()` remains an unused alternate path (Approach A vs B — Approach B explicitly deferred in 06-03-PLAN, not a gap) |
| `tests/test_brief_renderer.py` | Renderer contract tests | ✓ VERIFIED | Passes in full-suite run; includes new regression test for the CAT_II/ROUTINE title-drop bug found+fixed during UAT |
| `tests/test_brief_clustering.py` | Clustering unit tests | ✓ VERIFIED | Passes |
| `tests/test_vault_writer.py` | Vault-writer unit tests | ✓ VERIFIED (was absent) | 8 tests, all pass |
| `tests/test_brief_consumer.py` | Consumer integration tests (new, untracked) | ✓ VERIFIED | Present, substantive, passes in full-suite run |
| `tests/test_brief_main_views.py` | View-filter tests (new, untracked) | ✓ VERIFIED | Present, substantive, passes in full-suite run |
| `tests/test_dsn_safety.py` | Regression guard against prod-DSN use in tests | ✓ VERIFIED | 2/2 pass; addresses the UAT-discovered risk that db_live fixtures could wipe production Postgres |
| `tests/test_store_txn_hygiene.py` | Idle-in-transaction regression guard | ✓ VERIFIED | 5/5 pass |
| `docker-compose.yml` | Writable vault mount + threshold/vault env vars | ✓ VERIFIED | `brief` service has `${OBSIDIAN_VAULT_PATH:-./data/obsidian}/brief-outbox:/vault/brief-outbox:rw`, `CLUSTER_THRESHOLD`, `VAULT_INCLUDE_EMAIL`, `INFOTRIAGE_VAULT_PATH` |
| `.env.example` | Documents new vault/threshold env vars | ✓ VERIFIED | `OBSIDIAN_VAULT_PATH`, `CLUSTER_THRESHOLD=0.75`, `VAULT_INCLUDE_EMAIL=1` present |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|---------------------|--------|
| `apps/brief/clustering.py::cluster_items_in_memory()` (via `renderer.py::_cluster_rows` and `html_renderer.py::_apply_semantic_clustering`) | `EnrichedItem.embedding` | `consumer.py`/`main.py` SQL `LEFT JOIN infotriage.embeddings` → `renderer.py::_rows_to_enriched_items()` → `r.get("embedding")` (no zero-vector default) | Yes — UAT tests 3 and 8 confirm live multi-item merges driven by real pgvector-stored embeddings, and CCIR/keyword-divergent singletons proving semantic discrimination | ✓ FLOWING (was DISCONNECTED) |
| `apps/brief/vault_writer.py::write_vault_digest()` | `enrichment_rows` (from consumer's live Postgres fetch) | `consumer.py::process_verdict()` passes the same `enrichment_rows`/`cop_rows`/`cip_rows` already fetched for digest rendering | Yes — UAT test 4 confirms 24 real `.md` files written from a live render, with parseable front-matter | ✓ FLOWING (was DISCONNECTED — module didn't exist) |
| `apps/brief/main.py` `/sab`, `/health`, `/vault` | enrichment rows | `infotriage.enrichment JOIN infotriage.articles LEFT JOIN infotriage.embeddings` | Yes — live query, live-verified via UAT | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full pytest suite (Phase 6 relevant files) | `pytest tests/test_brief_clustering.py tests/test_brief_renderer.py tests/test_vault_writer.py tests/test_brief_consumer.py tests/test_brief_main_views.py -q` | 68 passed | ✓ PASS |
| Full workspace test suite (single run, per verification constraints) | `pytest -q` | 292 passed, 1 failed, 32 skipped | ⚠️ 1 failure — `test_bus_consume.py::test_consume_delivers_message`, a pre-existing RabbitMQ live-consumer contention flake documented as unrelated in both 06-05-SUMMARY.md and 06-06-SUMMARY.md; not in `apps/brief/` scope |
| No `[0.0]*4` embedding default | `grep -n 'embedding=\[0\.0\]' apps/brief/*.py` | empty | ✓ PASS |
| No hardcoded `threshold=0.75` at renderer call sites | `grep -n 'threshold=0.75' apps/brief/renderer.py` | empty | ✓ PASS |
| No fever()/HTML_TEMPLATE copy anti-patterns | `grep -rn "fever(\|fever_key("` / `grep -n "HTML_TEMPLATE"` in `apps/brief/` | empty / import-only | ✓ PASS |
| No unresolved debt markers (TBD/FIXME/XXX) | `grep -n -E "TBD|FIXME|XXX" apps/brief/*.py apps/triage/sab_html.py` | empty | ✓ PASS |
| sab_html.py keyword-overlap anti-pattern resolved | `grep -n "def cluster\b" apps/triage/sab_html.py` + read | `cluster()` now checks `_cluster_idx` first, falls back only when embeddings truly absent | ✓ PASS |

### Requirements Coverage

Phase 6's `requirements:` field (both in ROADMAP.md line 201 and the newer 06-05/06-06 PLAN frontmatter) reads `spec §Reading-surface routing` — a SPEC-local section reference into `06-SPEC.md`, not a `.planning/REQUIREMENTS.md` registry ID (`D-`/`C-`/`P-`/`A-`/`PR-`/`DI-`/`N-`/`NF-`). This is the project's established convention (also flagged, and explicitly accepted, in the 2026-07-06 verification and in 06-05-SUMMARY.md / 06-06-SUMMARY.md's own "Requirements" sections: "spec section, not a REQUIREMENTS.md ID — no `requirements mark-complete` applicable"). No `.planning/REQUIREMENTS.md` entries map to Phase 6, so there are no orphaned requirements to report.

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|--------------|--------|----------|
| R1 | 06-01-PLAN | Event-driven consumer | ✓ SATISFIED | Unchanged |
| R2 | 06-01-PLAN | SAB markdown renderer | ✓ SATISFIED | Unchanged (regression fixed + re-tested) |
| R3 | (SUMMARY/SPEC only) | SAB HTML renderer / serving | ✓ SATISFIED | Unchanged |
| R4 | 06-02-PLAN | pgvector semantic clustering | ✓ SATISFIED (was BLOCKED) | Now functions against live data — see SC1b above |
| R5 | (SUMMARY/SPEC only) | SAB event/serving contract | ✓ SATISFIED | Unchanged |
| R6 | 06-04-PLAN | Obsidian vault-writer | ✓ SATISFIED (was not planned/built) | `vault_writer.py` built and wired |
| SC1b | 06-03-PLAN | Clustering data-flow fix | ✓ SATISFIED | See SC1b above |
| "spec §Reading-surface routing" | 06-05-PLAN, 06-06-PLAN | Test-DSN safety + store txn hygiene (UAT-discovered gap-closure) | ✓ SATISFIED | `tests/test_dsn_safety.py`, `tests/test_store_txn_hygiene.py` both pass; addresses a real production-Postgres-wipe risk discovered during UAT |
| ADR-004, ADR-006, ADR-007 | 06-01-PLAN | Local-LLM-only, event schema conventions | ✓ SATISFIED | Unchanged |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `apps/brief/clustering.py` | 91 | `cluster_items()` (pgvector SQL-query clustering path) remains unused outside its own module and a signature test | ℹ️ Info | Not a blocker — Approach B was explicitly deferred to a future plan in 06-03-PLAN's Decision Log; Approach A (JOIN + in-memory clustering on pgvector-sourced embeddings) satisfies SC1b as written and is live-verified |
| `tests/integration/test_clustering_integration.py` | — | Hardcoded DSN `127.0.0.1:5432` with no reachability skip guard | ℹ️ Info | Pre-existing, logged in `deferred-items.md` from 06-05; does not affect production code paths |
| `tests/test_bus_consume.py` | 69 | `test_consume_delivers_message` fails against live RabbitMQ (contention) | ℹ️ Info | Pre-existing/known-flaky per 06-05-SUMMARY.md and 06-06-SUMMARY.md; outside `apps/brief/` scope, not introduced by Phase 6 gap-closure work |

No 🛑 Blocker or ⚠️ Warning-level anti-patterns found in `apps/brief/` or `apps/triage/sab_html.py`.

### Human Verification Required

None. The one remaining human-verification item from the prior report (concurrent SAB write safety) was resolved via completed human UAT (06-UAT.md, tests 1 and 7, status: complete, 9/9 passed) — per the launching agent's explicit direction, this UAT evidence is accepted as satisfying that check.

### Gaps Summary

All three gaps from the 2026-07-06 verification are closed:

1. **Semantic clustering now engages in production.** `consumer.py` and `main.py` join `infotriage.embeddings`; the `[0.0]*4` fallback is removed; `CLUSTER_THRESHOLD` is validated and threaded end-to-end into both the markdown and HTML render paths; `sab_html.py`'s keyword-overlap fallback is no longer reachable on the live path. Live UAT (tests 3, 6, 8, 9) confirms multi-item semantic clusters, CCIR-boundary respect, and threshold-driven cluster-count changes on real data.
2. **The Obsidian vault-writer now exists and is wired.** `apps/brief/vault_writer.py` is called from `consumer.py::process_verdict()` after every digest render (default/COP/CIP views) and exposed via `main.py`'s new `/vault` endpoint. Live UAT (test 4) confirms 24 real `.md` files with codec-parseable front-matter.
3. **Email now surfaces in both SAB and Obsidian.** The SAB half was already working; the Obsidian half is now satisfied by `vault_writer.py`'s default-inclusion of `imap://`-sourced items, confirmed by a UAT fixture test (live DB currently has 0 email rows since gmail-ingest is out of Phase 6 scope, so the live check was vacuous but the code path is exercised and correct).

Two additional gap-closure plans (06-05, 06-06) were executed beyond the original 3 gaps, closing a UAT-discovered production-safety issue (db_live tests could wipe the production Postgres instance) and a connection-hygiene issue (idle-in-transaction leaks) — both verified with passing regression tests.

Phase 6's stated goal — "SAB/digest become an event-driven product plus an Obsidian projection" — is now achieved and codebase-verified, corroborated by completed human UAT (9/9 pass).

---

_Verified: 2026-07-11_
_Verifier: Claude (gsd-verifier)_
