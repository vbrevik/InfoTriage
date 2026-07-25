---
phase: 260725-lme-fix-ccir-pre-filter-threshold-miscalibra
plan: 01
subsystem: triage
tags: [ccir, pre-filter, threshold, regression-test]
dependency-graph:
  requires: []
  provides: ["evidence-anchored INFOTRIAGE_PREFILTER_THRESHOLD default (0.70)"]
  affects: ["apps/triage/worker.py process_item() pre-filter gate"]
tech-stack:
  added: []
  patterns: ["monkeypatch.delenv for env-default regression tests", "cosine-target vector helper in test fixtures"]
key-files:
  created: []
  modified:
    - apps/triage/worker.py
    - tests/test_prefilter.py
    - .planning/STATE.md
decisions:
  - "Raised INFOTRIAGE_PREFILTER_THRESHOLD default from 0.50 to 0.70 — an evidence-anchored floor strictly below every observed corpus similarity (0.743-0.848), so production filtering behavior is unchanged today. Full recalibration is out of scope, tracked as backlog phase 999.2."
metrics:
  duration: "~20 minutes"
  completed: 2026-07-25
status: complete
---

# Phase 260725-lme Plan 01: Fix CCIR pre-filter threshold miscalibration Summary

Raised the unvalidated `INFOTRIAGE_PREFILTER_THRESHOLD` default from 0.50 to an
evidence-anchored 0.70, backed by a corpus measurement and pinned with two new
behavioral regression tests, without changing any production filtering behavior.

## What Was Built

- **Task 1:** Two new tests in `tests/test_prefilter.py`
  (`test_prefilter_default_threshold_skips_below_070`,
  `test_prefilter_default_threshold_passes_at_071`), both with
  `INFOTRIAGE_PREFILTER_THRESHOLD` explicitly unset via `monkeypatch.delenv(...,
  raising=False)`. Added a `_ccir_vector_at_cosine(c)` helper (`import math`) to
  build a CCIR vector at an exact target cosine against `VEC`. Then changed the
  `os.environ.get("INFOTRIAGE_PREFILTER_THRESHOLD", ...)` fallback in
  `apps/triage/worker.py` from `"0.50"` to `"0.70"`, and replaced the one-line
  `# Phase 9: CCIR pre-filter` comment with a block recording the corpus
  evidence (423 live items, mE5-large, 0.743-0.848 band, 0.7452 lowest genuine
  match) and the 999.2 backlog cross-reference. Gate logic (`>=` comparison,
  both fall-through conditions, PASS/SKIP logging) is byte-identical.
- **Task 2:** Added a one-line-summary bullet to the top-most `### Just-completed`
  session entry in `.planning/STATE.md`, naming the 0.50 -> 0.70 change, the
  zero-skip production history, and cross-referencing backlog phase `999.2`.
- **Task 3:** Ran the full validation gate (pytest full suite, mypy, black) and
  made two atomic commits with explicit file paths.

## RED Evidence (Task 1, before the worker.py fix)

Ran `pytest tests/test_prefilter.py -k "default_threshold" -v` against the
**unmodified** worker.py (old 0.50 default):

```
tests/test_prefilter.py F.                                               [100%]
FAILURES
_______________ test_prefilter_default_threshold_skips_below_070 _______________
tests/test_prefilter.py:302: in test_prefilter_default_threshold_skips_below_070
    assert score_calls == []
E   AssertionError: assert [{'source': '... 'Test Item'}] == []
E     Left contains one more item: {'source': 'Test Source', 'summary': 'A summary', 'title': 'Test Item'}
Captured stdout call:
{"message": "pre-filter PASS item_id=... best_ccir=PIR-2 similarity=0.690", ...}
1 failed, 1 passed, 7 deselected in 0.26s
```

`test_prefilter_default_threshold_skips_below_070` failed exactly as predicted:
at the old 0.50 default, similarity 0.690 satisfies `0.690 >= 0.50`, so the
gate PASSES the item through to the LLM scorer instead of skipping it (log:
`pre-filter PASS ... similarity=0.690`). `test_prefilter_default_threshold_passes_at_071`
passed under the old default too (0.71 >= 0.50 also passes) — this is expected;
only the skip-side test was required to demonstrate RED per the plan.

## GREEN Evidence (after the worker.py fix)

`pytest tests/test_prefilter.py -v`: **9 passed** (7 pre-existing + 2 new).

## Full Validation Gate (Task 3)

1. `INFOTRIAGE_PG_DSN=postgresql://infotriage:infotriage_dev@127.0.0.1:22000/infotriage python -m pytest tests/ -q`
   → **617 passed, 0 failed, 54 skipped**. Last recorded baseline in
   `.planning/STATE.md` (2026-07-24 session) was "572 passed / 0 real failures".
   The higher pass count reflects unrelated repo growth between that baseline
   and now (CCIR retirement, entity-resolution fixes, Phase 08/09 work already
   committed on `main`); **zero failures either run, so zero new failures**.
2. `python -m mypy apps/triage/worker.py tests/test_prefilter.py` → **clean, no
   issues found**.
3. `python -m black --check apps/triage/worker.py tests/test_prefilter.py` →
   **clean, both files unchanged**.

## Fixture Sanity Sweep (Task 1, step 5)

`grep -rn "put_ccir_vector\|INFOTRIAGE_PREFILTER_THRESHOLD" tests/` found CCIR
vector usage only in `tests/test_prefilter.py` (reviewed — the existing tests
use either cosine 0.0 or 1.0, both outside the newly-active 0.50-0.70 band) and
`tests/test_ccir_vectors.py` (pure store-layer tests against
`find_similar_ccir` directly — they never call `process_item()`, so the
pre-filter gate default does not apply to them). **No existing test needed a
fixture adjustment.**

## Deviations from Plan

None — plan executed exactly as written.

## Commits

- `3acbc45` — `fix(triage): anchor CCIR pre-filter threshold to corpus evidence (0.50 -> 0.70)`
  (`apps/triage/worker.py`, `tests/test_prefilter.py`)
- `<pending>` — `chore(planning): note pre-filter threshold miscalibration alongside 999.2 backlog`
  (`.planning/STATE.md`, this plan directory) — recorded after this SUMMARY is written, per Task 3.

## Self-Check: PASSED

- `apps/triage/worker.py` — FOUND, diff +15/-1 as expected (one literal + comment block).
- `tests/test_prefilter.py` — FOUND, 9/9 tests pass.
- `.planning/STATE.md` — FOUND, `grep -c "999\.2"` returns 1 (was 0).
- Commit `3acbc45` — FOUND in `git log`.
