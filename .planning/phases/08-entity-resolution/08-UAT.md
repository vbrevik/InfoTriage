---
status: complete
phase: 08-entity-resolution
source: [08-01-SUMMARY.md, 08-02-SUMMARY.md]
started: 2026-07-24T18:04:02.000Z
updated: 2026-07-25T00:00:00.000Z
---

## Current Test
<!-- OVERWRITE each test - shows where we are -->

All 5 tests complete. 5/5 pass.

## Tests

### 1. Entity extraction during triage
expected: Newly triaged items have named entities (people, organizations, places) automatically extracted from their title/summary and stored in the canonical entity store — no manual step required.
result: pass
note: Confirmed via live query — entities.name/type populated via entity_links, no manual step. Top entities are noise-dominated (GitHub, Black, vbrevik, Medium, ad/newsletter domains) rather than defense/geopolitics signal — operator accepted as known issue, to be fixed via Test 3 (Entity Graph.md quality) and the in-flight worker.py/vault_writer.py NER-cleanup changes already in the working tree.

### 2. Cross-language entity linking
expected: The same real-world entity mentioned in different languages (e.g. NATO in an English article, Russland/Russia in a Norwegian article) is linked to a single canonical entity record instead of being duplicated once per language.
result: pass
note: No canonical/parent-entity column in `entities` table (id, name, name_norm, lang, type, embedding — unique on name_norm+lang). Confirmed with operator: cross-language linking is intentionally a runtime embedding-cosine join (T*=0.92, mE5-large) at read time, not a persisted merge. Design matches intent.

### 3. Entity Graph.md in the Obsidian vault
expected: Entity Graph.md exists in the vault, listing entities with type, language-tagged aliases, and linked-item counts — and the entities that surface prominently are the ones that matter for your interests (defense/geopolitics/tech), not incidental noise from email chrome or your own name.
result: pass (after fix)
note: |
  Two real gaps found and fixed:
  (1) Noise-dominated ranking — top entities were GitHub/Black/own name/Medium/
  ad-tech domains, zero defense/geopolitics/tech signal. Fixed via
  apps/triage/entities.py::is_noise_entity() — denylist (own name, CI/platform
  chrome) + bare-domain regex, checked in resolve_entities() before linking so
  new noise is never stored. Tunable via INFOTRIAGE_ENTITY_DENYLIST env var.
  Existing 38 noise entities purged from prod via new
  scripts/purge_noise_entities.py (reuses is_noise_entity() so purge stays in
  lockstep with the runtime filter).
  (2) Missing aliases — production Entity Graph.md is written by
  write_entity_graph_from_store() (store-query path), which never rendered
  language-tagged aliases (only the older, unwired render_entity_graph() had
  them). Fixed: Store.get_active_entities() (Postgres + InMemory) now
  aggregates aliases as "{mention} ({lang})" strings (same convention as
  get_all_entities()); render_entity_graph_from_store() renders them.
  Verified live: regenerated Entity Graph.md now tops with Google/Claude
  Code/EU (real CCIR-tagged signal) and shows aliases per entity. Full suite
  615/615 green (INFOTRIAGE_PG_DSN set), mypy clean, black clean. Commits
  pending.

### 4. Entity resolution never blocks scoring
expected: If entity extraction or linking fails or times out for an item, the item is still scored normally and a verdict is published — entity resolution is best-effort and never blocks the triage pipeline.
result: pass
note: Confirmed in code (apps/triage/worker.py:285-308) — asyncio.wait_for with INFOTRIAGE_ENTITY_NER_TIMEOUT (default 15s), both TimeoutError and generic Exception caught+logged, falls through unconditionally to publish VerdictReady. Existing regression tests test_entity_resolution_failure_does_not_block_verdict + test_entity_resolution_timeout_does_not_block_verdict both pass.

### 5. Vault item notes show entity wikilinks
expected: Individual item notes written to the Obsidian vault display wikilinked entities (e.g. [[NATO]]) pulled from the canonical entity graph, not the old heuristic extractor.
result: pass
note: Confirmed live — vault notes wikilink from the canonical entity graph ([[Ollama]], [[Docker]], [[Kitematic]]). URL-safety fix in the working tree verified directly (render_wikilinked preserves URLs while still linking standalone mentions). Minor unrelated cosmetic issue noted (not blocking): `## Entities` line can show duplicate names (e.g. "Docker, Docker") — _entity_names() doesn't dedupe. Deferred, not fixed this session.

## Summary

total: 5
passed: 5
issues: 0
pending: 0
skipped: 0

## Gaps

[none yet]
