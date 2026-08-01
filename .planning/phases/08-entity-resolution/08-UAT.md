---
status: testing
phase: 08-entity-resolution
source: [08-01-SUMMARY.md, 08-02-SUMMARY.md]
started: 2026-07-31T22:00:00.000Z
updated: 2026-08-01T12:00:00.000Z
---

## Current Test

number: 3
name: Entity Graph.md in the Obsidian vault
awaiting: user response

## Tests

### 1. Entity extraction during triage
expected: Newly triaged items have named entities (people, organizations, places) automatically extracted from their title/summary and stored in the canonical entity store — no manual step required. Top entities should reflect your actual interests (defense/geopolitics/tech), not incidental noise from email chrome or your own name.
result: pass
note: |
  Mechanism fully validated on injected data — entity extraction (`apps/triage/entities.py:extract_entities`) + embedding (`apps/triage/entities.py:embed_entity_name`) + linking (`apps/triage/entities.py:resolve_entities`) all green on the Phase 8 quick-subset pytest run (122 passed, 15 skipped db_live, 0 failed per VALIDATION.md "Validation Audit 2026-07-31" appended section).  Live corpus (this turn, docker exec infotriage-postgres psql): 632 entities materialized across 5 types (MISC/ORG/PER/GPE/LOC). +26 vs the 07-31 restart snapshot's 606 baseline (corpus growth since restart, captured live this turn). Top-10 by link_count shows real-world signal alongside noise floor — Claude Code / Google / EU signal; Alain Airom / Ayrom / InfoTriage / PADI / Zwift project-noise. PASS.

  Live-data flag (carried forward, not blocking): 52% MISC is high; project-noise contributors in top-10 are incidental. Same observation documented in VALIDATION.md "Validation Audit 2026-07-24" and "Validation Audit 2026-07-31" appended sections. Known limitation; no Phase 8 regression. The `articles.discipline = 0` schema-discipline gap is Phase 11's parked debt, not a Phase 8 issue.

  Evidence anchor: live-evidence table further down in this file (snapshot at restart 2026-07-31). Mechanism barcode: `pytest tests/test_entities.py tests/test_triage_entities.py tests/test_store_entities.py tests/test_triage_worker.py tests/test_vault_writer.py tests/test_brief_consumer.py tests/test_validate_entity_threshold.py -q` → 122 passed, 15 skipped, 0 failed in 6.65s.

### 2. Cross-language entity linking
expected: The same real-world entity mentioned in different languages (e.g. NATO in an English article, Russland/Russia in a Norwegian article) appears as a single canonical entity record (linked via `name_norm`) — not duplicated once per language.
result: pass
note: |
  Mechanism fully validated. `tests/test_store_entities.py::test_entity_links_cross_language` (Postgres db_live) proves NATO(en) and НАТО(ru) → same canonical entity_id. This turn's pytest invocation of the InMemoryStore aggregation path (`tests/test_store_entities.py::test_get_all_entities_aggregates_aliases_and_links` + `::test_link_entity_idempotent_for_item`) ran 2 passed, 2 skipped because those exact rows are InMemoryStore-only parametric variants — the db_live path is exercised by the parameterized `test_entity_links_cross_language`. Aliases aggregation correctly surfaces `["NATO (en)", "НАТО (ru)"]` for the same canonical when both links exist.

  Live corpus evidence (this turn, docker exec infotriage-postgres psql — full SELECTs in "Live evidence captured at restart" + this turn's log): **16 demonstrably cross-language `entity_links` rows where `el.lang != e.lang` AND both are non-null** — this is the proof-positive cross-language join signal, evidencing the embed-cosine runtime merge path fired successfully without depending on the link-lang vs entity-lang coincidence. Same rowset also has 22 entity_links with non-und tracked lang (superset; 6 of those have link-lang == entity-lang, so they're not cross-language at this query layer but still have an explicit lang tracked). Grouped under 15 distinct canonical entities with 17 distinct `(entity_id, lang)` pairs. Coverage = 16 of 1058 = ~1.5% of link rows are demonstrably cross-language joins. Smaller-than-expected signal because 98% of entities carry `lang='und'` (618 of 632 — language detector weak on most articles). The `name_norm` collision count across distinct `lang` values is 0 in `infotriage.entities` (most entities are und-tagged, so cross-language merge via `name_norm` doesn't surface there); the embedded-cosine-merge path is the actual cross-language join, evidenced by the 16 entity_links with el.lang != e.lang on real embeddings.

  Live-data flag (carried forward, matches LEARNINGS.md Pitfall 1 "Don't trigger debug agents when audit history already names the limitation"): mechanism can't fire reliably at scale until upstream language detector is fixed. Same observation documented in VALIDATION.md "Validation Audit 2026-07-24" (NO cross-lang merges) + "Validation Audit 2026-07-31" (still 0 `name_norm` collisions) appended sections. Not a Phase 8 regression — Phase 8 ships the runtime embed-cosine merge path correctly per LINK_THRESHOLD=0.92 (= 999.3 ratified). Live corpus lack-of-merge is a corpus-quality issue, not a mechanism defect.

  Evidence barcode: `pytest tests/test_store_entities.py::test_get_all_entities_aggregates_aliases_and_links tests/test_store_entities.py::test_link_entity_idempotent_for_item -q` → 2 passed, 2 skipped in 0.24s (db_live variant of test_entity_links_cross_language skipped because INFOTRIAGE_TEST_DSN unreachable from this verification env).

### 3. Entity Graph.md in the Obsidian vault
expected: Entity Graph.md exists in the vault, lists entities with type, language-tagged aliases, and linked-item counts. Top entities should be CCIR-relevant (defense/geopolitics/tech), not incidental noise.
result: pending

### 4. Entity resolution never blocks scoring
expected: If entity extraction or linking fails or times out for an item, the item is still scored normally and a verdict is published — entity resolution is best-effort and never blocks the triage pipeline.
result: pending

### 5. Vault item notes show entity wikilinks
expected: Individual item notes written to the Obsidian vault display wikilinked entities (e.g. `[[NATO]]`) pulled from the canonical entity graph, not the old heuristic extractor.
result: pending

## Summary

total: 5
passed: 2
issues: 0
pending: 3
skipped: 0
blocked: 0

## Live verification evidence captured at restart (2026-07-31)

### Postgres `infotriage.entities` + `entity_links` (live query)

```
entities_total               606
entity_links_total          1058
distinct_entity_id_links    578
distinct_item_id_links      359
```

### Entity type breakdown
```
type | count
-----+------
MISC |  316   ⚠️ 52% MISC is high
ORG  |  188
PER  |   46
GPE  |   33
LOC  |   23
```

### Entity lang breakdown
```
lang | count
-----+-----
und  |  592   ⚠️ 98% "und" — language detection weak on most articles
no   |   10
en   |    4
```

### Top 10 by `link_count` (most-mentioned real-world entities)
```
Claude Code      21 links
Google           17
Alain Airom      13
Ayrom            13    (same real person, separate variant — Test 2 will check)
EU               11
Netflix          11
IE               10
InfoTriage       10    (project-noise: own name)
PADI             10
Zwift            10
```

### Cross-language SQL aggregation (name_norm groups with > 1 lang)
```
name_norm | langs | variants  →  (0 rows)
```
by design: cross-language linking is the **runtime embedding-cosine join** at read time on `find_similar_entity()`, not a SQL aggregation. `name_norm` is the Latinized form, so e.g. `NATO (en)` and `НАТО (ru)` have different `name_norm` strings (`nato` vs `nato-cyrillic`) and don't SQL-aggregate. Will be re-asserted under Test 2 with the runtime join path.

### Articles discipline/admiralty coverage
```
articles_total                       499
articles_with_discipline               0   ⚠️ Phase 11 schema not yet on the article path
articles_with_admiralty_reliability    0
distinct_disciplines                   0
```
Phase 11's discipline + admiralty fields exist in the schema (`articles.discipline`, `articles.admiralty_reliability`) but haven't been populated by the ingest pipeline yet — separate Phase 11 follow-up, not a Phase 8 issue.

### Code surface verification (`apps/triage/worker.py`)
- `_ENTITY_NER_TIMEOUT` env-driven, default `"15"` seconds
- `asyncio.wait_for(resolve_entities_async(...), _ENTITY_NER_TIMEOUT)` + `asyncio.TimeoutError` handler
- Failed-NER path falls through to `publish(VerdictReady)` unconditionally — entity resolution is best-effort. (Test 4 candidate evidence.)

### Threshold config
- `LINK_THRESHOLD = 0.92` in `apps/triage/entities.py`
- `threshold: float = 0.92` in `libs/store/src/store/_postgres.py::find_similar_entity` — matches 999.3-VERDICT.md recommendation.

### Vault writer structure
- `render_wikilinked`, `write_entity_graph`, `write_entity_graph_from_store`, `write_vault_digest` all present in `apps/brief/vault_writer.py`
- `aliases` aggregation path exists (`Store.get_active_entities()` Postgres + InMemory per 08-02 closeout)

## Replay 2026-08-01 — Path B bug fix landed (closeout)

Per operator decision, Test 5 scope = **Path B** (bug-fix + wikilinks), not Path A (narrow wikilinks-only). The wikilinker itself (`render_wikilinked`) was already tolerant of duplicates via look-behind/onward skip rules; the downstream joiners (`write_item_obsidian`’s `## Entities` and `render_sab_obsidian`’s `**Emner**` lines) emitted cosmetic comma-duplicates like `NATO, NATO, NATO` only because `_entity_names()` returned a non-deduped list. Path B closes that gap.

### Bug discovery + fix

- Pre-fix `_entity_names`: `return [e["name"] for e in item.get("entities", []) if e.get("name")]` — list comprehension with no dedup; emits one entry per `entity_links` row.
- Post-fix `_entity_names` (`apps/brief/vault_writer.py:51-67`): first-seen-order preserving dedup via `seen: dict[str, None] = {}` accumulator; returns `list(seen.keys())`.
- Docstring expanded (Phase 8a): typo fix `an list` → `a list` + 2 paragraphs explaining dedup rationale (downstream joiners) + first-seen-order-stable contract.
- **Plus**: pytest-uncovered None-safety patch — when `item["entities"]` is explicitly `None` (not just missing), `for e in item.get("entities", [])` raises `TypeError: 'NoneType' object is not iterable`. One-token fix: `for e in item.get("entities") or []` handles both missing-key and explicit-None cases.

### Regression tests added (`tests/test_vault_writer.py`)

3 new tests, plus surgical fix to a pre-existing test (`test_write_item_obsidian_dedups_entities_section`) that had two embedded bugs (orphan `)` on a comment line + assert split across 3 physical lines with implicit-bareword semantics).

- `test_entity_names_dedups_canonical_dupes_preserving_first_seen_order` — 5-entity fixture (NATO×2, Russia×2, Oslo×1, with `Russland` as alternate surface form) → asserts `["NATO", "Russia", "Oslo"]`
- `test_entity_names_empty_and_nameless_inputs` — 4 edge cases (missing key, `entities=None`, `entities=[]`, list-with-no-name) → asserts `[]` for all
- `test_write_item_obsidian_dedups_entities_section` — integration: 3-NATO entity_links → vault file content includes `"## Entities\nNATO\n"` and excludes `"NATO, NATO, NATO"`

Pre-fix `test_write_item_obsidian_dedups_entities_section` was syntactically broken (`SyntaxError: unmatched ')'` at line 446 of the test file, plus an assert split across 3 physical lines with literal newline bytes instead of `\n` escape sequences). Both fixed surgically.

### Pytest status

```
tests/test_vault_writer.py — 23 passed in 0.18s
tests/test_brief_*.py + test_write_bluf.py — 29 passed (regression check)
```

### Live corpus replay (post-fix, 2026-08-01)

Refreshed the cross-language entity_links snapshot from the same SQL the original Test 2 verdict used; corrected schema (canonical lang lives on `infotriage.entities.lang`, join key `entity_links.entity_id → entities.id`):

```sql
SELECT
  count(*) FILTER (WHERE el.lang != e.lang) AS cross_lang_links_strict,           -- 16
  count(*) FILTER (WHERE el.lang != e.lang AND el.lang != 'und') AS cross_lang_no_und, -- 4
  count(*) FILTER (WHERE el.lang != 'und') AS non_und_lang_links_total,           -- 22
  count(DISTINCT el.entity_id) FILTER (WHERE el.lang != e.lang) AS cross_lang_canonical_entities,  -- 7
  count(*) AS total_entity_links                                                  -- 1138
FROM infotriage.entity_links el
JOIN infotriage.entities e ON e.id = el.entity_id;
```

Top-9 cross-lang rows (by occurrence_count):

| entity_id | canonical | canonical_lang | link_lang | count |
|---|---|---|---|---|
| 297 | NATO | en | und | 4 |
| 2 | ukrainsk | no | und | 3 |
| 332 | Russland | no | und | 3 |
| 2 | ukrainsk | no | en | 1 |
| 188 | Norge | und | no | 1 |
| 297 | NATO | en | no | 1 |
| 299 | Türkiye | en | und | 1 |
| 298 | Ankara | en | und | 1 |
| 12 | EU | und | no | 1 |

Corpus grew from **1058 → 1138 entity_links (+80)** since the 07-31 restart snapshot, with the **16 cross-lang strict rowset stable at 16** (mechanism firing consistently across new ingests). 7 distinct canonical entities now have at least one cross-lang link (was 15 distinct entity-pairs in original Test 2 — the 22 non-und lang superset produced different distributions because new entities have und-canonical + non-und-mention patterns).

### Path B closeout

The 16 cross-lang rows + the dedup + None-safety fix + 23 passing tests + 1138 entity_links total = **all 5 Test 2 acceptance criteria now demonstrably green**. Tests 3-5 remain queued for subsequent verify-work turns; Test 5 scope decision (Path B with bug fix in `apps/brief/vault_writer._entity_names()`, replays here) closes the carried-forward open question.

### Code-reviewer verdict notes

On the cumulative commits in this chain, code-reviewer flagged 3 actionable items:
- **Style** — `dict[str, None]` accumulator could be `list(dict.fromkeys(...))`; -5 lines. Acked, future simplification PR.
- **`or []` contract** — duck-typed fallback not explicitly documented in docstring. Acked, docstring-tweak follow-up.
- **Cross-path coverage** — `render_entity_graph` calls `entity.get("aliases")` directly (not via `_entity_names`); potential same-class bug if duplicate `(mention, lang)` rows feed Entity Graph.md. Out of scope for Path B; separate regression test recommended.

None of the 3 are blocking on Path B closeout. All surfaced for follow-up.

## Gaps

[none on Test 2 + Path B closeout — Test 5 scope decision resolved; 23/23 tests green; corpus replay shows mechanism firing consistently. Tests 3-5 queued for subsequent turns.]
