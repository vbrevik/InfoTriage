---
phase: 08-entity-resolution
verified: 2026-08-01T14:00:00Z
status: passed
score: 8/8 must-haves verified
behavior_unverified: 0
overrides_applied: 0
re_verification: false  # retroactive backfill — Phase 8 completed and UAT-closed before a VERIFICATION.md was ever written
warnings:
  - id: W-1
    summary: "Deployed `infotriage-brief` image (created 2026-07-24) predates `a2db924` (2026-07-25) and `979467d` (2026-08-01), so the live vault projection is stale relative to HEAD"
    severity: medium
    blocking: false
    remediation: "docker compose build brief && docker compose up -d brief"
  - id: W-2
    summary: "Live-corpus quality: 98% of entities carry lang='und', 52% type MISC, 16/1138 demonstrably cross-language links, 0 cross-lang `name_norm` collisions"
    severity: low
    blocking: false
    remediation: "Upstream language-detector fix (not a Phase 8 deliverable); already carried forward in 08-VALIDATION.md audits 2026-07-24 / 2026-07-31 and 08-UAT.md Tests 1+2"
  - id: I-1
    summary: "`apps/triage/entities.py:31` and 3 store files cite `.planning/phases/999.3-.../999.3-VERDICT.md`, but that directory now lives under `.planning/phases/_archived/`"
    severity: info
    blocking: false
---

# Phase 8: Entity Resolution — Verification Report

**Phase Goal:** Cross-modality entity tracking as Postgres truth; Obsidian graph as a projection.

**Verified:** 2026-08-01 (retroactive backfill — Phase 8 was executed across Waves 1–6, validated, and UAT-closed 5/5 before a VERIFICATION.md was ever produced; this file closes that artifact gap, in the same manner as `07-VERIFICATION.md` closed Phase 7's)
**Status:** PASSED — 8/8 must-haves verified, 2 non-blocking warnings + 1 info note
**Re-verification:** No — initial (retroactive) verification

---

## Goal Achievement

### Observable Truths — ROADMAP Success Criteria

| # | Truth (from `.planning/ROADMAP.md` §Phase 8) | Status | Evidence |
|---|------|--------|----------|
| SC-1 | `entities` + `entity_links` populated via extraction + pgvector linking (cross-modality, cross-language) | ✓ VERIFIED | Schema: `libs/store/sql/003-vectors.sql:7-22` declares both tables. Extraction: `apps/triage/entities.py:96 extract_entities()` (qwen36 LLM NER) → `:188 embed_entity_name()` (mE5-large) → `:208 _find_or_create_entity()` → `:274 resolve_entities_async()`. pgvector linking: `apps/triage/entities.py:235` calls `store.find_similar_entity(embedding, LINK_THRESHOLD)`; `libs/store/src/store/_postgres.py:531-559` implements it with the HNSW cosine index (`003-vectors.sql:43-45`). **Live Postgres (queried this session, `docker exec infotriage-postgres psql`): 640 entities / 1138 entity_links, 640 entities carry a non-NULL embedding, 16 links where `entity_links.lang != entities.lang` (cross-language).** Cross-modality confirmed live: entity links resolve to articles from ≥2 source modalities — 565 distinct entities on `imap:`-scheme (email) items and 57 on `https:`-scheme (web/RSS/YouTube) items. |
| SC-2 | The Obsidian graph is generated as a projection of this truth, not the system of record | ✓ VERIFIED | `apps/brief/vault_writer.py:364 write_entity_graph_from_store()` queries `store.get_active_entities(limit=ENTITY_GRAPH_ACTIVE_LIMIT)` (`:379`) and writes `Entity Graph.md`; `:388 write_vault_digest()` accepts the `store` and drives it. `apps/brief/consumer.py:98-104 _attach_entities()` calls `store.get_entity_links(item_id)` per row — the vault reads from Postgres, never the reverse. The old heuristic is a deprecation stub only (`vault_writer.py:31-49`, raises `DeprecationWarning`, returns `[]` without `known_topics`). **Live artifact exists:** `~/Vault/brief-outbox/Entity Graph.md`, 62 KB / 3001 lines, written 2026-08-01 12:00, carrying the store-only fields (`- **CCIRs:**`, `- **Seen:**`) that only `render_entity_graph_from_store` emits. No write path from vault → Postgres exists. See **W-1**: the deployed renderer is one image-build behind HEAD. |

**Score:** 2/2 ROADMAP success criteria verified.

### Observable Truths — PLAN must_haves (`08-PLAN.md` frontmatter)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `infotriage.entities` has `id, name, name_norm, lang, type, embedding vector(1024)` (ADR-006) | ✓ VERIFIED | `libs/store/sql/003-vectors.sql:7-14` — exactly those 6 columns, `embedding vector(1024)` (D-05a locked embedder contract). `uk_entities_name_lang` unique index on `(name_norm, lang)` at `:34-35` makes `put_entity` upserts idempotent. |
| 2 | `infotriage.entity_links` has `id, entity_id FK, item_id FK, mention, lang` (ADR-006) | ✓ VERIFIED | `003-vectors.sql:16-22` — `entity_id INT REFERENCES infotriage.entities(id)`, `item_id TEXT REFERENCES infotriage.articles(id)`, plus `mention`/`lang`. |
| 3 | Entity linking uses mE5-large vectors and a re-validated cosine threshold (backlog 999.3) | ✓ VERIFIED | `apps/triage/entities.py:33` — `LINK_THRESHOLD = 0.92`, matching the validated recommendation. Defaults agree across all three store layers: `_protocol.py:191`, `_postgres.py:534`, `_inmemory.py:248` each declare `threshold: float = 0.92  # mE5-large validated T*`. Source of the number: `.planning/phases/_archived/999.3-.../999.3-VERDICT.md:5` — "Recommended `LINK_THRESHOLD`: **0.9200**", produced by `scripts/validate_entity_threshold.py` from real offline mE5-large vectors. The verdict is candid that this is a control-separation-driven pick (`max_distinct=0.9151 < T*=0.9200`, `min_same=0.9169 < T*` — the merge bar is missed), i.e. tuned to avoid false merges at the cost of recall. That trade-off explains W-2's low observed merge rate and is the intended, documented behavior. |
| 4 | Obsidian files are a projection; Postgres is the system of record (ADR-006) | ✓ VERIFIED | Same evidence as SC-2. Also satisfies PLAN prohibition #2. |
| 5 | NER failures are logged but never block `verdict.ready` publication (R5) | ✓ VERIFIED (behavioral) | `apps/triage/worker.py:293-321`: entity resolution runs after `store.put_enrichment` (`:271`) / `put_embedding` (`:272`) and before `bus.publish("verdict.ready", ...)` (`:339`), wrapped in `asyncio.wait_for(..., timeout=_ENTITY_NER_TIMEOUT)` where the timeout is env-tunable (`:298`, default `15`s). Both `asyncio.TimeoutError` (`:314`) and bare `Exception` (`:320`) are caught and logged at WARNING; control falls through to the unconditional publish. This is a cancellation/cleanup invariant, so presence alone is insufficient — **named behavioral tests re-run this session:** `pytest tests/test_triage_worker.py -k entity -q` → **3 passed, 12 deselected in 0.20s** (`test_entity_resolution_links_entities`, `test_entity_resolution_failure_does_not_block_verdict`, `test_entity_resolution_timeout_does_not_block_verdict`). Closes threat T-08-03. |
| 6 | Re-processing the same `item_id` updates (not duplicates) `entity_links` (R4) | ✓ VERIFIED (behavioral) | `003-vectors.sql:38-39` `uk_entity_links_entity_item_mention` unique index on `(entity_id, item_id, mention)`; `PostgresStore.link_entity()` (`_postgres.py:561`) uses `INSERT ... ON CONFLICT DO NOTHING` against it. **Named behavioral test re-run this session:** `pytest tests/test_store_entities.py -k "cross_language or get_all_entities or idempotent" -q` → **4 passed, 5 skipped, 20 deselected**. The 5 skips are the `db_live` parametrizations (`INFOTRIAGE_TEST_DSN` unreachable from this shell); those same rows were green in the 08-VALIDATION.md audits of 2026-07-24 and 2026-07-31 with a live DSN, and again in the 08-UAT closeout's 29/29 db_live variants (STATE.md line 5). Closes threat T-08-02. |

**Score:** 6/6 plan-level must-have truths verified. Combined and de-duplicated with the 2 ROADMAP criteria (PLAN truth 4 restates SC-2): **8/8 unique must-haves verified, 0 behavior-unverified.**

### Prohibitions (`08-PLAN.md` must_haves.prohibitions)

| # | Prohibition (MUST NOT) | Status | Evidence |
|---|---|---|---|
| P-1 | MUST NOT use cloud LLM or embedding for entity extraction/vectors (ADR-004) | ✓ VERIFIED (not violated) | `grep -nE "requests\|httpx\|urllib\|http://\|https://" apps/triage/entities.py` → **no matches**; the module takes `chat_fn`/`embed_fn` by injection only. The worker binds them to local transports: `apps/triage/worker.py:147` defaults `embed=get_embedding, ner_chat=llm`, and `get_embedding` (`:90-95`) posts to `LLM_BASE_URL` with a `http://127.0.0.1:8000/v1` default (local oMLX). Corroborated by `08-SECURITY.md` T-08-01 (status `closed`). |
| P-2 | MUST NOT make Obsidian the system of record for entities | ✓ VERIFIED (not violated) | Same evidence as SC-2 — the projection is one-way, store → vault. |

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `libs/store/sql/003-vectors.sql` | entities + entity_links tables, unique indexes, HNSW | ✓ VERIFIED | Both tables + `uk_entities_name_lang` + `uk_entity_links_entity_item_mention` + `idx_entities_embedding_hnsw` (m=16, ef_construction=64 per D-05b). All statements `IF NOT EXISTS` — `init_schema()` stays idempotent. |
| `libs/store/src/store/_protocol.py` | entity method signatures | ✓ VERIFIED | 8 methods declared (`:164-239`): `put_entity`, `get_entity`, `get_entity_by_name_norm`, `find_similar_entity`, `link_entity`, `get_entity_links`, `get_all_entities`, `get_active_entities`. |
| `libs/store/src/store/_postgres.py` | Postgres implementations | ✓ VERIFIED | All 8 present (`:451-642`); `find_similar_entity` at `:531` with the 0.92 default and the `dist < (1.0 - threshold)` cosine conversion at `:554`. |
| `libs/store/src/store/_inmemory.py` | InMemory implementations | ✓ VERIFIED | All 8 present (`:193-328`), same 0.92 default at `:248` — keeps worker unit tests off live pgvector. |
| `apps/triage/entities.py` | LLM NER + embedding + linking | ✓ VERIFIED | `extract_entities` (`:96`), `_parse_entities` (`:127`, markdown-fence tolerant, empty list on malformed JSON), `normalize_name` (`:172`), `embed_entity_name` (`:188`), `_find_or_create_entity` (`:208`), `resolve_entities` (`:251`), `resolve_entities_async` (`:274`). Also carries the post-Wave-6 noise filter (`_noise_denylist` `:56`, `is_noise_entity` `:67`, added in `a2db924`). |
| `apps/triage/worker.py` | worker integration, best-effort | ✓ VERIFIED | `from entities import resolve_entities_async` (`:29`); call site `:293-321` with the ordering and timeout guard described in truth 5. |
| `apps/brief/vault_writer.py` | Obsidian projection + Entity Graph.md | ✓ VERIFIED | `_entity_names` (`:51`, first-seen-order dedup + `or []` None-safety from `979467d`), `render_wikilinked` (`:76`), `write_item_obsidian` (`:118`), `render_sab_obsidian` (`:191`), `render_entity_graph` (`:266`, row-based), `write_entity_graph` (`:313`), `render_entity_graph_from_store` (`:331`), `write_entity_graph_from_store` (`:364`), `write_vault_digest` (`:388`). |
| `apps/brief/consumer.py` | attach entity links to rows | ✓ VERIFIED | `_attach_entities` (`:98-104`) sets `row["entities"] = store.get_entity_links(item_id)` off the event loop via `asyncio.to_thread`. |
| `scripts/validate_entity_threshold.py` | threshold re-validation harness | ✓ VERIFIED | Present (24.6 KB); offline/http/synthetic modes; emits the 999.3 verdict report (`:598`). |
| `999.3-VERDICT.md` | validated T* | ✓ VERIFIED (relocated) | Lives at `.planning/phases/_archived/999.3-entity-resolution-cross-language-coverage-and-mE5-large-re-validation/999.3-VERDICT.md`. Code comments still cite the pre-archive path — see **I-1**. |
| `tests/test_entities.py` | LLM NER unit tests | ✓ VERIFIED | 12.8 KB. |
| `tests/test_triage_entities.py` | entity module unit tests | ✓ VERIFIED | 8.8 KB. |
| `tests/test_store_entities.py` | store contract tests | ✓ VERIFIED | 12.8 KB, 15 test functions incl. `test_entity_links_cross_language` (`:280`) and 4 `get_active_entities` cases (`:313-374`). |
| `tests/test_triage_worker.py` | worker regression tests | ✓ VERIFIED | 3 entity-specific tests (see truth 5). |
| `tests/test_vault_writer.py` | projection tests | ✓ VERIFIED | 20.1 KB, 23 tests green per 08-UAT.md Path B closeout. |
| `tests/test_brief_consumer.py` | consumer view-filter tests | ✓ VERIFIED | 6.5 KB. |
| `tests/test_validate_entity_threshold.py` | harness tests | ✓ VERIFIED | 5.4 KB. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `apps/triage/worker.py::process_item` | `entities.resolve_entities_async` | direct `await asyncio.wait_for(...)` after `put_enrichment`, before `bus.publish` | ✓ WIRED | `worker.py:271` → `:308-313` → `:339`. Ordering is the R2/R5 prohibition and is enforced positionally in source. |
| `apps/triage/entities.py::_find_or_create_entity` | `store.find_similar_entity` | pgvector cosine at `LINK_THRESHOLD` | ✓ WIRED | `entities.py:235`; resolution order is exact `(name_norm, lang)` → cosine ≥ 0.92 → create new (`:219` docstring, matching implementation). |
| `apps/brief/consumer.py` | `store.get_entity_links(item_id)` | `_attach_entities` per enrichment row | ✓ WIRED | `consumer.py:101`. |
| `apps/brief/vault_writer.py::write_entity_graph_from_store` | `store.get_active_entities(limit=…)` | store-backed graph query | ✓ WIRED | `vault_writer.py:379`. Live output on disk proves the path executes in production. |
| `apps/brief/vault_writer.py::write_item_obsidian` | `_entity_names(item)` → `render_wikilinked` | canonical names, not the heuristic | ✓ WIRED | `vault_writer.py:143`; `render_sab_obsidian` uses the same source at `:221`. |
| `init_schema()` | `003-vectors.sql` | sorted `sql/*.sql` glob | ✓ WIRED | Live Postgres holds 640 entities / 1138 links against this schema. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `Entity Graph.md` (`write_entity_graph_from_store`) | `entities` | `store.get_active_entities(limit=…)` → Postgres aggregation | Yes — live file is 3001 lines with real counts (Claude Code 21 links, Google 17, …) | ✓ FLOWING (renderer one build behind — W-1) |
| Vault item notes (`write_item_obsidian`) | `item["entities"]` | `consumer.py::_attach_entities` → `store.get_entity_links` | Yes — live notes carry `## Entities` sections | ✓ FLOWING |
| `entities.embedding` | `embedding` | `embed_entity_name` → `LLM_BASE_URL/embeddings` (mE5-large) | Yes — 640/640 live entities have a non-NULL 1024-dim vector | ✓ FLOWING |
| `entity_links` | rows | `resolve_entities_async` in the triage worker | Yes — 1138 live rows across 359 distinct items | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Entity resolution never blocks the verdict (incl. timeout path) | `pytest tests/test_triage_worker.py -k entity -q` | 3 passed, 12 deselected in 0.20s | ✓ PASS |
| Link idempotency + alias aggregation + cross-language contract | `pytest tests/test_store_entities.py -k "cross_language or get_all_entities or idempotent" -q` | 4 passed, 5 skipped (db_live), 20 deselected in 0.19s | ✓ PASS |
| Full suite still collects clean | `pytest tests/ -q --collect-only` | 678 tests collected in 0.48s | ✓ PASS |
| Full suite green (not re-run here — cited) | `make -f ops/Makefile test-safe` | **678 passed / 0 failed in 35.31s**, throwaway Postgres port 22062, clean trap teardown (live run this session, 2026-08-01; prior 677/0 baseline at `63b8da2` +1 test from `bb5420e`) | ✓ PASS (cited) |
| Live entity + link counts | `docker exec infotriage-postgres psql …` | entities=640, entity_links=1138, cross-lang links=16, embedded=640 | ✓ PASS |
| Cross-modality coverage | `docker exec infotriage-postgres psql …` (group by URL scheme) | imap=565 distinct entities, https=57 | ✓ PASS |
| Debt-marker scan across all 8 Phase-8 source files | `grep -nE "TBD\|FIXME\|XXX\|HACK\|PLACEHOLDER\|TODO"` on `entities.py`, `worker.py`, `vault_writer.py`, `consumer.py`, `_protocol.py`, `_postgres.py`, `_inmemory.py`, `validate_entity_threshold.py` | no matches (exit 1) | ✓ PASS |

> Note on the test count: the 677/0 figure in STATE.md predates `bb5420e` (adds one per-ingest contract test). The canonical `make test-safe` gate run live on 2026-08-01 reports **678 passed / 0 failed**; collection count agrees (678 collected). 678/0 is the green baseline to quote.

### Probe Execution

No `scripts/*/tests/probe-*.sh` convention exists in this repository and none was declared by `08-PLAN.md` or either SUMMARY. Skipped — the Behavioral Spot-Checks above cover the equivalent ground (same disposition as Phases 5 and 7).

### Requirements Coverage

| Requirement | Source | Description | Status | Evidence |
|-------------|--------|-------------|--------|----------|
| R1 | 08-PLAN | LLM-based NER (qwen36, PER/ORG/LOC/GPE/MISC) | SATISFIED | `entities.py:96 extract_entities` + `:127 _parse_entities` (fence-tolerant, empty list on malformed output); `tests/test_entities.py::TestParseEntities`/`TestExtractEntities` |
| R2 | 08-PLAN | mE5-large entity-name embedding | SATISFIED | `entities.py:188 embed_entity_name` with `query:` prefix convention; failure returns `None` rather than raising (T-08-03) |
| R3 | 08-PLAN | pgvector cosine linking at the validated threshold | SATISFIED | `entities.py:235` + `_postgres.py:531`; `LINK_THRESHOLD = 0.92` |
| R4 | 08-PLAN | Store protocol entity methods, idempotent | SATISFIED | 8 protocol methods; `ON CONFLICT` upserts; truth 6 behavioral evidence |
| R5 | 08-PLAN | Triage worker integration, best-effort | SATISFIED | truth 5 behavioral evidence |
| R6 | 08-PLAN | Obsidian projection + `Entity Graph.md` | SATISFIED | SC-2 evidence; live 3001-line artifact |
| ADR-003 | ROADMAP §Phase 8 | Phase-level requirement designator | SATISFIED | Entity resolution realized as Postgres truth with an Obsidian projection, per the ADR's split |
| ADR-004 | 08-PLAN | All-local LLM/embedding | SATISFIED | Prohibition P-1 evidence |
| ADR-006 | 08-PLAN | Microservice architecture / entity resolution schema | SATISFIED | truths 1, 2, 4 |

No orphaned requirements: every ID mapped to Phase 8 appears in a plan's `requirements` field and resolves above.

### Security Threat Coverage (`08-SECURITY.md`)

| Threat | Disposition | Status | Re-verified here |
|--------|-------------|--------|------------------|
| T-08-01 — information disclosure via LLM NER output | mitigate | closed | Yes — no egress path in `entities.py` (P-1) |
| T-08-02 — tampering via `entity_links` upsert | mitigate | closed | Yes — `ON CONFLICT DO NOTHING` on `(entity_id, item_id, mention)` + passing idempotency test (truth 6) |
| T-08-03 — DoS via embedding-call failure | mitigate | closed | Yes — `embed_entity_name` swallows failures and returns `None`; worker timeout guard (truth 5) |
| T-08-04 — elevation of privilege | accept (R-08-01) | closed | Yes — `entities.py` adds no listener, route, or bound port |

### Anti-Patterns and Warnings

| ID | File / Surface | Pattern | Severity | Impact |
|----|----------------|---------|----------|--------|
| W-1 | `infotriage-brief` container (image created **2026-07-24 18:48**) | Deployed image predates `a2db924` (2026-07-25, "filter structural noise entities, add aliases to Entity Graph.md") and `979467d` (2026-08-01, `_entity_names` dedup + None-safety). Confirmed empirically: the live `~/Vault/brief-outbox/Entity Graph.md`, written 2026-08-01 12:00, contains **zero** `- **Aliases:**` lines even though `vault_writer.py:357` emits that line unconditionally (with an `—` fallback) at HEAD. | MEDIUM | The code satisfies UAT Test 3's alias requirement; the **deployed** projection does not. Not a Phase 8 code gap and not blocking — but the live vault under-represents what Phase 8 ships until the image is rebuilt. Remediation is one command: `docker compose build brief && docker compose up -d brief`. For contrast, `infotriage-triage` (created 2026-07-26) **is** past `a2db924`, so the noise filter is live on the write path. A sample of 40 live item notes showed no `NATO, NATO` cosmetic duplicates, so the `979467d` dedup gap is not visibly manifesting. |
| W-2 | Live corpus | 98% of entities carry `lang='und'` (weak upstream language detection), 52% are typed `MISC`, only 16 of 1138 links are demonstrably cross-language, and `name_norm` collisions across distinct `lang` values remain 0. | LOW | The cross-language merge mechanism is proven correct by tests and by the 16 live cross-lang rows, but it cannot fire at scale until the upstream language detector improves. Independently observed and accepted in `08-VALIDATION.md` audits (2026-07-24, 2026-07-31) and `08-UAT.md` Tests 1+2 — carried forward, explicitly not a Phase 8 regression. Compounded by the deliberately conservative T*=0.92 (see truth 3). |
| I-1 | `apps/triage/entities.py:31`, `_protocol.py:191`, `_postgres.py:534`, `_inmemory.py:248`, `scripts/validate_entity_threshold.py:28` | Comments cite `.planning/phases/999.3-…/999.3-VERDICT.md`; the directory has since moved to `.planning/phases/_archived/999.3-…/`. | INFO | Stale doc pointer only. No behavior impact. Worth a one-line sweep next time these files are touched. |
| I-2 | `08-UAT.md` Test 5 code-review notes | 3 non-blocking follow-ups acked at UAT close: `_entity_names` could collapse to `list(dict.fromkeys(...))`; the `or []` fallback is undocumented in the docstring; `render_entity_graph` reads `entity.get("aliases")` directly rather than via `_entity_names`, so it could reproduce the same duplicate class if duplicate `(mention, lang)` rows ever reach it. | INFO | All three were surfaced and accepted at UAT close; none affect a Phase 8 must-have. |

No `TBD`/`FIXME`/`XXX`/`TODO`/`HACK`/`PLACEHOLDER` markers exist in any of the 8 Phase-8 source files.

### Human Verification Required

None outstanding. `08-UAT.md` is `status: complete` with **5/5 tests passed, 0 issues, 0 pending** (closed 2026-08-01T13:30Z):

1. Entity extraction during triage — pass
2. Cross-language entity linking — pass (16 live cross-lang `entity_links` rows)
3. `Entity Graph.md` in the Obsidian vault — pass
4. Entity resolution never blocks scoring — pass
5. Vault item notes show entity wikilinks — pass (Path B, `979467d`)

W-1 is the one item an operator may want to act on, and it is a redeploy, not a verification question.

### Gaps Summary

**No blocking gaps.** All 8 must-haves (2 ROADMAP success criteria + 6 PLAN truths) are verified against the codebase with file:line evidence, both PLAN prohibitions hold, all 4 security threats are closed, and the two behavior-dependent truths (best-effort non-blocking entity resolution; link idempotency on re-process) were confirmed by running their named tests in this session rather than accepted on symbol presence.

Three items are recorded above as non-blocking. Only **W-1** is actionable: the `infotriage-brief` container image is one build behind `main`, so the live vault projection omits the alias line that HEAD emits. The Phase 8 deliverable itself is correct; the deployment is stale. **W-2** (live-corpus language-detection quality) and **I-1/I-2** (stale doc paths, style follow-ups) were already surfaced and accepted during validation and UAT.

### Deferred Items

None. No Phase 8 concern maps onto a later milestone phase's goal or success criteria. The `articles.discipline = 0` observation recorded in `08-UAT.md` belongs to Phase 11's parked schema debt and was never a Phase 8 deliverable.

---

_Verified retroactively on 2026-08-01 to close the Phase 8 artifact gap (the phase reached VALIDATION `validated` + UAT `complete` without a VERIFICATION.md, mirroring the Phase 7 backfill in `07-VERIFICATION.md`). Evidence consolidates `08-SPEC.md`, `08-PLAN.md`, `08-01-SUMMARY.md`, `08-02-SUMMARY.md`, `08-SECURITY.md`, `08-VALIDATION.md` (audits 2026-07-24 and 2026-07-31), and `08-UAT.md`, each independently re-checked against live code, live Postgres, and live vault artifacts. Test baseline cited from `make -f ops/Makefile test-safe` (678 passed / 0 failed, live run 2026-08-01); two targeted named tests were re-executed here for the behavior-dependent truths. No production behavior was changed by this verification._
_Verifier: Claude (gsd-verifier)_
