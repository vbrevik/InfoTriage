---
phase: 08-entity-resolution
plan: 02
type: plan
wave: 2-6
depends_on: [08-01]
files_modified:
  - apps/brief/vault_writer.py
  - tests/test_vault_writer.py (new tests for write_entity_graph)
  - scripts/validate_entity_threshold.py (run to produce report)
  - .planning/phases/999.3-entity-resolution-cross-language-coverage-and-mE5-large-re-validation/999.3-VERDICT.md (generated)
  - apps/triage/entities.py (potentially: LINK_THRESHOLD update)
autonomous: true
requirements: [R5, R6, ADR-004, ADR-006]

---

# Phase 8 — Waves 2-6 Completion Plan

## Current State Assessment

**Wave 1 (Store foundation):** DONE
- `put_entity`, `get_entity`, `link_entity`, `get_entity_links` in Store Protocol + Postgres + InMemory
- Unique constraints in `003-vectors.sql`
- Contract tests in `tests/test_store_entities.py`
- `tests/`: 344 passed, 45 skipped

**Wave 2 (LLM NER):** DONE
- `apps/triage/entities.py` with qwen36-based NER (PER/ORG/LOC/GPE/MISC)
- Structured JSON parsing with markdown fence tolerance
- Fallback to empty list on parse/LLM failure
- mE5-large embedding with `query:` prefix convention
- Tests: `tests/test_entities.py` covers all paths

**Wave 3 (Triage worker integration):** DONE
- `worker.py` calls `resolve_entities_async` after `put_enrichment` and before `verdict.ready`
- Wrapped in `try/except` — failures logged, never block scoring
- Worker test regression test exists

**Wave 4 (Vault writer projection):** DONE
- `vault_writer.py` uses `_entity_names()` pulling canonical names from `item['entities']`
- `consumer.py:106` attaches `store.get_entity_links(item_id)` to each row
- Heuristic `extract_entities()` is deprecated
- `render_wikilinked()` uses canonical entity names

**Wave 5 (Entity Graph.md):** ✅ DONE
- `write_entity_graph(items, vault_path)` and `write_entity_graph_from_store(store, vault_path)` exist in `vault_writer.py`
- `write_vault_digest()` calls `write_entity_graph_from_store()` after writing item notes and SAB
- `render_entity_graph()` (row-based) and `render_entity_graph_from_store()` (store-backed) both render type/lang and language-tagged aliases
- `Store.get_all_entities()` returns canonical entities with a sorted `aliases` list (`"NATO (en)"`, `"НАТО (ru)"`) and `link_count`
- `alias_count` was removed from the API (redundant with `len(aliases)`)

**Wave 5 (mE5-large threshold validation):** ✅ DONE
- `scripts/validate_entity_threshold.py` produced `999.3-VERDICT.md` in `offline` mode
- Recommended `LINK_THRESHOLD = 0.92` adopted in `apps/triage/entities.py`
- `libs/store/src/store/_postgres.py::find_similar_entity()` default threshold is 0.92

**Wave 6 (Contract tests):** ✅ DONE
- `tests/test_validate_entity_threshold.py`, `tests/test_entities.py`, `tests/test_store_entities.py`, `tests/test_triage_worker.py`, and `tests/test_vault_writer.py` all green
- Focused Phase 8 subset (entity + store + worker + vault + validation): 82 tests, 73 passed, 9 skipped, 5.09s
- Full non-live suite (`-m 'not db_live and not rabbitmq'`): 394 passed, 48 deselected in 24.17s

## Execution Plan: Waves 2-6 Remaining Work

### Wave 5-A: Entity Graph.md Generation (Priority: HIGH)

**File to modify:** `apps/brief/vault_writer.py`
**Tests to add:** `tests/test_vault_writer.py`

#### Implementation

Add `write_entity_graph(store, vault_path)` function to `vault_writer.py`:

```python
def write_entity_graph(store, vault_path: Path) -> Path:
    """Generate a standalone Entity Graph.md note from the canonical entity graph.

    Queries all entities with their aliases (grouped by name_norm across languages),
    linked item counts, and entity links. Writes Entity Graph.md to the vault.

    Skips silently if INFOTRIAGE_VAULT_PATH is unset and vault_path is not provided.
    """
    vault_path = Path(vault_path)
    vault_path.mkdir(parents=True, exist_ok=True)

    # Query all distinct entities with alias counts and link counts
    # Uses get_entity_links to aggregate — the store already has the data
    rows = store.get_entity_links.__self__.get_all_entity_links() if hasattr(store.get_entity_links.__self__, 'get_all_entity_links') else []

    # If the store doesn't have a "get all" method, iterate a known entity list
    # This is a design decision: Phase 8 could add get_all_entities() to the protocol
    # OR Entity Graph could be built from vault files already written.
    # For minimal scope: build from existing vault item notes' entity wikilinks.
    ...
```

**Design decision (Boundary):** Should `write_entity_graph` query the database directly or parse existing vault files?
- **Recommendation:** Query the database via a new `get_all_entities()` protocol method. This is the correct approach because Postgres is the system of record (ADR-006) and vault files are projection only. A stale vault wouldn't produce a valid entity graph.
- **Protocol change:** Add `get_all_entities(self) -> list[dict]` to the Store Protocol, PostgresStore, and InMemoryStore. This is a read-only aggregation query (SELECT with GROUP BY).

#### Protocol extension: `get_all_entities()`

Add to `_protocol.py`:
```python
def get_all_entities(self) -> list[dict]:
    """Return all canonical entities with language-tagged aliases and link count."""
    raise NotImplementedError
```

Postgres implementation:
```sql
SELECT e.id, e.name, e.name_norm, e.lang, e.type,
       ARRAY_AGG(DISTINCT el.mention || ' (' || el.lang || ')') AS aliases,
       COUNT(DISTINCT el.item_id) AS link_count
FROM infotriage.entities e
LEFT JOIN infotriage.entity_links el ON e.id = el.entity_id
GROUP BY e.id
ORDER BY link_count DESC, e.name_norm;
```

#### Entity Graph.md format

```markdown
# InfoTriage · Entity Graph

_Generated from Postgres canonical entity store._

## Entities

### NATO
- **Type:** ORG
- **Aliases:** NATO (en), НАТО (ru), NATO (no)
- **Linked items:** 285

### Putin
- **Type:** PER
- **Aliases:** Putin (en), Путин (ru)
- **Linked items:** 142
```

#### Update `write_vault_digest()`

After writing item notes and SAB, call:
```python
write_entity_graph(store, vault_path)
paths.append(vault_path / "Entity Graph.md")
```

#### Tests

In `tests/test_vault_writer.py`:
- `test_write_entity_graph_creates_file` — mock store, call write_entity_graph, assert Entity Graph.md exists
- `test_write_entity_graph_includes_aliases` — verify aliases are grouped by name_norm
- `test_write_entity_graph_link_counts` — verify item counts are accurate

### Wave 5-B: mE5-large Threshold Validation (Priority: HIGH)

**File to run:** `scripts/validate_entity_threshold.py`
**Output:** `.planning/phases/999.3-entity-resolution-cross-language-coverage-and-mE5-large-re-validation/999.3-VERDICT.md`

#### Execution steps

1. **Check environment:** Verify mE5-large weights exist locally (`~/.cache/huggingface/` or `~/.omlx/models/`)
2. **Run validation:** `python scripts/validate_entity_threshold.py --report <path-to-verdict>`
   - Default mode is `offline` (uses local safetensors)
   - This is the RECOMMENDED mode per the script docstring — no HTTP dependency
3. **Review verdict:** Check GO/PARTIAL/NO-GO outcome and recommended `LINK_THRESHOLD`
4. **Update entities.py if needed:** If the validated threshold differs from 0.85, update `LINK_THRESHOLD` in `apps/triage/entities.py`
5. **If offline mode unavailable:** Fall back to `--mode http` (requires oMLX running) or `--mode synthetic --allow-synthetic` (with explicit WARNING that result is invalid for production)

#### Fallback: no local model weights

If mE5-large is not cached locally:
1. Download via HuggingFace: `huggingface-cli download intfloat/multilingual-e5-large`
2. Or use `--mode http` with the local oMLX endpoint
3. Or use `--corpus tests/fixtures/entity_validation_sample.json --mode synthetic --allow-synthetic` for development-only validation (clearly marked invalid in report)

### Wave 6: Contract Tests & Regression (Priority: MEDIUM)

**Scope:** Ensure the full suite remains green after Wave 5-A changes.

#### Steps
1. Run `pytest tests/test_vault_writer.py -x` after adding `write_entity_graph` tests
2. Run `pytest tests/test_entities.py -x` (should still pass)
3. Run `pytest tests/test_store_entities.py -x` (should still pass)
4. Run full suite: `pytest tests/ -q` — verify 344 passed / 45 skipped baseline maintained

#### Additional tests to add for Wave 5-A
- Test that `write_entity_graph` with empty store produces a valid (but empty) Entity Graph.md
- Test that `write_entity_graph` skips gracefully when vault_path doesn't exist (mkdir + write)
- Integration test: write items → resolve entities → write vault → write entity graph → verify graph contains all entities

## Execution Order

```
Wave 5-A (Entity Graph.md) → Wave 5-B (threshold validation) → Wave 6 (full regression)
```

Wave 5-A and 5-B are INDEPENDENT and could run in parallel if two agents are available.

## Closeout Notes

Phase 8 Wave 5 closed out in commit `b9aebae`. The entity graph projection and
mE5-large threshold validation are now part of the production code path. Phase 8
is functionally complete; next is Phase 9 (RAG recall) execution.

## Acceptance Criteria

- [x] `get_all_entities()` added to Store Protocol + PostgresStore + InMemoryStore
- [x] `write_entity_graph_from_store(store, vault_path)` queries the store and writes `Entity Graph.md`
- [x] `consumer.py` passes the Store into `write_vault_digest()` so production uses the store-backed graph
- [x] `write_vault_digest()` keeps a backward-compatible row-based `write_entity_graph()` path for callers without a Store
- [x] Entity Graph.md lists entities with type/lang tags, language-tagged aliases, and linked item counts
- [x] `alias_count` removed from the `get_all_entities()` API (redundant with `len(aliases)`)
- [x] Row-based `render_entity_graph()` also renders entity type and language
- [x] 999.3-VERDICT.md generated from real mE5-large offline vectors (T*=0.92)
- [x] LINK_THRESHOLD in entities.py updated to 0.92 (validated value)
- [x] tests/test_vault_writer.py includes tests for `write_entity_graph` and `write_entity_graph_from_store`
- [x] tests/test_store_entities.py includes tests for `get_all_entities`
- [x] Full pytest suite (excluding live db/rabbitmq markers): 405 passed, 43 skipped

## Risk Assessment

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| mE5-large weights not cached | Medium | Provide `--mode http` fallback; document download step |
| get_all_entities() adds store protocol surface | Low | It's read-only; adds one simple aggregation query |
| Entity Graph.md format diverges from Obsidian conventions | Low | Use standard Obsidian wikilink syntax `[[Entity]]` |
| Validation takes too long on large corpus | Low | Default corpus is only 12 pairs; --corpus-from-postgres is opt-in |

## Files to Touch

| File | Change |
|------|--------|
| `apps/brief/vault_writer.py` | Add `write_entity_graph()`, update `write_vault_digest()` |
| `libs/store/src/store/_protocol.py` | Add `get_all_entities()` method |
| `libs/store/src/store/_postgres.py` | Implement `get_all_entities()` with aggregation SQL |
| `libs/store/src/store/_inmemory.py` | Implement `get_all_entities()` with dict aggregation |
| `tests/test_vault_writer.py` | Tests for `write_entity_graph` |
| `.planning/phases/999.3-.../999.3-VERDICT.md` | Generated by running validation script |
| `apps/triage/entities.py` | Potentially update `LINK_THRESHOLD` (only if validation differs) |
