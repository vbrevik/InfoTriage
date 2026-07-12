---
phase: 08-entity-resolution
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - libs/store/sql/003-vectors.sql
  - libs/store/src/store/_protocol.py
  - libs/store/src/store/_postgres.py
  - libs/store/src/store/_inmemory.py
  - apps/triage/entities.py
  - apps/triage/worker.py
  - apps/brief/vault_writer.py
  - tests/test_entities.py
  - tests/test_store_entities.py
autonomous: true
requirements: [R1, R2, R3, R4, R5, R6, ADR-004, ADR-006]

must_haves:
  truths:
    - "infotriage.entities has id, name, name_norm, lang, type, embedding vector(1024) (ADR-006)"
    - "infotriage.entity_links has id, entity_id FK, item_id FK, mention, lang (ADR-006)"
    - "Entity linking uses mE5-large vectors and a re-validated cosine threshold (backlog 999.3)"
    - "Obsidian files are a projection; Postgres is the system of record (ADR-006)"
    - "NER failures are logged but never block verdict.ready publication (R5)"
    - "Re-processing the same item_id updates (not duplicates) entity_links (R4)"
  artifacts:
    - libs/store/src/store/_protocol.py
    - libs/store/src/store/_postgres.py
    - libs/store/src/store/_inmemory.py
    - apps/triage/entities.py
    - apps/triage/worker.py
    - apps/brief/vault_writer.py
    - tests/test_entities.py
    - tests/test_store_entities.py
  key_links:
    - "003-vectors.sql already declares entities/entity_links/embeddings tables and HNSW indexes"
    - "Phase 5 worker.py calls put_enrichment before publishing verdict.ready; entity extraction hooks after put_enrichment"
    - "vault_writer.py currently uses extract_entities heuristic; replace with entity_links query"
  prohibitions:
    - statement: "MUST NOT use cloud LLM or embedding for entity extraction/vectors"
      status: resolved
      verification: all calls route through local oMLX (ADR-004)
    - statement: "MUST NOT make Obsidian the system of record for entities"
      status: resolved
      verification: entities/entity_links live in Postgres; vault is projection only

---

<objective>
Phase 8 delivers cross-language entity resolution as Postgres truth and projects the
resulting graph into Obsidian. The work spans five waves:

1. **Wave 1 — Store foundation**: add `put_entity`, `get_entity`, `link_entity`,
   `get_entity_links` to the Store Protocol and both Postgres/InMemory implementations.
2. **Wave 2 — NER + embedding + linking module**: build `apps/triage/entities.py` with
   LLM-based NER, mE5-large embedding, and pgvector cosine linking.
3. **Wave 3 — Triage worker integration**: call the entity pipeline after enrichment and
   before `verdict.ready` publication.
4. **Wave 4 — Obsidian projection**: replace `vault_writer.py`'s heuristic with a query
   against `entity_links`, and generate a standalone `Entity Graph.md`.
5. **Wave 5 — mE5-large threshold re-validation**: run the cross-language/cross-modality
   validation that backlog 999.3 requires, document the production threshold.

Output: entity resolution is part of the production scoring path; Obsidian item notes link
to canonical entities and an entity graph note is generated.
</objective>

<execution_context>
@$HOME/.claude/gsd-core/workflows/execute-plan.md
@$HOME/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/08-entity-resolution/08-SPEC.md
@docs/adr/ADR-006-microservice-architecture-entity-resolution.md
@.planning/phases/999.3-entity-resolution-cross-language-coverage-and-mE5-large-re-validation
</context>

<downstream_consumer>
Plans consume:
- Frontmatter (wave, depends_on, files_modified, autonomous)
- Tasks in XML format with read_first and acceptance_criteria
- Verification criteria
- must_haves for goal-backward verification
</downstream_consumer>

## Artifacts this plan produces (this plan)

New symbols introduced by 08-01:
- `libs/store/src/store/_protocol.py` — Protocol methods: `put_entity`, `get_entity`, `link_entity`, `get_entity_links`
- `libs/store/src/store/_postgres.py` — Postgres implementations using pgvector cosine and ON CONFLICT upserts
- `libs/store/src/store/_inmemory.py` — InMemory implementations using dict + stdlib cosine
- `apps/triage/entities.py` — `extract_entities()`, `embed_entity_name()`, `link_mentions()`, `EntityMention` dataclass
- `apps/triage/worker.py` — entity extraction hook after `put_enrichment`
- `apps/brief/vault_writer.py` — `[[Canonical Name]]` wikilinks from `entity_links`; `write_entity_graph()`
- `tests/test_entities.py` — NER/embedding/linking unit tests (InMemory + mocked LLM/embedder)
- `tests/test_store_entities.py` — Store contract tests for entity methods (inmemory + db_live postgres)

<tasks>

<task type="implement" tdd="true">
  <name>Task 1: Add entity Store Protocol methods and failing contract tests</name>
  <files>libs/store/src/store/_protocol.py, libs/store/src/store/_postgres.py, libs/store/src/store/_inmemory.py, tests/test_store_entities.py</files>
  <read_first>
    - libs/store/src/store/_protocol.py (existing put_item/get_item pattern)
    - libs/store/src/store/_postgres.py (put_item ON CONFLICT pattern; find_near_duplicate vector query)
    - libs/store/src/store/_inmemory.py (dict pattern; _cosine_sim helper)
    - libs/store/sql/003-vectors.sql (entities/entity_links schema)
    - tests/test_triage_enrichment.py (parametrized inmemory+postgres fixture pattern)
  </read_first>
  <action>
    First add the unique constraints required for idempotent upserts to
    `libs/store/sql/003-vectors.sql`: `ALTER TABLE infotriage.entities ADD CONSTRAINT
    uk_entities_name_lang UNIQUE (name_norm, lang);` and `ALTER TABLE
    infotriage.entity_links ADD CONSTRAINT uk_entity_links_entity_item_mention UNIQUE
    (entity_id, item_id, mention);`. Then add four methods to the Store Protocol: `put_entity(self, name: str, name_norm: str,
    lang: str, type: str | None, embedding: list[float] | None) -> str` returning the entity
    id; `get_entity(self, entity_id: str) -> dict | None`; `link_entity(self, entity_id: str,
    item_id: str, mention: str, lang: str) -> None`; `get_entity_links(self, item_id: str)
    -> list[dict]`. For Postgres, `put_entity` uses `INSERT ... ON CONFLICT (name_norm, lang)
    DO UPDATE` and returns the id. `link_entity` first deletes any existing links for the
    item_id (or uses ON CONFLICT on (entity_id, item_id, mention)) so re-processing is
    idempotent. `get_entity_links` returns rows with `entity_id`, `name`, `mention`, `lang`.
    InMemoryStore mirrors with dicts and stdlib cosine for any vector search. Create
    `tests/test_store_entities.py` with a parametrized `store` fixture, tests:
    `test_put_get_entity_roundtrip`, `test_put_entity_idempotent`,
    `test_link_entity_idempotent_for_item`, `test_get_entity_links`,
    `test_entity_links_cross_language` (postgres only, verifies two lang variants link to same
    entity). These tests MUST fail initially because the methods do not exist.
  </action>
  <verify>
    <automated>pytest tests/test_store_entities.py -x; test $? -ne 0</automated>
  </verify>
  <done>tests/test_store_entities.py exists and fails (RED) before implementation.</done>
  <acceptance_criteria>
    - tests/test_store_entities.py contains the 5 tests listed above
    - The store fixture is parametrized over "inmemory" and db_live "postgres"
    - `pytest tests/test_store_entities.py -x` exits non-zero (RED)
  </acceptance_criteria>
</task>

<task type="implement" tdd="true">
  <name>Task 2: Implement Store entity methods</name>
  <files>libs/store/src/store/_protocol.py, libs/store/src/store/_postgres.py, libs/store/src/store/_inmemory.py</files>
  <read_first>
    - tests/test_store_entities.py (contract to satisfy)
    - libs/store/src/store/_postgres.py (put_item/get_item/find_near_duplicate patterns)
    - libs/store/sql/003-vectors.sql (entities/entity_links columns)
  </read_first>
  <action>
    Implement the four methods on Protocol, PostgresStore, and InMemoryStore. Postgres:
    `put_entity` inserts into `infotriage.entities (name, name_norm, lang, type, embedding)`
    with `ON CONFLICT (name_norm, lang) DO UPDATE SET name=EXCLUDED.name,
    type=EXCLUDED.type, embedding=COALESCE(EXCLUDED.embedding,
    infotriage.entities.embedding)` and returns `id::text`. This prevents a failed
    re-process embedding from wiping an existing valid vector. Empty embedding lists from
    the caller must be converted to `None` (SQL NULL) before binding. `link_entity` uses
    `ON CONFLICT (entity_id, item_id, mention) DO NOTHING` (the unique constraint added in
    Task 1). `get_entity_links` joins `infotriage.entity_links` to
    `infotriage.entities` on entity_id filtered by item_id. InMemory: `_entities` dict
    keyed by `(name_norm, lang)` storing dicts; `_entity_links` list of tuples;
    `get_entity_links` filters by item_id. All SQL uses `%s` binds; no f-string SQL.
  </action>
  <verify>
    <automated>pytest tests/test_store_entities.py -x && pytest tests/test_store_entities.py -m db_live -x</automated>
  </verify>
  <done>All Store entity methods pass inmemory and db_live contract tests.</done>
  <acceptance_criteria>
    - _protocol.py declares the four methods with type hints
    - _postgres.py and _inmemory.py implement all four methods
    - `pytest tests/test_store_entities.py -x` passes (inmemory)
    - `pytest tests/test_store_entities.py -m db_live -x` passes (postgres)
    - No f-string SQL in the new methods
  </acceptance_criteria>
</task>

<task type="implement" tdd="true">
  <name>Task 3: Build apps/triage/entities.py — NER, embedding, linking</name>
  <files>apps/triage/entities.py, tests/test_entities.py</files>
  <read_first>
    - apps/triage/triage_score.py (llm() function signature, local LLM call pattern)
    - apps/triage/worker.py (where this module will be called)
    - libs/store/src/store/_protocol.py (entity methods from Task 2)
    - tests/test_triage_worker.py (mocking patterns for worker tests)
  </read_first>
  <action>
    Create `apps/triage/entities.py` with:
    - `EntityMention(NamedTuple)`: name, type, lang, confidence
    - `extract_entities(text: str, lang: str) -> list[EntityMention]`: prompt qwen36 to
      return JSON list of objects `{name, type, confidence}`. Supported types:
      PER, ORG, LOC, GPE, MISC. Parse failure logs warning and returns [].
    - `embed_entity_name(name: str, lang: str) -> list[float] | None`: call oMLX embeddings with
      model `intfloat/multilingual-e5-large`, input prefixed with `query: ` (per R2
      convention). Returns 1024-dim vector or `None` on failure. `None` is the value that
      must be passed to the store so Postgres inserts NULL, not an empty list.
    - `link_mentions(store, mentions, item_id, threshold=0.85)`: for each mention, query
      `store.get_entity_links`-like vector search (or add a dedicated
      `find_similar_entity(store, vector, threshold)` helper) to find the best matching
      entity by cosine similarity. If match >= threshold, link to existing entity; else
      `put_entity` a new canonical entity and link to it.
    - `resolve_entities_for_item(store, item_id, title, summary, lang)`: orchestrates
      extract → embed → link, wrapped in try/except so failures are logged but not raised.

    Create `tests/test_entities.py` with mocked LLM/embedder tests:
    - `test_extract_entities_parses_json`
    - `test_extract_entities_malformed_json_returns_empty`
    - `test_link_mentions_creates_new_entity`
    - `test_link_mentions_links_existing_entity`
    - `test_resolve_entities_for_item_swallows_exception`
  </action>
  <verify>
    <automated>pytest tests/test_entities.py -x</automated>
  </verify>
  <done>entities.py module exists with NER, embedding, linking; unit tests pass with mocked dependencies.</done>
  <acceptance_criteria>
    - apps/triage/entities.py defines EntityMention, extract_entities, embed_entity_name, link_mentions, resolve_entities_for_item
    - extract_entities returns typed mentions for valid JSON input
    - Malformed LLM JSON returns empty list and logs warning
    - link_mentions creates new entity when no match and links existing when similarity >= threshold
    - resolve_entities_for_item catches exceptions and logs them
    - tests/test_entities.py passes
  </acceptance_criteria>
</task>

<task type="implement" tdd="true">
  <name>Task 4: Wire entity resolution into triage worker</name>
  <files>apps/triage/worker.py, tests/test_triage_worker.py</files>
  <read_first>
    - apps/triage/worker.py (process_item, on_message, run_consumer)
    - apps/triage/entities.py (resolve_entities_for_item from Task 3)
    - tests/test_triage_worker.py (existing worker tests with mocked store/bus)
  </read_first>
  <action>
    In `apps/triage/worker.py`, after `store.put_enrichment(item_id, ...)` returns and
    before `bus.publish("verdict.ready", ...)`, call
    `await asyncio.to_thread(entities.resolve_entities_for_item, store, item_id,
    item.title, item.summary, item.lang)` (or make `resolve_entities_for_item` async if it
    already awaits I/O). The call must be wrapped in `try/except Exception` and log a
    warning on failure; it must NOT prevent `verdict.ready` publication. Add a test in
    `tests/test_triage_worker.py` that mocks `resolve_entities_for_item` to raise and
    asserts that `bus.publish` is still called.
  </action>
  <verify>
    <automated>pytest tests/test_triage_worker.py -x</automated>
  </verify>
  <done>Triage worker calls entity resolution after enrichment; failures do not block verdict publication.</done>
  <acceptance_criteria>
    - worker.py calls resolve_entities_for_item after put_enrichment and before bus.publish
    - Entity resolution failure is caught and logged; verdict.ready still publishes
    - tests/test_triage_worker.py contains a regression test for this behavior
    - `pytest tests/test_triage_worker.py -x` passes
  </acceptance_criteria>
</task>

<task type="implement" tdd="true">
  <name>Task 5: Replace vault_writer heuristic with entity-graph projection</name>
  <files>apps/brief/vault_writer.py, tests/test_vault_writer.py</files>
  <read_first>
    - apps/brief/vault_writer.py (current extract_entities heuristic and render_wikilinked)
    - libs/store/src/store/_protocol.py (get_entity_links from Task 2)
    - tests/test_vault_writer.py (existing vault writer tests)
  </read_first>
  <action>
    Replace the heuristic `extract_entities()` usage in `write_item_obsidian()` and
    `render_sab_obsidian()` with a call to `store.get_entity_links(item_id)` (passed in the
    item dict or fetched from a store instance). Use the canonical `name` from the link
    rows to build `[[Name]]` wikilinks. Keep `render_wikilinked()` but feed it canonical
    names. Add `write_entity_graph(store, vault_path)` that queries distinct entities with
    link counts and aliases (grouped by name_norm) and writes `Entity Graph.md` with one
    section per canonical entity listing aliases and linked item count. Update
    `tests/test_vault_writer.py` to pass entity_links in item dicts and assert canonical
    wikilinks appear.
  </action>
  <verify>
    <automated>pytest tests/test_vault_writer.py -x</automated>
  </verify>
  <done>vault_writer projects canonical entities from Postgres; Entity Graph.md is generated.</done>
  <acceptance_criteria>
    - vault_writer.py no longer uses the heuristic extract_entities for wikilinks
    - Item notes contain [[Canonical Name]] links from entity_links
    - write_entity_graph produces Entity Graph.md with entity aliases and link counts
    - tests/test_vault_writer.py passes
  </acceptance_criteria>
</task>

<task type="validate" tdd="false">
  <name>Task 6: mE5-large threshold re-validation</name>
  <files>scripts/validate_entity_threshold.py, .planning/phases/999.3-entity-resolution-cross-language-coverage-and-mE5-large-re-validation/999.3-VERDICT.md</files>
  <read_first>
    - .planning/research/spark-model-benchmark-2026-07-09.md (if exists)
    - docs/adr/ADR-006-microservice-architecture-entity-resolution.md (R3 threshold note)
    - .planning/phases/00-concept-spike/SPIKE-FINDINGS.md (R3 findings)
  </read_first>
  <action>
    Create `scripts/validate_entity_threshold.py` that:
    1. Loads a multi-day, multi-language corpus from `infotriage.articles` (or a supplied
       JSON file) covering at least two languages (e.g., en/no/ru).
    2. Runs `extract_entities()` and `embed_entity_name()` on each mention.
    3. Computes pairwise cosine similarities for known same-entity cross-language pairs
       (e.g., NATO/НАТО) and known distinct pairs (e.g., Trump/Putin).
    4. Prints a threshold recommendation and writes a markdown report to
       `.planning/phases/999.3-entity-resolution-cross-language-coverage-and-mE5-large-re-validation/999.3-VERDICT.md`.
    Run the script against a live test DB (or a fixture corpus if DB unavailable) and update
    the default `LINK_THRESHOLD` in `apps/triage/entities.py` if the validated value
    differs from 0.85.
  </action>
  <verify>
    <automated>python scripts/validate_entity_threshold.py --corpus tests/fixtures/entity_validation_sample.json --report .planning/phases/999.3-entity-resolution-cross-language-coverage-and-mE5-large-re-validation/999.3-VERDICT.md</automated>
  </verify>
  <done>mE5-large entity-link threshold is measured on cross-language data and documented.</done>
  <acceptance_criteria>
    - scripts/validate_entity_threshold.py exists and runs end-to-end
    - Report file 999.3-VERDICT.md documents the chosen threshold and cross-language coverage
    - Default LINK_THRESHOLD in entities.py matches the validated value
  </acceptance_criteria>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| LLM output → entities | NER text and type originate from qwen36; may hallucinate mentions |
| embedding output → pgvector | mE5-large vectors from local oMLX; tampering requires host access |
| Postgres → Obsidian | Obsidian files are derived from Postgres; operator may edit files, but canonical truth remains in DB |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-08-01 | Information disclosure | LLM NER output | medium | mitigate | No PII handling change; NER output is stored in Postgres only |
| T-08-02 | Tampering | entity_links upsert | high | mitigate | ON CONFLICT / delete-before-insert prevents duplicate links on re-process |
| T-08-03 | Denial of service | embedding call failure | medium | mitigate | Embedding failure is caught; entity created with NULL vector, linking disabled for that entity |
| T-08-04 | Elevation | none | low | accept | No new network-facing surface beyond existing worker/vault_writer |
</threat_model>

<verification>
- `pytest tests/test_store_entities.py -x` (inmemory) and `-m db_live -x` (postgres) green
- `pytest tests/test_entities.py -x` green
- `pytest tests/test_triage_worker.py -x` green
- `pytest tests/test_vault_writer.py -x` green
- `scripts/validate_entity_threshold.py` runs and produces 999.3-VERDICT.md
- Full suite: `pytest tests/ -q` returns 329 pass / 39 skip baseline (or better)
</verification>

<success_criteria>
- Store Protocol has `put_entity`, `get_entity`, `link_entity`, `get_entity_links`
- Postgres + InMemory implementations pass contract tests
- `apps/triage/entities.py` extracts typed mentions, embeds with mE5-large, links via pgvector
- Triage worker calls entity resolution after enrichment; failures do not block verdict.ready
- `vault_writer.py` uses canonical entities from `entity_links`
- `Entity Graph.md` is generated in the Obsidian vault
- mE5-large link threshold is re-validated and documented in 999.3-VERDICT.md
- Full pytest suite remains green
</success_criteria>

<output>
Create `.planning/phases/08-entity-resolution/08-01-SUMMARY.md` when done
</output>
