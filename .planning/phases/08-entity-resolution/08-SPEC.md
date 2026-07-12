# Phase 08: Entity Resolution — Specification

**Created:** 2026-07-12
**Ambiguity score:** 0.13 (gate: ≤ 0.20)
**Requirements:** 6 locked (R1–R6)
**Depends on:** Phase 5 (triage app, embeddings, enrichment)

## Goal

Make PostgreSQL the canonical system of record for cross-modality, cross-language entity
tracking, and project the resulting entity graph into Obsidian as a read-only view. Phase 8
replaces the placeholder heuristic entity extraction in `apps/brief/vault_writer.py` with a
proper pipeline: NER → embedding → pgvector linking → canonical `entities`/`entity_links`
tables → Obsidian `[[Entity]]` wikilinks and a standalone entity-graph note.

## Background

Phase 0 spike R3 proved the mechanism on real data: 285 entities from 144 items, 599
`entity_links`; NATO merged to a single `entity_id` across 5 TASS items; control entities
stayed distinct (Trump ≠ Putin). The spike used `BAAI/bge-m3` vectors, but Phase 5 locked
`intfloat/multilingual-e5-large` (mE5-large) @ 0.84 for article dedup. ADR-006 therefore
requires Phase 8 to **re-validate** the 0.85 entity-link threshold on mE5-large vectors before
production. The schema (`entities`, `entity_links`, `embeddings` with HNSW cosine indexes)
already exists from Phase 2 (`libs/store/sql/003-vectors.sql`); it has not yet been populated
by the production pipeline.

`apps/brief/vault_writer.py` currently uses a lightweight heuristic (`extract_entities`) to
inject `[[Entity]]` wikilinks. This is explicitly documented as a placeholder to be replaced
by Phase 8.

## Requirements

1. **Entity extraction (NER)**: Extract typed entity mentions from article title + summary using the local LLM.
   - Current: no production NER; `vault_writer.py` uses a regex/proper-noun heuristic
   - Target: a new `apps/triage/entities.py` module exposes `extract_entities(text: str, lang: str) -> list[EntityMention]` where each mention has `name`, `type` (PER/ORG/LOC/GPE/MISC), and `confidence`. The LLM prompt returns structured JSON; parse failures fall back to an empty list. All processing is local (ADR-004).
   - Acceptance: Given a Norwegian article about NATO, the function returns `{"name": "NATO", "type": "ORG"}`; given a Russian article about НАТО, it returns the Cyrillic mention with `lang="ru"`.

2. **Entity embedding**: Compute an mE5-large vector for each canonical entity name.
   - Current: `infotriage.entities.embedding` exists but is never written
   - Target: `intfloat/multilingual-e5-large` embeds the normalized entity name with the `query:` prefix (per R2 spike convention). The vector is 1024-dim and written to `entities.embedding`.
   - Acceptance: Two mentions of the same entity in different languages produce vectors whose cosine similarity is ≥ the validated link threshold.

3. **Entity linking / canonicalization**: Merge mentions into canonical entities via pgvector HNSW cosine similarity.
   - Current: `entity_links` table exists but has no production writes
   - Target: `EntityResolver.link_mentions(mentions, item_id)` queries `infotriage.entities` ordered by cosine distance; if the best match is ≥ `LINK_THRESHOLD` (default 0.85, re-validated on mE5-large), the mention is attached to that entity; otherwise a new `entities` row is created. The threshold is configurable via `ENTITY_LINK_THRESHOLD` env var.
   - Acceptance: "NATO" (en), "НАТО" (ru), and "NATO" (no) mentions link to the same `entity_id`; "Trump" and "Putin" remain distinct entities.

4. **Store protocol methods**: Add `put_entity`, `get_entity`, `link_entity`, `get_entity_links` to the Store Protocol and both Postgres/InMemory implementations.
   - Current: Store has no entity methods
   - Target: Protocol methods with typed signatures; Postgres implementation uses `ON CONFLICT` upserts and pgvector cosine queries; InMemory implementation uses dict lookups and stdlib cosine.
   - Acceptance: Contract tests pass for both inmemory and db_live Postgres stores; idempotent upserts; cross-language linking test passes on Postgres.

5. **Triage worker integration**: Extract and link entities for every non-duplicate article during scoring.
   - Current: `apps/triage/worker.py` scores and enriches but does not touch entities
   - Target: after `put_enrichment()` and before publishing `verdict.ready`, call the entity extractor + resolver for the article. Entity extraction is best-effort: failures are logged but do not block scoring or verdict publication.
   - Acceptance: Process an `item.ingested` event → `infotriage.entities` and `infotriage.entity_links` have rows; `verdict.ready` still publishes even if NER fails.

6. **Obsidian projection**: Replace the heuristic wikilink generator with a projection of the canonical entity graph.
   - Current: `vault_writer.py` uses `extract_entities()` heuristic
   - Target: `vault_writer.py` reads `entity_links` for the item and emits `[[Canonical Name]]` wikilinks. A new `write_entity_graph(vault_path)` produces a standalone `Entity Graph.md` note listing canonical entities, aliases by language, and linked item counts.
   - Acceptance: An item note links `[[NATO]]` instead of `[[Nato]]`; `Entity Graph.md` contains a "NATO" section with aliases "НАТО", "NATO" and a count of linked items.

## Boundaries

**In scope:**
- `apps/triage/entities.py` — NER + embedding + linking module
- `libs/store` — entity store protocol methods + SQL idempotency
- `apps/triage/worker.py` — hook entity extraction into scoring pipeline
- `apps/brief/vault_writer.py` — replace heuristic with entity-graph projection
- Tests: unit (InMemory), contract (Postgres), cross-language integration
- mE5-large re-validation of the 0.85 link threshold on a multi-day, multi-language corpus

**Out of scope:**
- Standing auto-wiki / on-demand synthesis — Phase 10 (Wiki-LLM)
- RAG recall over entities — Phase 9
- SP-COP network visualization — ADR-005, parallel non-blocking spike
- Admiralty reliability scoring — backlog
- SOCMINT / Telegram / AIS — Phase 11
- CNR alerting — Phase 12

## Constraints

- **ADR-004**: all LLM / embedding calls are local (qwen36 via oMLX, mE5-large via oMLX). No cloud.
- **mE5-large re-validation**: the 0.85 threshold from R3 (bge-m3) is NOT automatically valid for mE5-large. Phase 8 must measure and document the mE5-large threshold before using it in production.
- **Postgres truth**: `infotriage.entities` is the system of record; Obsidian files are a projection only.
- **Best-effort NER**: entity extraction failures must never block scoring or verdict publication.
- **Idempotency**: re-processing the same `item_id` must update (not duplicate) entity links.
- **No new paid services**: all dependencies free/self-hosted.

## Acceptance Criteria

- [ ] `apps/triage/entities.py` exists with `extract_entities()`, `embed_entity_name()`, `link_mentions()`
- [ ] LLM NER returns typed mentions (PER/ORG/LOC/GPE/MISC) as structured JSON
- [ ] mE5-large entity vectors are 1024-dim and written to `infotriage.entities.embedding`
- [ ] `LINK_THRESHOLD` is re-validated on mE5-large; default documented in code and env
- [ ] Cross-language mentions (e.g., NATO/НАТО/NATO-no) link to the same `entity_id`
- [ ] Control entities (e.g., Trump vs Putin) remain distinct
- [ ] Store Protocol has `put_entity`, `get_entity`, `link_entity`, `get_entity_links`
- [ ] Postgres + InMemory implementations pass contract tests
- [ ] Triage worker calls entity extraction after enrichment and before `verdict.ready`
- [ ] Entity extraction failure does not block `verdict.ready`
- [ ] `vault_writer.py` uses canonical entities from `entity_links` instead of the heuristic
- [ ] `Entity Graph.md` is generated in the Obsidian vault
- [ ] Full pytest suite remains green (329 pass / 39 skip baseline)

## Edge Coverage

**Coverage:** 10/10 applicable edges covered · 0 unresolved

| Category | Requirement | Status | Resolution / Reason |
|----------|-------------|--------|---------------------|
| Empty input | R1 | ✅ covered | Article with no extractable entities → empty mentions list; no crash |
| LLM parse failure | R1 | ✅ covered | Malformed JSON → fallback to empty list; logged at WARNING |
| First mention | R3 | ✅ covered | No match in `entities` → create new row |
| Near-duplicate names | R3 | ✅ covered | Cosine threshold separates distinct people |
| Cross-language merge | R3 | ✅ covered | mE5-large validation test required |
| Re-processing same item | R4/R5 | ✅ covered | `link_entity` upsert removes old links for item_id before inserting new ones |
| Embedding failure | R2/R5 | ✅ covered | Embedding failure logged; entity still created with NULL vector (linking disabled for that entity) |
| Store failure | R5 | ✅ covered | Entity store failure logged; does not block verdict publication |
| Obsidian vault absent | R6 | ✅ covered | Graph note skipped if `INFOTRIAGE_VAULT_PATH` unset |
| Concurrent items | R3/R5 | ✅ covered | Postgres row-level locks + ON CONFLICT; InMemory single-threaded |

## Prohibitions (must-NOT)

**Coverage:** 4/4 applicable prohibitions resolved · 0 unresolved

| Prohibition (must-NOT statement) | Requirement | Status | Verification / Reason |
|----------------------------------|-------------|--------|------------------------|
| MUST NOT use cloud LLM/embedding for NER or entity vectors | R1, R2 | resolved | ADR-004; all calls route through local oMLX |
| MUST NOT make Obsidian the system of record for entities | R6 | resolved | `entities`/`entity_links` live in Postgres; vault is projection only |
| MUST NOT block `verdict.ready` on entity extraction failure | R5 | resolved | try/except around entity pipeline; log + continue |
| MUST NOT duplicate entity_links on re-processing the same item | R4, R5 | resolved | delete links for item_id before insert (or ON CONFLICT upsert) |

## Ambiguity Report

| Dimension          | Score | Min  | Status | Notes |
|--------------------|-------|------|--------|-------|
| Goal Clarity       | 0.90  | 0.75 | ✓      | Postgres truth + Obsidian projection clearly scoped |
| Boundary Clarity   | 0.88  | 0.70 | ✓      | Explicit out-of-scope list (Wiki-LLM, RAG, SP-COP) |
| Constraint Clarity | 0.85  | 0.65 | ✓      | ADR-004, mE5-large re-validation, best-effort NER |
| Acceptance Criteria| 0.82  | 0.70 | ✓      | 13 pass/fail criteria across 6 requirements |
| **Ambiguity**      | 0.13  | ≤0.20| ✓      | Gate passed |

## Interview Log

| Round | Perspective    | Question summary                                   | Decision locked                                      |
|-------|----------------|---------------------------------------------------|--------------------------------------------------------|
| 1     | Researcher     | Where does entity resolution live?                | `apps/triage/entities.py` + Store methods; triggered by triage worker |
| 1     | Researcher     | Which embedding model?                            | mE5-large (locked by Phase 5); threshold re-validated in Phase 8 |
| 2     | Simplifier     | Minimum viable scope?                             | NER + linking + Store methods + vault projection; no SP-COP, no Wiki-LLM |
| 2     | Boundary       | What happens if NER fails?                        | Log and continue; never block scoring |
| 3     | Boundary Keeper| What is explicitly out?                           | Wiki-LLM, RAG recall, SP-COP viz, Admiralty, SOCMINT, CNR alerts |

---

*Phase: 08-entity-resolution*
*Spec created: 2026-07-12*
*Next step: create 08-PLAN.md with waves, tasks, and verification criteria*
