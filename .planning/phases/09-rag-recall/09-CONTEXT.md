# Phase 9: RAG recall - Context

**Gathered:** 2026-07-13
**Status:** Ready for planning

<domain>
## Phase Boundary

Add a CCIR pre-filter to the triage worker so clearly off-topic items skip the LLM scorer, and build a thematic recall CLI (`recall.py`) over the durable InfoTriage corpus. The pre-filter compares each incoming article's mE5-large embedding against pre-computed CCIR vectors and short-circuits to `skip` when the maximum cosine similarity is below a calibrated threshold τ. The recall tool lets the operator ask "what do we know about X since date?" and returns cited articles (title, source, URL, score) with optional local qwen36 synthesis.

</domain>

<spec_lock>
## Requirements (locked via ROADMAP.md)

**2 success criteria are locked.** See `.planning/ROADMAP.md` §Phase 9 for full requirements, boundaries, and acceptance criteria.

Downstream agents MUST read `.planning/ROADMAP.md` §Phase 9 before planning or implementing. Requirements are not duplicated here.

**In scope:**
- CCIR vector representation derived from `ccir.md`
- Pre-filter cosine gate in `apps/triage/worker.py` before `score_item()`
- Audit logging of pre-filter skips in `infotriage.audit`
- Thematic recall CLI (`scripts/recall.py` or `apps/triage/recall.py`) with `--topic`, `--since`, `--json`, `--obsidian`
- Citation of `articles.id` and `url` per recall result
- Local qwen36 synthesis for recall summaries

**Out of scope (deferred):**
- SAB `/recall` HTTP endpoint — future enhancement, not required for Phase 9
- DGX Spark synthesis — Phase 10 (Wiki-LLM) only; recall uses local qwen36
- Full-body search by default — recall searches `title + summary + enrichment.why`; full-body expansion is an optional flag
- Admiralty reliability scoring — post-M2 backlog
- Multi-user / team sharing — M3

</spec_lock>

<decisions>
## Implementation Decisions

### CCIR vector representation

- **D-01:** One vector per CCIR (PIR-1..6, FFIR-1..3, SIR-1..3) derived from the corresponding section text in `ccir.md`. The section heading + bullet text is embedded with the `query:` prefix (asymmetric retrieval convention for mE5-large) and stored in a new `infotriage.ccir_vectors` table.
- **D-02:** `ccir_vectors` schema: `ccir_id TEXT PRIMARY KEY`, `embedding vector(1024) NOT NULL`, `model TEXT NOT NULL`, `updated_at TIMESTAMPTZ DEFAULT NOW()`. A helper function populates/updates vectors on demand from the current `ccir.md`.
- **D-03:** If a CCIR section is long, truncate to the first ~512 tokens before embedding (same input window as item dedup). No multi-vector per CCIR in Phase 9.

### Pre-filter threshold τ

- **D-04:** Start with a conservative fixed threshold **τ = 0.50**. Goal: skip only *clearly* off-topic items; borderline items still go to the LLM.
- **D-05:** Threshold is configurable via env var `INFOTRIAGE_PREFILTER_THRESHOLD` (default 0.50). This allows live tuning without a code change.
- **D-06:** Validation method: sample items where pre-filter says skip and compare to the eventual LLM score. If the LLM also returns `ccir=none`, the pre-filter is correct. Tune threshold upward if too many false negatives; downward if too many false positives.

### Pipeline integration

- **D-07:** Pre-filter runs inside `apps/triage/worker.py` **after** the item embedding is computed (which is already done for dedup) and **before** `score_item()` is called.
- **D-08:** If `max(cosine(item, ccir_vector)) < τ`, the worker writes an enrichment row with `ccir=none, cnr=none, score=0, bucket=skip, why="pre-filter: off-topic"`, stores the embedding, and publishes `verdict.ready` with `bucket=skip`. No LLM call is made.
- **D-09:** If the item passes the pre-filter (similarity ≥ τ), the worker proceeds to the normal LLM scoring path. The pre-filter does not change the score or bucket of passed items.
- **D-10:** Pre-filter failures (embedding call, DB write) must not silently skip items; they should fall back to the normal LLM scoring path and log a warning.

### Audit logging

- **D-11:** Extend `infotriage.audit` with a `details JSONB` column to capture structured metadata. The existing columns (`op`, `table_name`, `item_id`, `ts`) are preserved.
- **D-12:** On pre-filter skip, write: `op='pre_filter_skip'`, `table_name='enrichment'`, `item_id=<item_id>`, `details={"max_similarity": <float>, "threshold": <float>, "best_ccir": "<ccir_id>"}`.
- **D-13:** If extending the audit table is blocked by migration complexity, fallback: write the same row with `details` omitted and log the structured metadata via the JSON logger.

### Recall search scope

- **D-14:** Default recall searches `articles.title + articles.summary + enrichment.why` for items with `bucket != skip` and `ts >= --since`.
- **D-15:** The recall query embeds the user's `--topic` with the `query:` prefix and performs a cosine-similarity search against the existing `infotriage.embeddings` table (item vectors).
- **D-16:** Optional `--include-body` flag fetches the article body from blobs and includes it in the context sent to the synthesis LLM. Default is off.
- **D-17:** Optional filters: `--ccir PIR-1`, `--bucket keep|maybe`, `--limit N`, `--since 7d|2026-07-01`.

### Recall output format

- **D-18:** `recall.py` is a CLI tool. Default output is Markdown to stdout with a ranked list of articles (title, source, URL, CCIR, score, similarity).
- **D-19:** `--json` returns structured JSON (list of result objects with `item_id`, `url`, `title`, `source`, `score`, `similarity`).
- **D-20:** `--obsidian <path>` writes a Markdown note with front matter to the Obsidian vault. The note contains the ranked list and, if synthesis is requested, a synthesized summary with citations.
- **D-21:** Synthesis is triggered by `--synthesize` and uses local qwen36 only. The prompt instructs the model to cite every claim with `[item_id]` and to answer only from the provided context.

### DGX synthesis trigger

- **D-22:** Phase 9 recall uses local qwen36 for all synthesis. DGX Spark is explicitly out of scope.
- **D-23:** A future Phase 10 (Wiki-LLM) may add a `--dgx` flag to `recall.py`; the code should be structured so that adding a second LLM backend is a small change.

### Embedding reuse

- **D-24:** Reuse the existing `infotriage.embeddings` table for item vectors. The pre-filter compares the item vector against `infotriage.ccir_vectors`.
- **D-25:** Same mE5-large model for both. Items use `passage:` prefix; CCIR vectors use `query:` prefix (standard mE5 asymmetric retrieval).
- **D-26:** No new embedding table for recall. If recall needs a different vector representation later (e.g., chunking), that is a Phase 10 concern.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & boundaries
- `.planning/ROADMAP.md` §Phase 9 — Locked goal, success criteria, dependencies
- `.planning/REQUIREMENTS.md` — A-1 (CCIR pre-filter), PR-6 (RAG-assisted SAB)

### Architecture decisions
- `docs/ARCHITECTURE.md` — ADR-001 (Postgres canonical store), ADR-004 (local LLM only), ADR-006 (pgvector HNSW cosine, mE5-large)

### Phase dependencies
- `.planning/phases/05-triage-app/05-CONTEXT.md` — `worker.py` pipeline, `score_item()`, `put_embedding`, `find_near_duplicate`
- `.planning/phases/08-entity-resolution/08-CONTEXT.md` — entity linking, `ccir.md` structure

### Existing code (to adapt)
- `apps/triage/worker.py` — `process_item()`; pre-filter inserts after embedding, before `score_item()`
- `apps/triage/triage_score.py` — `score_item()`; unchanged except pre-filter short-circuit
- `libs/store/src/store/_protocol.py` — add `find_similar_ccir` / recall helpers here
- `libs/store/src/store/_postgres.py` — implement vector search against `infotriage.embeddings`
- `libs/store/sql/003-vectors.sql` — `infotriage.embeddings` HNSW index
- `libs/store/sql/004-audit.sql` — `infotriage.audit` table
- `ccir.md` — source of CCIR section text for vector generation

### Infrastructure reference
- `docker-compose.yml` — triage container env vars; add `INFOTRIAGE_PREFILTER_THRESHOLD`

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `apps/triage/worker.py` `process_item()` — proven async pipeline; embedding is computed before scoring
- `apps/triage/worker.py` `get_embedding()` — mE5-large embedding call via oMLX/Spark
- `libs/store/src/store/_postgres.py` `find_near_duplicate()` — pgvector cosine search pattern
- `libs/store/sql/003-vectors.sql` — HNSW cosine index on `infotriage.embeddings`
- `libs/store/sql/004-audit.sql` — audit table schema

### Established Patterns
- All SQL uses `%s` bind params — never f-strings (V5/T-02-01)
- `register_vector()` before vector queries (Pitfall 1)
- Async blocking calls wrapped in `asyncio.to_thread()`
- Store Protocol methods added to `_protocol.py`, `_postgres.py`, and `_inmemory.py`
- mE5-large prefixes: `passage:` for corpus docs, `query:` for queries

### Integration Points
- `infotriage.embeddings` — stores item vectors; reused for recall search
- `infotriage.audit` — extended with `details JSONB` for pre-filter skip logging
- `infotriage.ccir_vectors` — new table for CCIR vectors
- RabbitMQ `verdict.ready` — published for both pre-filter skips and LLM-scored items

</code_context>

<specifics>
## Specific Ideas

- **CCIR vector generation script**: `scripts/build_ccir_vectors.py` reads `ccir.md`, extracts each CCIR section, embeds it with `query:` prefix, and upserts into `infotriage.ccir_vectors`. Run once at deploy or when `ccir.md` changes.
- **Pre-filter query**: `SELECT ccir_id, (embedding <=> %s::vector) AS dist FROM infotriage.ccir_vectors ORDER BY embedding <=> %s::vector LIMIT 1;` — if `1 - dist >= τ`, pass; else skip.
- **Recall query**: `SELECT e.item_id, a.title, a.source, a.url, e.ccir, e.score, (emb.embedding <=> %s::vector) AS dist FROM infotriage.enrichment e JOIN infotriage.articles a ON a.id = e.item_id JOIN infotriage.embeddings emb ON emb.item_id = e.item_id WHERE e.bucket != 'skip' AND a.ts >= %s ORDER BY emb.embedding <=> %s::vector LIMIT %s;`
- **Synthesis prompt**: "Answer the query using ONLY the provided articles. Cite every claim with [item_id]. If the articles do not answer the query, say so."

</specifics>

<deferred>
## Deferred Ideas

- SAB `/recall` HTTP endpoint — future enhancement; not in Phase 9 scope
- DGX Spark synthesis for recall — Phase 10 (Wiki-LLM)
- Full-body chunking and indexing — Phase 10
- Per-CCIR adaptive thresholds — backlog; start with global threshold

</deferred>

---

*Phase: 09-rag-recall*
*Context gathered: 2026-07-13*
