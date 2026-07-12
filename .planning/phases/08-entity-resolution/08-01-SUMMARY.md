# Phase 8 — Entity Resolution (08-01) Summary

## What was delivered

1. **Store foundation**
   - Added `put_entity`, `get_entity`, `link_entity`, `get_entity_links` to the Store Protocol.
   - Implemented them in `PostgresStore` (pgvector + ON CONFLICT upserts) and `InMemoryStore` (dict-backed fake).
   - Added unique constraints in `libs/store/sql/003-vectors.sql` for idempotent upserts.
   - Added contract tests in `tests/test_store_entities.py`.

2. **NER + embedding + linking module**
   - Created `apps/triage/entities.py` with lightweight regex/heuristic NER, mE5-large embedding, and entity linking.
   - Added `LINK_THRESHOLD = 0.85` constant for future similarity-based linking.
   - Added unit tests in `tests/test_triage_entities.py`.

3. **Triage worker integration**
   - Wired `resolve_entities_async` into `apps/triage/worker.py` after enrichment and before `verdict.ready` publication.
   - Entity resolution failures are caught and logged; they never block verdict publication.
   - Added regression test in `tests/test_triage_worker.py`.

4. **Obsidian projection**
   - Replaced `apps/brief/vault_writer.py` heuristic with entity graph projection from `store.get_entity_links()`.
   - Added deprecation stub for the old `extract_entities()` public function.
   - Updated `apps/brief/consumer.py` to fetch and attach entity links to rows.
   - Updated `tests/test_vault_writer.py` and `tests/test_brief_consumer.py`.

5. **mE5-large threshold re-validation**
   - Created `scripts/validate_entity_threshold.py` and fixture `tests/fixtures/entity_validation_sample.json`.
   - Script embeds cross-language entity pairs, computes cosine similarities, recommends a threshold, and writes a markdown report.
   - Added `tests/test_validate_entity_threshold.py`.
   - Generated `.planning/phases/999.3-entity-resolution-cross-language-coverage-and-mE5-large-re-validation/999.3-VERDICT.md`.

## Test results

- `pytest tests/ -q`: 344 passed, 45 skipped.
- No regressions.

## Known limitations / future work

- The current implementation uses exact normalised-name matching for entity identity. Similarity-based cross-language alias merging is documented and threshold-validated but not yet implemented.
- The regex NER is intentionally lightweight; it may miss complex entity mentions that a full NER model would catch.

## Files changed

- `libs/store/sql/003-vectors.sql`
- `libs/store/src/store/_protocol.py`
- `libs/store/src/store/_postgres.py`
- `libs/store/src/store/_inmemory.py`
- `apps/triage/entities.py`
- `apps/triage/worker.py`
- `apps/brief/vault_writer.py`
- `apps/brief/consumer.py`
- `tests/test_store_entities.py`
- `tests/test_triage_entities.py`
- `tests/test_triage_worker.py`
- `tests/test_vault_writer.py`
- `tests/test_brief_consumer.py`
- `tests/test_validate_entity_threshold.py`
- `tests/fixtures/entity_validation_sample.json`
- `scripts/validate_entity_threshold.py`
- `.planning/phases/999.3-entity-resolution-cross-language-coverage-and-mE5-large-re-validation/999.3-VERDICT.md`
- `.planning/STATE.md`
