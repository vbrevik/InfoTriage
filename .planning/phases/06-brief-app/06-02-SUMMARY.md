# Phase 6 — Plan 06-02 (pgvector semantic clustering) + Wave 1 complete

## One-liner

Replaced keyword-overlap fallback with pgvector HNSW semantic clustering — per-CCIR sections, greedy centroid assignment, configurable threshold via `CLUSTER_THRESHOLD` env var.

## What Was Built (verified via disk state + tests)

### `apps/brief/clustering.py` — new module

- `EnrichedItem` dataclass (13 fields: item_id, title, source, url, summary, ccir, cnr, score, bucket, why, pmesii, tessoc, embedding) ✅
- `cluster_items(store, ccir_sections, threshold, window_hours)` — pgvector via cursor()
  - Queries enrichment + articles + embeddings in two batched queries (ALL %s bind params)
  - Greedy centroid-based clustering per CCIR section
  - Items in different CCIR sections never merge ✅
- `cluster_items_in_memory(items, threshold)` — pure Python fallback using `_cosine_distance()`
  - Same greedy algorithm, enables unit tests without Postgres
  - Also enforces per-CCIR grouping (fixed during review)
- `_cosine_distance(a, b)` — matches pgvector `<=>` operator semantics (distance, not similarity)

### `apps/brief/renderer.py` — modified

- Removed `_STOP` stop words set (keyword-overlap removed entirely) ✅
- Removed `_digest_cluster` import from `digest.py` ✅
- Added `_cluster_rows(rows)` helper that converts dict rows → EnrichedItem → pgvector clusters → dicts
- All 4 `_digest_cluster()` call sites replaced with `_cluster_rows()` ✅
- `CCIR_ORDER` still imported from `apps.triage.digest` ✅
- `render_bluf()` unchanged ✅
- Docstring updated in `render_cluster()` ✅

### `apps/brief/main.py` — modified

- Added `CLUSTER_THRESHOLD = float(os.getenv("CLUSTER_THRESHOLD", "0.75"))` ✅
- Range validation: `0.0 <= CLUSTER_THRESHOLD <= 1.0` with `ValueError` on out-of-range ✅

### `tests/test_brief_clustering.py` — new

- 11 tests across 6 test classes:
  - `TestCosineDistance` (4 tests): identical, opposite, zero, similar vectors
  - `TestSingleCluster` (1): 3 similar items → 1 cluster
  - `TestMultipleClusters` (1): 2 similar + 2 orthogonal → 3 clusters
  - `TestCcirBoundary` (1): property-based, no cluster spans 2+ CCIR sections
  - `TestSingleItemCluster` (1): all orthogonal → 3 singletons
  - `TestEmptyInput` (1): empty → empty list
  - `TestThresholdDefault` (2): verify 0.75 default on both functions

## Verification

| Check | Status |
|-------|--------|
| `pytest tests/test_brief_clustering.py -v` | 11/11 PASSED ✅ |
| `pytest tests/test_brief_renderer.py -v` | 23/23 PASSED ✅ |
| `grep -r "from apps.triage.digest import.*cluster" apps/brief/` | nothing (keyword-overlap removed) ✅ |
| `grep -r "fever()" apps/brief/` | nothing ✅ |
| `grep "_STOP" apps/brief/renderer.py` | 0 occurrences ✅ |
| `grep "_digest_cluster" apps/brief/renderer.py` | 0 occurrences (only in docstring) ✅ |
| `grep "CLUSTER_THRESHOLD" apps/brief/main.py` | default "0.75" + 0.0-1.0 validation ✅ |

## Remaining (deferred)

- **Integration test**: Requires live Postgres + RabbitMQ — deferred
- **Acceptance check**: 3 NATO articles scenario requires live data — deferred
