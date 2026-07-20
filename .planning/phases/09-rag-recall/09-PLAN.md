---
phase: 09-rag-recall
plan: 01
type: execute
wave: 1
depends_on:
  - 08-entity-resolution
files_modified:
  - libs/store/sql/003-vectors.sql
  - libs/store/sql/004-audit.sql
  - libs/store/src/store/_protocol.py
  - libs/store/src/store/_postgres.py
  - libs/store/src/store/_inmemory.py
  - apps/triage/worker.py
  - scripts/build_ccir_vectors.py
  - apps/triage/recall.py
  - tests/test_ccir_vectors.py
  - tests/test_prefilter.py
  - tests/test_recall.py
autonomous: true
requirements: [R1, ADR-001, ADR-004, ADR-006]

must_haves:
  truths:
    - "One vector per CCIR in infotriage.ccir_vectors table (D-01, D-02)"
    - "Pre-filter cosine gate uses τ=0.50, configurable via INFOTRIAGE_PREFILTER_THRESHOLD (D-04, D-05)"
    - "Pre-filter runs after embedding, before score_item() in worker.py (D-07)"
    - "Pre-filter skip writes enrichment with ccir=none, bucket=skip (D-08)"
    - "Audit pre-filter skips with details JSONB (D-11, D-12)"
    - "Recall CLI searches title+summary+enrichment.why via item vectors (D-14, D-15)"
    - "Recall outputs Markdown by default; --json, --obsidian, --synthesize flags (D-18, D-19, D-20)"
    - "Local qwen36 only for synthesis; DGX deferred (D-22, D-23)"
    - "Reuse infotriage.embeddings for items; infotriage.ccir_vectors for CCIRs (D-24, D-25)"
  artifacts:
    - libs/store/sql/003-vectors.sql (new ccir_vectors table, HNSW index)
    - libs/store/sql/004-audit.sql (details JSONB column on audit table)
    - libs/store/src/store/_protocol.py (find_similar_ccir, recall_items methods)
    - libs/store/src/store/_postgres.py (implementations)
    - libs/store/src/store/_inmemory.py (implementations)
    - scripts/build_ccir_vectors.py (CCIR vector build script)
    - apps/triage/worker.py (pre-filter integration)
    - apps/triage/recall.py (thematic recall CLI)
    - tests/test_ccir_vectors.py (unit + db_live tests)
    - tests/test_prefilter.py (pre-filter integration tests)
    - tests/test_recall.py (recall CLI tests)
  key_links:
    - "003-vectors.sql already has infotriage.embeddings with HNSW index — ccir_vectors follows same pattern"
    - "004-audit.sql has basic audit table — extend with details JSONB (D-11)"
    - "worker.py process_item() calls get_embedding() before score_item() — pre-filter slot is between lines 120 and 134"
    - "Store Protocol already has find_similar_entity pattern — find_similar_ccir mirrors it for ccir_vectors"
  prohibitions:
    - statement: "MUST NOT use cloud LLM or embedding for pre-filter or recall"
      status: resolved
      verification: all calls route through local oMLX (ADR-004)
    - statement: "MUST NOT add SAB /recall HTTP endpoint in Phase 9"
      status: resolved
      verification: recall.py is CLI-only; code structured for future HTTP endpoint addition (D-23)
    - statement: "MUST NOT modify score_item() output for items that pass the pre-filter"
      status: resolved
      verification: pre-filter pass path is transparent; score_item() unchanged

---

<objective>
Phase 9 delivers two capabilities:

1. **CCIR pre-filter**: A cosine-similarity gate in the triage worker that skips the LLM scorer
   for clearly off-topic items. Each CCIR (PIR/FFIR/SIR) has a pre-computed vector derived from
   `ccir.md`. An incoming item's embedding is compared against all CCIR vectors; if the maximum
   cosine similarity is below τ (default 0.50), the item is short-circuited to `skip` without
   an LLM call. Audit log captures each skip.

2. **Thematic recall CLI (`recall.py`)**: A command-line tool that lets the operator query "what
   do we know about X since date?" The query embeds the topic with the `query:` prefix and performs
   cosine similarity against the existing `infotriage.embeddings` table. Results include cited
   articles (title, source, URL, CCIR, score, similarity) with optional local qwen36 synthesis.

Output: the triage worker skips off-topic items silently (saving LLM cost); the operator can
run `recall.py --topic "Arctic security" --since 7d` to find relevant corpus items.
</objective>

<execution_context>
@$HOME/.claude/gsd-core/workflows/execute-plan.md
@$HOME/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/09-rag-recall/09-CONTEXT.md
@.planning/phases/09-rag-recall/09-DISCUSSION-LOG.md
@docs/adr/ADR-001-postgres-canonical-store.md
@docs/adr/ADR-004-local-llm-only.md
@docs/adr/ADR-006-microservice-architecture-entity-resolution.md
</context>

<downstream_consumer>
Plans consume:
- Frontmatter (wave, depends_on, files_modified, autonomous)
- Tasks in XML format with read_first and acceptance_criteria
- Verification criteria
- must_haves for goal-backward verification
</downstream_consumer>

## Artifacts this plan produces

| Artifact | Purpose |
|----------|---------|
| `libs/store/sql/003-vectors.sql` (extension) | New `infotriage.ccir_vectors` table + HNSW index |
| `libs/store/sql/004-audit.sql` (extension) | `details JSONB` column on `infotriage.audit` |
| `libs/store/src/store/_protocol.py` (extension) | `find_similar_ccir()` and `recall_items()` methods |
| `libs/store/src/store/_postgres.py` (extension) | Postgres implementations of new methods |
| `libs/store/src/store/_inmemory.py` (extension) | InMemory implementations for tests |
| `scripts/build_ccir_vectors.py` | Build/maintain CCIR vectors from `ccir.md` |
| `apps/triage/worker.py` (edit) | Pre-filter short-circuit in `process_item()` |
| `apps/triage/recall.py` | Thematic recall CLI |
| `tests/test_ccir_vectors.py` | CCIR vector tests (inmemory + db_live) |
| `tests/test_prefilter.py` | Pre-filter integration tests |
| `tests/test_recall.py` | Recall CLI tests |

<tasks>

## Wave 1: Schema foundation

### Task 1: Create `infotriage.ccir_vectors` table and audit extension

**Files:** `libs/store/sql/003-vectors.sql`, `libs/store/sql/004-audit.sql`

**Read first:**
- `libs/store/sql/003-vectors.sql` (existing schema — follow same IF NOT EXISTS, HNSW pattern)
- `libs/store/sql/004-audit.sql` (current audit table — extend, not replace)

**Action:**
Add to `003-vectors.sql`:
```sql
CREATE TABLE IF NOT EXISTS infotriage.ccir_vectors (
    ccir_id     TEXT        PRIMARY KEY,     -- e.g. "PIR-1", "FFIR-2", "SIR-3"
    embedding   vector(1024) NOT NULL,       -- mE5-large 1024-dim, query: prefix embedding
    model       TEXT        NOT NULL DEFAULT 'intfloat/multilingual-e5-large',
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ccir_vectors_embedding_hnsw
    ON infotriage.ccir_vectors USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
```

Add to `004-audit.sql`:
```sql
ALTER TABLE infotriage.audit ADD COLUMN IF NOT EXISTS details JSONB;
```

This is non-breaking: `details` is nullable, existing rows are untouched.

**Verify:**
```bash
# Run SQL against a test Postgres instance and verify tables exist
```

**Done:** `003-vectors.sql` declares `ccir_vectors` table with HNSW index. `004-audit.sql` extends audit with `details JSONB`.

---

### Task 2: Add Store Protocol methods for CCIR and recall

**Files:** `libs/store/src/store/_protocol.py`, `libs/store/src/store/_postgres.py`, `libs/store/src/store/_inmemory.py`

**Read first:**
- `libs/store/src/store/_protocol.py` (existing `find_similar_entity` and `find_near_duplicate` patterns — mirror these)
- `libs/store/src/store/_postgres.py` (vector query patterns with `<=>` and HNSW)
- `libs/store/src/store/_inmemory.py` (dict-backed pattern, `_cosine_sim` helper)

**Action:**
Add two methods to the `Store` Protocol:

```python
def find_similar_ccir(
    self,
    vector: list[float],
    threshold: float = 0.50,  # D-04 default τ
) -> Optional[dict]:
    """Return the nearest CCIR vector with cosine similarity >= threshold, or None.

    Args:
        vector: 1024-dim item embedding.
        threshold: minimum cosine similarity to consider a CCIR match (default 0.50).

    Returns:
        dict with keys: ccir_id, similarity (cosine similarity >= threshold).
        Returns None when no CCIR vector meets the threshold.
    """
    ...

def recall_items(
    self,
    query_vector: list[float],
    since: datetime.datetime | None = None,
    ccir: str | None = None,
    bucket: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """Search infotriage.embeddings for items similar to query_vector.

    Searches over items with bucket != 'skip' by default. Optional filters:
    - since: only items created_at >= this timestamp
    - ccir: only items matching this CCIR ID (e.g. "PIR-1")
    - bucket: filter by bucket value ("keep", "maybe", or exclude "skip")

    Returns list of dicts with keys: item_id, title, source, url, ccir, score, similarity.
    Ordered by similarity DESC. Limited to `limit` results.
    """
    ...
```

Postgres implementation:
- `find_similar_ccir`: `SELECT ccir_id, (1 - (embedding <=> %s::vector)) AS sim FROM infotriage.ccir_vectors WHERE (embedding <=> %s::vector) <= %s ORDER BY embedding <=> %s::vector LIMIT 1;` (convert distance to similarity, filter by threshold)
- `recall_items`: JOIN `infotriage.enrichment` → `infotriage.articles` → `infotriage.embeddings`, filter by bucket/since/ccir, ORDER BY embedding <=> query_vector, LIMIT

InMemory implementation:
- `find_similar_ccir`: iterate stored CCIR vectors, compute cosine, return best if >= threshold
- `recall_items`: iterate stored embeddings, compute cosine, filter by criteria, sort DESC, return top N

All SQL uses `%s` binds. No f-string SQL.

**Verify:**
```bash
pytest tests/test_store_ccir.py -x          # inmemory
pytest tests/test_store_ccir.py -m db_live -x  # postgres
```

**Done:** Store Protocol has `find_similar_ccir` and `recall_items`. Both Postgres and InMemory implementations pass contract tests.

---

## Wave 2: CCIR vector build script

### Task 3: Build `scripts/build_ccir_vectors.py`

**Files:** `scripts/build_ccir_vectors.py`, `tests/test_ccir_vectors.py`

**Read first:**
- `ccir.md` (source of CCIR section text — each section is one CCIR)
- `apps/triage/worker.py` `get_embedding()` (embedding call pattern to reuse)
- `apps/triage/triage_score.py` `llm()` function (alternative embedding pattern)
- `libs/store/src/store/_protocol.py` `find_similar_ccir` from Task 2

**Action:**
Create `scripts/build_ccir_vectors.py` that:
1. Reads `ccir.md` from the project root
2. Parses each CCIR section (PIR-1..6, FFIR-1..3, SIR-1..3) — section heading + bullet text
3. Truncates each section to the first ~512 tokens (per D-03, same as item dedup input)
4. Embeds each section with the `query:` prefix using the same oMLX endpoint as `get_embedding()`
5. Upserts each vector into `infotriage.ccir_vectors` via the Store protocol:
   ```python
   store.put(  # or direct SQL
       "UPSERT infotriage.ccir_vectors SET ccir_id=%s, embedding=%s, model=%s, updated_at=NOW() ON CONFLICT (ccir_id) DO UPDATE SET embedding=EXCLUDED.embedding, updated_at=NOW()",
       (ccir_id, embedding, "intfloat/multilingual-e5-large")
   )
   ```
6. Prints a summary: how many vectors written, how many updated

The script should be runnable standalone (not a Python package import) and accept an optional `--dsn` flag.

**Verify:**
```bash
python scripts/build_ccir_vectors.py --dsn "$INFOTRIAGE_PG_DSN"
# Should output: "Built N CCIR vectors: M new, N-M updated"
# All CCIR IDs present: PIR-1..6, FFIR-1..3, SIR-1..3
```

**Done:** `build_ccir_vectors.py` reads `ccir.md`, embeds each section with `query:` prefix, upserts into `infotriage.ccir_vectors`. Script runs end-to-end.

---

### Task 4: Test CCIR vector storage and retrieval

**Files:** `tests/test_ccir_vectors.py`

**Read first:**
- `tests/test_store_ccir.py` (from Task 2 — follow same fixture pattern)
- `ccir.md` (expected CCIR IDs)

**Action:**
Create `tests/test_ccir_vectors.py` with:
- Test that the `ccir_vectors` table exists (db_live only)
- Test that a known CCIR ID (e.g., "PIR-1") can be upserted and retrieved
- Test that re-upserting the same CCIR ID updates `updated_at` but preserves the vector
- Test that HNSW index exists (db_live only)
- Test that `find_similar_ccir` returns the correct CCIR when given a vector close to a known CCIR vector
- Test that `find_similar_ccir` returns None when the vector is far from all CCIR vectors

**Verify:**
```bash
pytest tests/test_ccir_vectors.py -x           # inmemory
pytest tests/test_ccir_vectors.py -m db_live -x  # postgres
```

**Done:** CCIR vector storage and retrieval tested for both store implementations.

---

## Wave 3: CCIR pre-filter in the triage worker

### Task 5: Integrate pre-filter into `worker.py` `process_item()`

**Files:** `apps/triage/worker.py`

**Read first:**
- `apps/triage/worker.py` (current `process_item()` — D-07 says pre-filter goes after line 120 (embedding computed) and before line 134 (score_item called))
- `libs/store/src/store/_protocol.py` `find_similar_ccir` from Task 2
- `apps/triage/triage_score.py` `score_item()` signature (unchanged)

**Action:**
In `process_item()`, after the embedding is computed (`vec = await asyncio.to_thread(embed, text)`) and before the duplicate check, run the CCIR pre-filter:

```python
# CCIR pre-filter (Phase 9, D-07): compare against CCIR vectors BEFORE dedup/score
try:
    best_ccir = await asyncio.to_thread(store.find_similar_ccir, vec)
except Exception as exc:
    log.warning("pre-filter CCIR search failed for item_id=%s: %s", item_id, exc)
    best_ccir = None  # fall through to LLM scoring

if best_ccir is not None and best_ccir["similarity"] >= float(os.environ.get("INFOTRIAGE_PREFILTER_THRESHOLD", "0.50")):
    # Item passes pre-filter — proceed to normal LLM scoring path (D-09)
    log.info("pre-filter PASS item_id=%s best_ccir=%s similarity=%.3f",
             item_id, best_ccir["ccir_id"], best_ccir["similarity"])
else:
    # Item fails pre-filter — skip LLM scoring (D-08)
    log.info("pre-filter SKIP item_id=%s best_ccir=%s similarity=%.3f",
             item_id, best_ccir["ccir_id"] if best_ccir else "none",
             best_ccir["similarity"] if best_ccir else 0.0)
    
    fields = {
        "ccir": "none",
        "cnr": "none",
        "score": 0,
        "bucket": "skip",
        "why": f"pre-filter: max_cosine={best_ccir['similarity'] if best_ccir else 0.0:.3f} < threshold",
        "pmesii": "none",
        "tessoc": "none",
    }
    
    await asyncio.to_thread(store.put_enrichment, item_id, fields)
    await asyncio.to_thread(store.put_embedding, item_id, vec)
    
    # Audit log (D-11, D-12)
    await asyncio.to_thread(store._audit_write,
        op="pre_filter_skip",
        table_name="enrichment",
        item_id=item_id,
        details={"max_similarity": best_ccir["similarity"] if best_ccir else 0.0,
                 "threshold": float(os.environ.get("INFOTRIAGE_PREFILTER_THRESHOLD", "0.50")),
                 "best_ccir": best_ccir["ccir_id"] if best_ccir else "none"}
    )
    
    payload = VerdictReady(...)  # same as current
    await bus.publish("verdict.ready", item_id, payload.model_dump(mode="json"))
    return  # Short-circuit: no LLM call made
```

If `best_ccir` is not None and similarity >= τ, proceed to the existing dedup + score path (D-09: no change to passed items).

If the pre-filter call itself fails (DB error, etc.), `best_ccir` is None and the item falls through to the normal LLM scoring path (D-10: failures must not silently skip items).

**Key constraints:**
- Audit write uses store internals or a new method — the `details JSONB` column from Task 1 makes this possible
- The short-circuit publishes `verdict.ready` with `bucket=skip` (same as the dedup skip path, D-08)
- Entity resolution (Phase 8) runs after enrichment write — the pre-filter skip must also trigger entity resolution (or skip it? — entity resolution is best-effort and D-10 says pre-filter failures fall through; a pre-filter skip is a "pass" of the pipeline, so entity resolution should still run)

Actually, looking at the current `process_item()` flow more carefully: entity resolution runs AFTER `put_enrichment` and `put_embedding` but BEFORE `bus.publish`. For the pre-filter skip path, I should keep the same sequence: enrichment write → embedding write → entity resolution → verdict ready publish.

Update the entity resolution block to run in the skip path too:
```python
# Entity resolution still runs (Phase 8, best-effort)
try:
    entity_text = item.title + " " + (item.summary or "")
    await resolve_entities_async(
        item_id, entity_text, item.lang or "en", store, embed, ner_chat
    )
except Exception as exc:
    log.warning("entity resolution failed for item_id=%s: %s", item_id, exc)
```

**Verify:**
```bash
pytest tests/test_prefilter.py -x
```

**Done:** Pre-filter integrates into `process_item()` after embedding computation. Off-topic items skip the LLM. Passed items are unchanged.

---

### Task 6: Test pre-filter integration

**Files:** `tests/test_prefilter.py`

**Read first:**
- `tests/test_triage_worker.py` (existing worker test patterns, mocking store/bus)
- `apps/triage/worker.py` (updated `process_item()` from Task 5)

**Action:**
Create `tests/test_prefilter.py` with tests:

1. `test_prefilter_skip_calls_no_llm`: Mock `find_similar_ccir` to return a CCIR match above τ. Assert that `score_item` (LLM scorer) is NOT called, enrichment is written with `bucket=skip`, `verdict.ready` is published with `bucket=skip`.

2. `test_prefilter_pass_calls_llm`: Mock `find_similar_ccir` to return a CCIR match below τ. Assert that `score_item` IS called normally, enrichment reflects LLM output.

3. `test_prefilter_no_ccir_vectors`: Mock `find_similar_ccir` to return None (empty CCIR table). Assert that the item proceeds to normal LLM scoring (D-10 fallback behavior).

4. `test_prefilter_db_failure_falls_through_to_llm`: Mock `find_similar_ccir` to raise an exception. Assert that the item proceeds to normal LLM scoring (D-10).

5. `test_prefilter_threshold_configurable`: Set `INFOTRIAGE_PREFILTER_THRESHOLD=0.70`. Mock CCIR similarity at 0.60. Assert skip happens (0.60 < 0.70). Then mock similarity at 0.75. Assert pass happens.

6. `test_prefilter_audit_log`: Assert that the audit write includes `op="pre_filter_skip"` with `details` containing `max_similarity`, `threshold`, and `best_ccir` (D-12).

7. `test_prefilter_entity_resolution_still_runs`: Assert that when pre-filter skips, entity resolution still runs (Phase 8 integration).

**Verify:**
```bash
pytest tests/test_prefilter.py -x
```

**Done:** Pre-filter behavior fully tested: skip path, pass path, fallback path, threshold config, audit logging, and entity resolution integration.

---

## Wave 4: Thematic recall CLI

### Task 7: Build `recall.py` CLI

**Files:** `apps/triage/recall.py`

**Read first:**
- `apps/triage/worker.py` `get_embedding()` (embedding call pattern to reuse)
- `libs/store/src/store/_protocol.py` `recall_items` from Task 2
- `apps/triage/triage_score.py` `llm()` function (for synthesis, D-21)

**Action:**
Create `apps/triage/recall.py` as a CLI tool with argparse:

```
usage: recall.py [-h] [--topic TOPIC] [--since SINCE] [--ccir CCIR]
                 [--bucket {keep,maybe,skip}] [--limit LIMIT]
                 [--json] [--obsidian PATH] [--synthesize] [--include-body]
```

Flags:
- `--topic TEXT` (required): Search query topic
- `--since TEXT`: Date filter — accepts `7d` (last 7 days) or `2026-07-01` (ISO date). Default: no filter. (D-17)
- `--ccir TEXT`: Filter by CCIR ID (e.g., `PIR-1`). (D-17)
- `--bucket TEXT`: Filter by bucket value. (D-17)
- `--limit INT`: Max results, default 50. (D-17)
- `--json`: Return structured JSON to stdout. (D-19)
- `--obsidian PATH`: Write a Markdown note with front matter to the Obsidian vault. (D-20)
- `--synthesize`: Trigger local qwen36 synthesis over the retrieved articles. (D-21)
- `--include-body`: Fetch article body from blobs and include in synthesis context. (D-16)

Default output (no `--json`, `--obsidian`, or `--synthesize`): Markdown to stdout with a ranked list of articles:
```
## Recall: "Arctic security" (2026-07-09 to 2026-07-16)

| # | Title | Source | CCIR | Score | Similarity |
|---|-------|--------|------|-------|------------|
| 1 | [Title](URL) | source | PIR-1 | 8 | 0.892 |
| 2 | [Title](URL) | source | FFIR-2 | 6 | 0.847 |
```

With `--synthesize`: After listing results, prompt local qwen36 with:
```
Answer the query using ONLY the provided articles. Cite every claim with [item_id].
If the articles do not answer the query, say so.

Query: <topic>

Articles:
[item_id: "xxx"] Title: "..." Source: "..." Summary: "..." CCIR: "PIR-1" Score: 8
...
```

The synthesis prompt instructs the model to cite every claim with `[item_id]` and answer only from provided context (D-21).

With `--obsidian <path>`: Write a Markdown note to the specified vault path. Front matter includes `topic`, `date`, `count`, `results` array. Body contains the ranked list and optional synthesis. (D-20)

With `--json`: Return a JSON array of result objects:
```json
[
  {"item_id": "xxx", "url": "...", "title": "...", "source": "...",
   "ccir": "PIR-1", "score": 8, "similarity": 0.892},
  ...
]
```

Structure note: The code uses a `RecallBackend` abstraction (Protocol-like) so that future DGX Spark (Phase 10) can be added as a second synthesis backend with minimal changes (D-23).

**Verify:**
```bash
python apps/triage/recall.py --topic "Arctic security" --since 7d
# Should output formatted Markdown to stdout
```

**Done:** `recall.py` CLI exists with all specified flags. Default Markdown output, `--json`, `--obsidian`, `--synthesize`, and `--include-body` all functional.

---

### Task 8: Test recall CLI

**Files:** `tests/test_recall.py`

**Read first:**
- `tests/test_store_ccir.py` (from Task 2 — store fixture pattern)
- `apps/triage/recall.py` (from Task 7)

**Action:**
Create `tests/test_recall.py` with:

1. `test_recall_returns_ranked_results`: Mock `recall_items` to return sample results. Assert CLI outputs ranked Markdown with correct similarity ordering.

2. `test_recall_json_output`: Run with `--json`. Assert output is valid JSON array with expected fields (item_id, url, title, source, ccir, score, similarity).

3. `test_recall_obsidian_writes_file`: Run with `--obsidian /tmp/test-vault/`. Assert a Markdown file is created with front matter and ranked list.

4. `test_recall_since_filter`: Run with `--since 2026-07-01`. Assert the store's `recall_items` is called with the correct `since` parameter.

5. `test_recall_ccir_filter`: Run with `--ccir PIR-1`. Assert the store's `recall_items` is called with the `ccir` parameter.

6. `test_recall_limit`: Run with `--limit 10`. Assert the store's `recall_items` is called with `limit=10`.

7. `test_recall_synthesis_calls_llm`: Mock the LLM function. Run with `--synthesize`. Assert LLM is called with the correct prompt containing article context and the `query:` embedded topic.

8. `test_recall_no_results`: Run with a topic that returns zero results. Assert output indicates "No results found for '<topic>'."

9. `test_recall_include_body`: Run with `--include-body`. Assert the synthesis prompt includes article body content.

**Verify:**
```bash
pytest tests/test_recall.py -x
```

**Done:** Recall CLI tested for all output modes, filters, synthesis, and edge cases.

---

## Wave 5: Verification and integration

### Task 9: Full verification suite

**Files:** (no new files — runs existing tests)

**Read first:**
- `tests/` (full test directory — know what exists)
- `pytest` config in `pyproject.toml`

**Action:**
Run the full test suite and verify:
```bash
pytest tests/ -q
```

Expected: baseline from Phase 8 tests + new Phase 9 tests all pass.

Specifically verify:
- `pytest tests/test_ccir_vectors.py -x` (CCIR vector storage)
- `pytest tests/test_ccir_vectors.py -m db_live -x` (CCIR vector storage, postgres)
- `pytest tests/test_prefilter.py -x` (pre-filter integration)
- `pytest tests/test_recall.py -x` (recall CLI)
- `pytest tests/test_store_ccir.py -x` (store contract)
- `pytest tests/test_store_ccir.py -m db_live -x` (store contract, postgres)
- Full suite: `pytest tests/ -q` — all green

**Done:** Full test suite passes. Phase 9 is verified.

---

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| CCIR vector → pre-filter decision | CCIR vectors are static embeddings from `ccir.md`; tampering requires DB access |
| Pre-filter → LLM call gate | Pre-filter skip bypasses LLM scoring — must not silently drop items that should be scored (D-10) |
| Recall query → corpus access | Recall searches the durable corpus; no write path from recall |
| LLM synthesis → operator output | Synthesis output is operator-facing; prompt must enforce citation-only-from-context constraint |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-09-01 | False negative | Pre-filter skip | medium | mitigate | τ=0.50 is conservative (D-04); borderline items still go to LLM. D-06 validates by sampling skips vs LLM scores. |
| T-09-02 | Silent data loss | Pre-filter DB failure | high | mitigate | If `find_similar_ccir` raises, `best_ccir=None` and item falls through to LLM scoring (D-10). |
| T-09-03 | Prompt injection | Recall synthesis prompt | medium | mitigate | Synthesis prompt restricts model to citing only from provided article context; violation triggers hard-exit. |
| T-09-04 | Information disclosure | Recall results | low | accept | Recall is a local CLI tool; no network-facing surface. |

</threat_model>

<verification>
- `pytest tests/test_ccir_vectors.py -x` (inmemory) and `-m db_live -x` (postgres) green
- `pytest tests/test_store_ccir.py -x` (inmemory) and `-m db_live -x` (postgres) green
- `pytest tests/test_prefilter.py -x` green
- `pytest tests/test_recall.py -x` green
- Full suite: `pytest tests/ -q` returns baseline + new tests all pass
- `python scripts/build_ccir_vectors.py --dsn "$INFOTRIAGE_PG_DSN"` writes all CCIR vectors
- `python apps/triage/recall.py --topic "test" --since 7d` runs end-to-end
</verification>

<success_criteria>
From `.planning/ROADMAP.md` §Phase 9:

1. **Clearly off-topic items skip the LLM** (`cosine(article, ccir_vector) < τ`), logged in `audit`.
   - Verified by: `test_prefilter_skip_calls_no_llm`, `test_prefilter_audit_log`
   - τ=0.50 default, configurable via `INFOTRIAGE_PREFILTER_THRESHOLD`
   - Audit row: `op="pre_filter_skip"`, `details={max_similarity, threshold, best_ccir}`

2. **A thematic recall (`recall.py --topic … --since …`) cites `articles.id`/`url` per claim; synthesis uses local qwen36.**
   - Verified by: `test_recall_returns_ranked_results`, `test_recall_json_output`, `test_recall_synthesis_calls_llm`
   - Outputs: Markdown (default), `--json`, `--obsidian <path>`
   - Synthesis with `--synthesize` uses local qwen36 only, cites claims with `[item_id]`

Additional verification:
- Pre-filter failures fall through to LLM scoring (no silent skips): `test_prefilter_db_failure_falls_through_to_llm`
- Entity resolution still runs on pre-filter skipped items (Phase 8 integration preserved)
- CCIR vectors are stored in `infotriage.ccir_vectors` with HNSW index
- No SAB `/recall` HTTP endpoint (out of scope, deferred)
</success_criteria>

<output>
Create `.planning/phases/09-rag-recall/09-01-SUMMARY.md` when done
</output>
