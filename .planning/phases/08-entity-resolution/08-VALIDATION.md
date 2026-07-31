---
phase: 08
slug: entity-resolution
status: validated
nyquist_compliant: true
wave_0_complete: true
created: 2026-07-13
---

# Phase 08 — Entity Resolution Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`) |
| **Quick run command** | `pytest tests/test_entities.py tests/test_triage_entities.py tests/test_store_entities.py tests/test_triage_worker.py tests/test_vault_writer.py tests/test_brief_consumer.py tests/test_validate_entity_threshold.py -q` |
| **Full suite command** | `pytest tests/ -q` |
| **Estimated runtime** | ~30 seconds (inmemory); ~60 seconds with db_live |

---

## Sampling Rate

- **After every task commit:** Run the quick Phase 8 subset above.
- **After every plan wave:** Run `pytest tests/ -q`.
- **Before `/gsd-verify-work`:** Full suite must be green.
- **Max feedback latency:** 60 seconds.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 08-01-01 | 01 | 1 | R1 NER | T-08-01 | NER output stored in Postgres only | unit | `pytest tests/test_triage_entities.py -q` | ✅ | ✅ green |
| 08-01-02 | 01 | 1 | R2 Entity embedding | T-08-03 | Embedding failure caught; entity stored with NULL vector | unit | `pytest tests/test_triage_entities.py::test_embed_entity_name_returns_none_on_failure -q` | ✅ | ✅ green |
| 08-01-03 | 01 | 2 | R3 Entity linking | T-08-02 | ON CONFLICT / delete-before-insert prevents duplicate links on re-process | unit + contract | `pytest tests/test_triage_entities.py tests/test_store_entities.py -q` | ✅ | ✅ green |
| 08-01-04 | 01 | 2 | R4 Store protocol methods | T-08-02 | Idempotent upserts; no duplicate entity_links | contract | `pytest tests/test_store_entities.py -q` | ✅ | ✅ green |
| 08-01-05 | 01 | 3 | R5 Triage worker integration | T-08-04 | Entity resolution failure does not block verdict.ready | unit | `pytest tests/test_triage_worker.py -q` | ✅ | ✅ green |
| 08-01-06 | 01 | 4 | R6 Obsidian projection | T-08-02 | Postgres remains system of record; vault is projection only | unit | `pytest tests/test_vault_writer.py tests/test_brief_consumer.py -q` | ✅ | ✅ green |
| 08-01-07 | 01 | 5 | mE5-large threshold re-validation | — | Threshold documented and validated on cross-language corpus | integration | `pytest tests/test_validate_entity_threshold.py -q` | ✅ | ✅ green |
| 08-02-01 | 02 | 2 | R1 NER (LLM-based, qwen36) | T-08-01 | LLM parse failure/malformed JSON returns empty list, never crashes | unit | `pytest tests/test_entities.py::TestParseEntities tests/test_entities.py::TestExtractEntities -q` | ✅ | ✅ green |
| 08-02-02 | 02 | 2 | R2/R3 Embedding + linking (LINK_THRESHOLD=0.92) | T-08-02, T-08-03 | Exact match takes precedence over similarity; embedding failure returns None, never blocks | unit | `pytest tests/test_entities.py::TestNormalizeName tests/test_entities.py::TestEmbedEntityName tests/test_entities.py::TestResolveEntities -q` | ✅ | ✅ green |
| 08-02-03 | 02 | 5 | R4 get_all_entities (store protocol) | T-08-02 | Aggregates aliases + link_count per canonical entity; empty store returns [] | contract | `pytest tests/test_store_entities.py::test_get_all_entities_aggregates_aliases_and_links tests/test_store_entities.py::test_get_all_entities_empty -q` | ✅ | ✅ green |
| 08-02-04 | 02 | 5 | R6 Entity Graph.md generation | T-08-02 | write_entity_graph/write_entity_graph_from_store produce Entity Graph.md with type/lang/alias/link-count; empty-store case handled | unit | `pytest tests/test_vault_writer.py -k entity_graph -q` | ✅ | ✅ green |
| 08-02-05 | 02 | 5 | LINK_THRESHOLD adopted at validated value | 999.3-VERDICT.md | `apps/triage/entities.py:LINK_THRESHOLD == 0.92` matches the validated recommendation | integration | `pytest tests/test_validate_entity_threshold.py -q` (verdict) + code inspection | ✅ | ✅ green |
| 08-02-06 | 02 | 6 | R4-extended `get_active_entities` (store protocol) | T-08-02 | Active-entities view used by `apps/brief/vault_writer.py:368` + `apps/wiki/wiki_worker.py`: stats + since-filter + limit, orders by `link_count DESC, name_norm`, empty case returns []. Coexists with 08-02-03 `get_all_entities` (not a rename); added post-08-02-SUMMARY (timing unverified; likely Wave 6 closeout polish). | contract | `pytest tests/test_store_entities.py::test_get_active_entities_stats_and_since_filter tests/test_store_entities.py::test_get_active_entities_empty tests/test_store_entities.py::test_get_active_entities_orders_by_link_count_then_name_norm tests/test_store_entities.py::test_get_active_entities_respects_limit -q` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements.

- [x] `tests/test_entities.py` — unit tests for LLM-based (qwen36) NER, parsing, embedding, and linking (Wave 2, added 2026-07-20)
- [x] `tests/test_triage_entities.py` — unit tests for `apps/triage/entities.py`
- [x] `tests/test_store_entities.py` — contract tests for Store entity methods
- [x] `tests/test_triage_worker.py` — regression tests for worker integration
- [x] `tests/test_vault_writer.py` — vault projection tests
- [x] `tests/test_brief_consumer.py` — consumer view-filter tests
- [x] `tests/test_validate_entity_threshold.py` — threshold validation script tests

---

## Manual-Only Verifications

All phase behaviors have automated verification.

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 60s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-07-13; re-validated 2026-07-24 (see audit below)

---

## Validation Audit 2026-07-24

The original approval (2026-07-13) covered only Wave 1 (08-01-SUMMARY.md). Wave
2-6 (08-02-SUMMARY.md: LLM-based NER via qwen36, `get_all_entities()`,
Entity Graph.md generation, LINK_THRESHOLD re-validated to 0.92) landed
2026-07-20 and was never mapped in this file despite `nyquist_compliant: true`
remaining set — a documentation-accuracy gap, not a test gap: all Wave 2-6
functionality already had real, passing tests (`tests/test_entities.py`,
targeted `test_store_entities.py`/`test_vault_writer.py` cases), they were
just absent from the Per-Task Verification Map above.

| Metric | Count |
|--------|-------|
| Gaps found | 5 (undocumented map rows for Wave 2-6; no missing/failing tests) |
| Resolved | 5 (map rows 08-02-01..05 added above, cross-checked against live code — `LINK_THRESHOLD == 0.92` confirmed in `apps/triage/entities.py`) |
| Escalated | 0 |

Full Phase 8 test set re-run at audit time: `pytest tests/test_entities.py
tests/test_triage_entities.py tests/test_store_entities.py
tests/test_triage_worker.py tests/test_vault_writer.py
tests/test_brief_consumer.py tests/test_validate_entity_threshold.py -q` →
**105 passed, 15 skipped** (db_live-gated), 0 failed.

**Separately observed during this audit (not a Nyquist gap — flagging for
awareness):** live production data shows entity extraction and cross-language
linking both working mechanically (535 entities, 1127 links; NATO/Russland/Iran
present), but the top-ranked entities by link count are dominated by non-
substantive noise (GitHub, CI workflow names, the operator's own name, email-
platform senders) rather than geopolitical actors, and a spot query for
same-`name_norm`-different-`lang` entity pairs returned zero rows — i.e. no
observed cross-language merges in the current live corpus, despite that being
Phase 8's core validated capability (999.3, T*=0.92). This is a live-data/
product-quality observation for a future `/gsd-verify-work 8` UAT session
(one is already in progress, paused at Test 1/5), not a test-coverage gap —
no VALIDATION.md action taken.

## Validation Audit 2026-07-31

Re-audit per `/gsd-validate-phase 8` triggered after the 260725-lme +
260726-jpe commits (mid-Phase-12-sub-wave-(a), post-`3e5b7cf` dedup-fix
re-score). State A — VALIDATION.md existed, all 12 task rows ✅ green, and
`status: validated` / `nyquist_compliant: true` already set. Re-verification
of every row against current code + tests; no gaps discovered.

| Metric | Count |
|--------|-------|
| Gaps found | 0 |
| Resolved | 0 |
| Escalated | 0 |

Current Phase 8 quick-subset re-run (the `Quick run command` from the frontmatter):

```
pytest tests/test_entities.py tests/test_triage_entities.py \
      tests/test_store_entities.py tests/test_triage_worker.py \
      tests/test_vault_writer.py tests/test_brief_consumer.py \
      tests/test_validate_entity_threshold.py -q
```

→ **122 passed, 15 skipped (db_live-gated), 0 failed in 6.65s — exit 0.**
(Δ vs. the 2026-07-24 audit baseline: **+17 net additional passing tests**
[105 → 122]; 15 still skipped require `-m db_live` with a reachable
`INFOTRIAGE_TEST_DSN` and are intentionally non-blocking. No regressions in
any row of the Per-Task Verification Map.)

Live-code invariants spot-checked against the map (file existence + symbol
presence):

| Map row | Code invariant | Verified |
|---------|---------------|----------|
| 08-02-05 | `apps/triage/entities.py:33` — `LINK_THRESHOLD = 0.92` (999.3 ratified) | ✅ |
| 08-02-04, 08-01-06 | `apps/brief/vault_writer.py` — `render_wikilinked` (l.65), `write_entity_graph` (l.302), `write_entity_graph_from_store` (l.353), `write_vault_digest` (l.377) | ✅ |
| 08-02-01..02 | `apps/triage/entities.py` — `extract_entities` (l.96), `embed_entity_name` (l.188), similarity lookup `store.find_similar_entity(embedding, LINK_THRESHOLD)` (l.235) | ✅ |
| 08-01-05 | `apps/triage/worker.py` — `resolve_entities_async` called after `put_enrichment`, before `verdict.ready`; exception swallowed | ✅ |
| 08-01-07 | `scripts/validate_entity_threshold.py` — exists; produces 999.3-VERDICT.md | ✅ |
| All rows | All 7 referenced test files exist + all 3 impl files exist | ✅ |

API-drift correction (not a gap, but the prior note framed it wrong): on
spot check, `Store.get_active_entities(...)` and `Store.get_all_entities(...)`
are **two distinct methods that coexist on the protocol** — production callers
(`apps/brief/vault_writer.py:368` + `apps/wiki/wiki_worker.py`) use the
*active*-entities view (stats + since-filter + limit), while the full-
aggregation `get_all_entities` from row 08-02-03 remains the canonical
full-graph sibling. Both have contract tests (`tests/test_store_entities.py`:
2 for `get_all_entities`, 4 for `get_active_entities`). **No rename happened.**
The 08-02 SUMMARY did not capture the `get_active_entities` addition; closed in
this audit by adding new map row **08-02-06** above (covers the active-entities
view with its 4 tests + 2 production callers). Row 08-02-03 (full aggregation)
stays as-is.

**Separately observed during this audit (not a Nyquist gap — flagging for
awareness):** with the dedup-fix `3e5b7cf` re-score settled (q.triage idle,
Postgres enrichment_total=495, last_5min=0, last_1h=0 per prior session's
verification), the live CCIR corpus contains 606 entities / 1058 entity_links
(verified in-session 2026-07-31 via `docker exec infotriage-postgres
psql`; distinct_entities_in_links=578, distinct_items_in_links=359).
Δ vs. the 2026-07-24 audit's 535/1127 = +71 entities / -69 links — net
of merge/stale-purge cycles; not a behavioural change. The
`name_norm` cross-language collision count remains 0 in the live corpus
(read: no observed cross-language merges at T*=0.92 yet, despite that being
Phase 8's validated capability). Top entities still reflect the same noise
floor flagged 2026-07-24 (Claude Code / Google / EU signal; InfoTriage / PADI
/ Zwift / Alain Airom/Ayrom project-noise). This is a live-data/product-
quality observation for the in-progress `/gsd-verify-work 8` UAT session
(just reset to `status: testing`, paused at Test 1/5), not a test-coverage
gap — same call as last audit, no VALIDATION.md action.
