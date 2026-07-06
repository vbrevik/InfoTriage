---
phase: 06-brief-app
verified: 2026-07-06T00:00:00Z
status: gaps_found
score: 1/3 roadmap must-haves verified (1 partial/failed, 2 failed)
behavior_unverified: 1
overrides_applied: 0
gaps:
  - truth: "brief (:22040) clusters via pgvector"
    status: failed
    reason: >
      The production data path never populates the `embedding` field consumed by clustering.
      Neither consumer.py's enrichment SELECT nor main.py's enrichment SELECT joins
      infotriage.embeddings, so every row reaching renderer.py's _rows_to_enriched_items()
      gets embedding=[0.0,0.0,0.0,0.0] (the dict.get default). _cosine_distance() returns 1.0
      for any zero vector (by its own documented behavior), which is always greater than
      max_dist=0.25 at the default threshold (0.75) — so no two items are ever merged.
      Semantic clustering is present in code and unit-tested, but does not engage on any
      real request. The real Postgres-querying cluster_items() function (which does fetch
      infotriage.embeddings via SQL) is dead code — never called from renderer.py, consumer.py,
      or main.py; the only place it's referenced outside its own module is a test that checks
      its default parameter value, never its query behavior.
    artifacts:
      - path: "apps/brief/renderer.py"
        issue: "_rows_to_enriched_items() defaults embedding to [0.0]*4 (line 119); _cluster_rows() calls cluster_items_in_memory(), never the pgvector-backed cluster_items()"
      - path: "apps/brief/consumer.py"
        issue: "_SELECT (lines 57-62) does not join infotriage.embeddings — no embedding column fetched"
      - path: "apps/brief/main.py"
        issue: "_ENRICHMENT_SQL (lines 48-54) does not join infotriage.embeddings — no embedding column fetched"
      - path: "apps/brief/clustering.py"
        issue: "cluster_items() (the real pgvector query path) exists but has zero call sites outside its own file and a signature-only test"
    missing:
      - "Wire consumer.py/main.py's enrichment fetch to join infotriage.embeddings (or call clustering.cluster_items() against the live store instead of the in-memory fallback with hollow data)"
      - "A live/integration test that clusters two genuinely-similar real enrichment rows and asserts they merge (the current test suite only exercises cluster_items_in_memory() with hand-authored embedding vectors, never through the actual DB-fetch → cluster path)"
    live_evidence: >
      Live-rendered data/digests/brief.md (fetched from the running infotriage-brief container,
      Up and healthy) shows a FFIR-3 section with 3 distinct items and zero "(N kilder: ...)"
      multi-source cluster tags anywhere in the file — consistent with every item landing in
      its own singleton cluster, as the code's zero-vector fallback predicts.
  - truth: "A vault-writer emits high-value items + the SAB as Obsidian .md (front-matter via codec; body summary; [[entity]] wikilinks)"
    status: failed
    reason: >
      No vault-writer module exists anywhere in the codebase. apps/ingest-obsidian/ is a
      READ-ONLY ingestion adapter from Phase 4 (articles-inbox → Item), the opposite
      direction of what SC2 requires. 06-SPEC.md's own Boundaries section explicitly moved
      this out of scope ("Obsidian vault-writer — a separate plan item; this phase only
      writes to data/digests/") during the initial 2026-07-04 interview, but that scope cut
      was never reflected back into ROADMAP.md's Phase 6 success criteria or deferred
      explicitly to a specific later phase — ROADMAP.md line 28 still lists Phase 6 as
      "[x] ... SAB renderer + Obsidian vault-writer" and the phase was marked complete
      (commit d0ab4ac) with this criterion unmet.
    artifacts:
      - path: "apps/brief/"
        issue: "No vault_writer.py, obsidian_writer.py, or equivalent module; no front-matter codec output, no [[entity]] wikilink generation anywhere in apps/brief/"
    missing:
      - "A vault-writer module that projects high-value enrichment items + the SAB into Obsidian .md files (front-matter via codec, body summary, [[entity]] wikilinks)"
      - "Either build it in this phase, or formally amend ROADMAP.md Phase 6 to drop this criterion and route it to a named later phase with matching goal text (checked against Phase 8/9/10/11/12 — none of their goals or success criteria specifically cover 'SAB → Obsidian .md projection'; Phase 8 covers the entity-link graph, Phase 10 covers a standing auto-wiki — neither is this projection)"
  - truth: "Email surfaces here (SAB + Obsidian), not in FreshRSS"
    status: failed
    reason: >
      SAB half is VERIFIED: live data/digests/brief.md contains Gmail/IMAP-sourced items
      (imap:// URLs) in the FFIR-3 section, and 06-SPEC.md confirms FreshRSS/Fever
      integration is fully retired from apps/brief/ (grep clean for fever()/fever_key()).
      Obsidian half is FAILED: since no vault-writer exists (see gap above), email items
      cannot surface in Obsidian at all. The truth is a conjunction (SAB AND Obsidian) so
      it fails as a whole.
    artifacts:
      - path: "apps/brief/"
        issue: "Same missing vault-writer as SC2 — no Obsidian output path for email-sourced items"
    missing:
      - "Same as SC2 — vault-writer needed before email can surface in Obsidian"
behavior_unverified_items:
  - truth: "Concurrent SAB writes via atomic .tmp + os.replace pattern do not produce partial reads (06-01-PLAN BACKSTOP)"
    test: "Run N concurrent writers to the same digest file (or N concurrent GET /sab requests during a render) and assert no reader ever observes a truncated/partial file"
    expected: "Every reader sees either the old complete file or the new complete file, never a partial write"
    why_human: "The .tmp + os.replace pattern is present in both consumer.py and main.py (code inspection confirms the correct idiom), but no test in the suite exercises real concurrent access — this is a race-condition property that grep/static analysis cannot prove or disprove; it was explicitly flagged in 06-01-PLAN.md as 'non-inferable, needs held-out/concurrency test'"
---

# Phase 6: Brief app Verification Report

**Phase Goal:** SAB/digest become an event-driven product plus an Obsidian projection.
**Verified:** 2026-07-06
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (ROADMAP.md Success Criteria — the contract)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1a | `brief` subscribes `verdict.ready` | ✓ VERIFIED | `apps/brief/consumer.py` `run_consumer()` calls `bus.consume("verdict.ready", _handler, prefetch_count=1)`; live-verified previously (republished verdict.ready → digests rewritten); orchestrator context confirms container `infotriage-brief` Up 21h healthy |
| 1b | ...clusters via pgvector | ✗ FAILED | Production fetch (consumer.py `_SELECT`, main.py `_ENRICHMENT_SQL`) never joins `infotriage.embeddings`; every row's embedding defaults to `[0.0]*4` in `renderer.py:119`; `_cosine_distance` returns 1.0 for zero vectors (max distance), always > `max_dist=0.25` at threshold 0.75 — clustering never merges. Live `data/digests/brief.md` FFIR-3 section (3 items) has zero "(N kilder: ...)" cluster tags. The real pgvector-querying `cluster_items()` is dead code (0 call sites outside its own module + a signature-only test) |
| 1c | ...renders the SAB served at :22040 | ✓ VERIFIED | `curl 127.0.0.1:22040/health` → 200, `curl 127.0.0.1:22040/sab` → 200; `main.py` serves via FastAPI on 22040; container healthy |
| 1d | ...publishes `sab.published` | ✓ VERIFIED | `consumer.py` `process_verdict()` builds `SabPublished` and calls `bus.publish("sab.published", ...)`; previously live-verified landing in `q.notify` |
| **1 (compound)** | **SC1 overall** | **✗ FAILED** | Compound AND — fails on clause 1b |
| 2 | A vault-writer emits high-value items + the SAB as Obsidian `.md` (front-matter, body summary, `[[entity]]` wikilinks) | ✗ FAILED | No such module exists anywhere in the repo (`find -iname "*vault*"`, `find -iname "*obsidian*"` → only `apps/ingest-obsidian/` which is a Phase-4 read-only ingestion adapter, the opposite direction). `06-SPEC.md` explicitly descoped this ("a separate plan item") without a corresponding ROADMAP.md update |
| 3 | Email surfaces here (SAB + Obsidian), not in FreshRSS | ✗ FAILED (partial) | SAB half ✓ verified (live `brief.md` contains `imap://` sourced items; grep clean for `fever()`/`fever_key()` in `apps/brief/`); Obsidian half ✗ impossible — no vault-writer exists |

**Score:** 1/3 roadmap success criteria fully verified (2 of 4 sub-clauses of SC1 pass; SC2 fails outright; SC3 half-passes but fails as a conjunction). 1 behavior-dependent truth present-but-unverified.

### PLAN-level must-haves (06-01, 06-02 — narrower R1-R5 SPEC scope)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 4 | `SabPublished` event schema on ContractEvent | ✓ VERIFIED | Pre-existing richer schema reused (`pub_ts`, `snapshot_day`, `ccir_topics`, `bluf_by_topic`, `item_refs`, `total_keep`, `since_ts`); `consumer.py` constructs and publishes it |
| 5 | `render_brief()` — CNR first, CCIR in CCIR_ORDER, cluster metadata | ✓ VERIFIED | `tests/test_brief_renderer.py` 23/23 pass (`test_cnr_i_appears_first`, `test_ccir_order_enforced`); code present in `renderer.py` |
| 6 | `render_list()` — score >= 8, sorted desc | ✓ VERIFIED | `tests/test_brief_renderer.py::test_score_below_threshold_excluded`, `test_sorted_descending` pass |
| 7 | `render_bluf()` — [N] citations, LLM-local, placeholder on failure | ✓ VERIFIED | `test_prompt_contains_citation_instructions`, `test_placeholder_on_connection_error` pass; routes through `apps.triage.triage_score.llm()` (ADR-004, no cloud client present) |
| 8 | Clustering is per-CCIR — never merges across sections | ✓ VERIFIED (unit-test only, not live) | `tests/test_brief_clustering.py::TestCcirBoundary` passes (property-based, in-memory fabricated embeddings) — but see gap #1b: this guarantee is untested against the live data-flow, where clustering never merges anything regardless of CCIR |
| 9 | `CLUSTER_THRESHOLD` env var configurable (0.0–1.0) | ⚠️ PARTIAL | `main.py` defines and range-validates `CLUSTER_THRESHOLD` (lines 44-46), but `renderer.py::_cluster_rows()` hardcodes `threshold=0.75` (line 150) and never receives `main.py`'s `CLUSTER_THRESHOLD` value — the env var is validated but not wired to the actual clustering call |
| 10 | All SQL uses `%s` bind params (never f-strings) | ✓ VERIFIED | `clustering.py` queries use `%s`/`ANY(%s)` throughout; `consumer.py`/`main.py` SELECTs use `%s` |
| 11 | Atomic file writes (`.tmp` + `os.replace`) | ✓ VERIFIED (code present) | Confirmed in `consumer.py` (lines 114-118) and `main.py` (`_write_atomic`, lines 81-86) |
| 12 | Concurrent SAB writes don't produce partial reads (BACKSTOP) | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | Correct atomic idiom present in code; no test exercises actual concurrent access — routed to human verification |
| 13 | No FreshRSS/Fever reads in apps/brief/ | ✓ VERIFIED | `grep -rn "fever(\|fever_key(" apps/brief/` → empty |
| 14 | No copied `HTML_TEMPLATE` inline HTML | ✓ VERIFIED | `HTML_TEMPLATE` appears only in a docstring comment in `renderer.py`; actual import is in `html_renderer.py` |

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `libs/contracts/src/contracts/_events.py` (SabPublished) | Event schema | ✓ VERIFIED | Pre-existing, reused |
| `apps/brief/renderer.py` | render_brief/list/bluf/cluster | ✓ VERIFIED (substantive, wired) | All 4 functions present and tested |
| `apps/brief/clustering.py` | pgvector HNSW clustering | ⚠️ HOLLOW — wired but data disconnected | Module exists, `cluster_items_in_memory()` is called by renderer, but never receives real embeddings in production (see gap #1b). `cluster_items()` (the real DB-backed path) is orphaned |
| `apps/brief/consumer.py` | verdict.ready consumer | ✓ VERIFIED | Subscribes, renders, publishes; live-verified |
| `apps/brief/main.py` | FastAPI :22040 server | ✓ VERIFIED | /health, /sab, /sab?window=, /sab?mode=list all present; live 200s confirmed |
| `apps/brief/html_renderer.py` | HTML SAB via sab_html.build_html | ✓ VERIFIED | Imports (not copies) `HTML_TEMPLATE` |
| Obsidian vault-writer | Emits high-value items + SAB as `.md` w/ wikilinks | ✗ MISSING | No such file/module exists anywhere |
| `tests/test_brief_renderer.py` | 23 contract tests | ✓ VERIFIED | 23/23 pass |
| `tests/test_brief_clustering.py` | 11 unit tests | ✓ VERIFIED (as unit tests) | 11/11 pass (re-run this session); tests exclusively exercise `cluster_items_in_memory()`/`_cosine_distance()` with hand-authored embeddings — they do not exercise the actual DB-fetch path that feeds production, so passing does not establish that clustering works live |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|---------------------|--------|
| `apps/brief/clustering.py` `cluster_items_in_memory()` (as called from `renderer.py::_cluster_rows`) | `EnrichedItem.embedding` | `renderer.py::_rows_to_enriched_items()` → `r.get("embedding", [0.0]*4)` | No — `embedding` key is never present in rows fetched by `consumer.py`/`main.py` SQL (no join to `infotriage.embeddings`), so the default `[0.0,0.0,0.0,0.0]` is used for every item | ✗ DISCONNECTED |
| `apps/brief/main.py` `/sab`, `/health` | enrichment rows | `infotriage.enrichment JOIN infotriage.articles` | Yes — live query, live-verified 200 responses with real content | ✓ FLOWING |
| `apps/brief/consumer.py` digest writes | enrichment rows | same JOIN as above | Yes | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Brief container healthy and serving | `docker ps --filter name=infotriage-brief` | `Up 3 minutes (healthy)` | ✓ PASS |
| `/health` returns 200 | `curl -o /dev/null -w "%{http_code}" http://127.0.0.1:22040/health` | `200` | ✓ PASS |
| `/sab` returns 200 | `curl -o /dev/null -w "%{http_code}" http://127.0.0.1:22040/sab` | `200` | ✓ PASS |
| Clustering unit tests pass | `pytest tests/test_brief_clustering.py -q` | `11 passed` | ✓ PASS (but see data-flow gap — tests use fabricated embeddings, not the live path) |
| Live SAB shows any multi-source cluster ("N kilder") | `grep -c "kilder" data/digests/brief.md` | `0` matches, 3-item FFIR-3 section with no merges | ✗ FAIL — confirms clustering does not engage live |
| No fever()/HTML_TEMPLATE copy anti-patterns | `grep -rn "fever(\|fever_key("` / `grep -n "HTML_TEMPLATE"` in `apps/brief/` | empty / docstring-only | ✓ PASS |
| No debt markers (TBD/FIXME/XXX/TODO/HACK/PLACEHOLDER) | `grep -n -E "TBD|FIXME|XXX|TODO|HACK|PLACEHOLDER" apps/brief/*.py` | no matches | ✓ PASS |

### Requirements Coverage

SPEC-local requirement IDs (R1-R5, from `06-SPEC.md §Requirements`) do not correspond to entries in the global `.planning/REQUIREMENTS.md` registry (which uses `D-`/`C-`/`P-`/`A-`/`PR-`/`DI-`/`N-`/`NF-` prefixes and has no "Reading-surface routing" section) — this is the project's established convention of phase-scoped SPEC requirement numbering, not an omission.

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|--------------|--------|----------|
| R1 | 06-01-PLAN (frontmatter) | Event-driven consumer | ✓ SATISFIED | `consumer.py` live-verified |
| R2 | 06-01-PLAN (frontmatter) | SAB markdown renderer | ✓ SATISFIED | `renderer.py`, 23/23 tests |
| R3 | not in any PLAN frontmatter | SAB HTML renderer / serving | ✓ SATISFIED (evidenced in SUMMARY/SPEC, not declared in a plan's `requirements:` field) | `html_renderer.py`, `main.py`, live 200s |
| R4 | 06-02-PLAN (body text only — no `requirements:` frontmatter field) | pgvector semantic clustering | ✗ BLOCKED | Code exists but does not function against live data (gap #1b above) — SPEC.md's own "✅ Delivered" claim for R4 is not supported by the production data-flow trace |
| R5 | not in any PLAN frontmatter | SAB event/serving contract | ✓ SATISFIED (evidenced, not declared) | `SabPublished` publish confirmed live |
| ADR-004, ADR-006, ADR-007 | 06-01-PLAN (frontmatter) | Local-LLM-only, event schema conventions | ✓ SATISFIED | grep clean for cloud LLM clients; `SabPublished` follows existing pattern |

**Note:** `06-02-PLAN.md` has no `requirements:` frontmatter field at all (R4 is only named in prose/title) — a minor traceability gap, not a blocker, since R4's identity is unambiguous from context.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `apps/brief/renderer.py` | 119 | `r.get("embedding", [0.0] * 4)` — silent hardcoded-empty fallback flows into rendering | 🛑 Blocker | This is the root cause of gap #1b: a stub-shaped default silently substitutes for real data with no error, log, or warning when the key is absent — production always hits this path |
| `apps/brief/renderer.py` | 150 | `cluster_items_in_memory(items, threshold=0.75)` — hardcoded threshold ignoring `CLUSTER_THRESHOLD` | ⚠️ Warning | `main.py`'s env var is validated but never reaches the actual clustering call (must-have #9 above) |

### Human Verification Required

### 1. Concurrent SAB write safety

**Test:** Fire N concurrent `GET /sab` requests (or trigger N rapid `verdict.ready` events) while the digest files are mid-render, and inspect whether any reader observes a truncated/partial `brief.md`/`sab.html`.
**Expected:** Every reader sees either the fully-old or fully-new file, never a partial write.
**Why human:** The `.tmp` + `os.replace` idiom is present and correct by inspection, but no automated test exercises real concurrent access; this was explicitly flagged as a "BACKSTOP (non-inferable)" item in `06-01-PLAN.md`'s must-haves and cannot be resolved by static analysis.

### Gaps Summary

Phase 6 delivered a solid, live-verified event-driven SAB pipeline (subscribe → render → serve → publish all work end-to-end against real Postgres/RabbitMQ), but the phase's stated goal — "SAB/digest become an event-driven product **plus an Obsidian projection**" — is not achieved:

1. **Semantic clustering is non-functional in production** (SC1's "clusters via pgvector" clause). The code and unit tests look complete and were reported as "✅ Delivered" in `06-SPEC.md`, but the production data path never attaches real embeddings to enrichment rows before clustering, so every item silently becomes a singleton cluster. This is a textbook Level-4 data-flow disconnect: the artifact exists, is substantive, is wired into the render call graph, but the value flowing through it is always the hardcoded-empty fallback. Live evidence (the running container's own `brief.md`) confirms zero clusters have ever merged.
2. **The Obsidian vault-writer required by SC2 does not exist at all.** `06-SPEC.md` unilaterally descoped it during the initial interview ("a separate plan item") without a corresponding ROADMAP.md amendment or an explicit, evidenced deferral to a specific later phase — Phase 8/9/10/11/12's goals cover an entity-link graph, RAG recall, a standing auto-wiki, SOCMINT collection, and push alerting respectively, none of which is "vault-writer emits high-value items + the SAB as Obsidian .md."
3. **SC3 (email surfaces in SAB + Obsidian) is half-true.** Email items do reach the SAB (live-confirmed via `imap://` URLs in `brief.md`), but the Obsidian half is impossible without item 2.

None of these are deferred to a later phase with clear, specific roadmap evidence (Step 9b check performed — no match found), so all three are retained as active gaps rather than deferred items. Phase 6 should not be treated as fully complete until (a) clustering is wired to real embedding data and demonstrated to merge at least one live cluster, and (b) either a vault-writer is built or ROADMAP.md is explicitly amended to move SC2/the Obsidian half of SC3 to a named phase.

---

_Verified: 2026-07-06_
_Verifier: Claude (gsd-verifier)_
