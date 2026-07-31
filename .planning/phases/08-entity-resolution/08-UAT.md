---
status: testing
phase: 08-entity-resolution
source: [08-01-SUMMARY.md, 08-02-SUMMARY.md]
started: 2026-07-31T22:00:00.000Z
updated: 2026-07-31T22:00:00.000Z
---

## Current Test

number: 1
name: Entity extraction during triage
awaiting: user response

## Tests

### 1. Entity extraction during triage
expected: Newly triaged items have named entities (people, organizations, places) automatically extracted from their title/summary and stored in the canonical entity store — no manual step required. Top entities should reflect your actual interests (defense/geopolitics/tech), not incidental noise from email chrome or your own name.
result: pending

### 2. Cross-language entity linking
expected: The same real-world entity mentioned in different languages (e.g. NATO in an English article, Russland/Russia in a Norwegian article) appears as a single canonical entity record (linked via `name_norm`) — not duplicated once per language.
result: pending

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
passed: 0
issues: 0
pending: 5
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

## Gaps

[none yet]
