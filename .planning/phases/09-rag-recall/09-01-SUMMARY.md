---
phase: 09-rag-recall
plan: 01
status: complete
goal: CCIR pre-filter gate + thematic recall over the durable corpus
verified: 2026-07-21
verified_by: "full pytest 479 passed / 0 failed / 0 skipped; mypy clean; live recall CLI + CCIR vector build smoke tests"
---

# 09-01-SUMMARY.md — RAG recall (complete)

Phase 9 delivered the two planned capabilities:

1. **CCIR pre-filter gate** in the triage worker: incoming items embeddings are compared against stored CCIR vectors; clearly off-topic items short-circuit to `skip` without an LLM call.
2. **Thematic recall CLI (`apps/triage/recall.py`)**: operator-facing tool that embeds a topic, searches the durable corpus, and returns ranked results with optional local synthesis.

The phase was executed as a single wave, amended from the original `09-PLAN.md` after implementation blockers were discovered during live execution.

## What shipped

### Wave 1: Schema + Store Protocol

- `libs/store/sql/003-vectors.sql` already contained the `infotriage.ccir_vectors` table and HNSW index; no new DDL was required.
- `libs/store/src/store/_protocol.py` gained `find_similar_ccir()` and `recall_items()`.
- `libs/store/src/store/_postgres.py` and `_inmemory.py` implement both methods.
- `find_similar_ccir()` returns the nearest CCIR (or `None` if the table is empty); the **caller applies the threshold** (deviation from the original plan, see below).
- `recall_items()` uses `psycopg.sql` composable SQL to keep `WHERE` clause assembly safe; no f-string SQL.

### Wave 2: CCIR vector build script

- `scripts/build_ccir_vectors.py` parses `ccir.md`, sections are embedded with the `query:` prefix, and vectors are upserted into `infotriage.ccir_vectors`.
- Smoke test: built 12 CCIR vectors against the test database.

### Wave 3: Pre-filter integration

- `apps/triage/worker.py` inserts the pre-filter after embedding computation and before the LLM scorer.
- Default threshold τ = 0.50, configurable via `INFOTRIAGE_PREFILTER_THRESHOLD`.
- Failures and empty CCIR tables fall through to normal LLM scoring — no silent data loss.
- Skipped items write a `skip` enrichment, store the embedding, and still run best-effort entity resolution before publishing `verdict.ready`.
- Audit rows are written with `op="pre_filter_skip"` and JSON `details` containing `max_similarity`, `threshold`, and `best_ccir`.

### Wave 4: Thematic recall CLI

- `apps/triage/recall.py` supports `--topic`, `--since` (relative `7d` or ISO date), `--ccir`, `--bucket`, `--limit`, `--json`, `--obsidian`, `--synthesize`, and `--include-body`.
- Default output is Markdown; `--json` returns a JSON array; `--obsidian` writes a note with YAML front matter; `--synthesize` calls local qwen36 with citation constraints.
- JSON output strips the full `body` to avoid leaking large content, while preserving `summary` and other metadata.

### Wave 5: Verification

- `tests/test_ccir_vectors.py` — CCIR vector store/retrieval (inmemory + db_live).
- `tests/test_build_ccir_vectors.py` — parser and script structure tests.
- `tests/test_prefilter.py` — pre-filter skip/pass/fallback/threshold/audit/entity-resolution tests.
- `tests/test_recall.py` — recall CLI output modes, filters, synthesis, and body-stripping tests.
- Full suite against live test DB: **479 passed, 0 failed, 0 skipped**.
- mypy clean on all modified Phase 9 files.

## Deviations from 09-PLAN.md

| Plan | Actual | Rationale |
|------|--------|-----------|
| `find_similar_ccir` applied a threshold internally and returned only matches above τ. | `find_similar_ccir` returns the raw nearest CCIR; `worker.py` applies τ. | Cleaner separation: the store method is reusable for recall/debugging and has no hidden threshold policy. |
| `recall_items` assembled its `WHERE` clause via string concatenation. | Uses `psycopg.sql` composable objects. | Safer SQL composition; easier to review and maintain. |
| Original plan did not mention the `ccir_vectors` table in integration tests. | `tests/test_store_integration.py` updated to expect `ccir_vectors`. | Table now exists, so the schema inventory test must account for it. |
| Original plan did not anticipate `[None]` aliases in `get_all_entities()`. | Added `ARRAY_AGG ... FILTER (WHERE el.mention IS NOT NULL AND el.lang IS NOT NULL)`. | Prevents unlinked entities from appearing with a single `[None]` alias in Entity Graph.md. |
| `--json` with `--include-body` originally emitted full text. | JSON output strips `body` (keeps `summary`). | Avoids unexpectedly large JSON payloads and content leakage in operator output. |
| Plan assumed separate waves executed over multiple sessions. | All work was completed in one contiguous execution pass. | The scope was small enough to close in a single wave. |

## Decisions recorded

- **Threshold policy:** τ = 0.50 default. This is intentionally conservative — the gate must err on the side of passing borderline items to the LLM rather than silently dropping them.
- **Fall-through on failure:** If CCIR lookup fails or no CCIR vectors exist, the item proceeds to normal LLM scoring. Pre-filter must never be a single point of failure.
- **Local-only LLM:** Synthesis in `recall.py` uses local qwen36 only (ADR-004). DGX Spark is deferred.
- **No `/recall` HTTP endpoint in Phase 9:** Recall remains CLI-only, with internal structure that allows future HTTP wrapping.
- **JSON content hygiene:** Full article `body` is stripped from JSON recall output; `summary` and metadata are preserved.

## Tests / verification

- `pytest tests/test_ccir_vectors.py -q` — green
- `pytest tests/test_prefilter.py -q` — green
- `pytest tests/test_recall.py -q` — green
- `pytest tests/test_build_ccir_vectors.py -q` — green
- Full suite with live test DB: `pytest -q --tb=short` — **479 passed, 0 failed, 0 skipped**
- `mypy` on modified Phase 9 files: clean
- Smoke tests:
  - `python scripts/build_ccir_vectors.py --dsn <test_dsn>` → 12 CCIR vectors built
  - `python apps/triage/recall.py --dsn <test_dsn> --topic "Arctic security" --since 7d --json --limit 5` → exit 0

## Files touched

### New
- `scripts/build_ccir_vectors.py`
- `apps/triage/recall.py`
- `tests/test_ccir_vectors.py`
- `tests/test_prefilter.py`
- `tests/test_recall.py`
- `tests/test_build_ccir_vectors.py`

### Modified
- `libs/store/src/store/_protocol.py` — added `find_similar_ccir()` and `recall_items()`
- `libs/store/src/store/_postgres.py` — implementations + `get_all_entities` `FILTER` fix
- `libs/store/src/store/_inmemory.py` — implementations
- `apps/triage/worker.py` — pre-filter gate integration
- `tests/test_store_integration.py` — expected tables list includes `ccir_vectors`

### Planning docs
- `.planning/ROADMAP.md` — Phase 9 marked complete
- `.planning/STATE.md` — Phase 9 completion recorded
- `.planning/phases/09-rag-recall/09-PLAN.md` — amended to reflect actual implementation

## Acceptance criteria

From ROADMAP.md §Phase 9:

- [x] Clearly off-topic items skip the LLM (`cosine(article, ccir_vector) < τ`) and are logged in `audit`.
- [x] A thematic recall (`recall.py --topic … --since …`) cites `articles.id`/`url` per claim; synthesis uses local qwen36.
- [x] Pre-filter failures fall through to LLM scoring.
- [x] Entity resolution still runs on pre-filter skipped items.
- [x] CCIR vectors stored with HNSW index.
- [x] No SAB `/recall` HTTP endpoint added.

## Next

- Phase 10 is unblocked and ready for planning when scheduled.
- M1 ship decision remains: accumulated Phase 7/8/9 commits are still ahead of `origin/main` and await explicit push.
