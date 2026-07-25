---
phase: 260725-lme-fix-ccir-pre-filter-threshold-miscalibra
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - apps/triage/worker.py
  - tests/test_prefilter.py
  - .planning/STATE.md
autonomous: true
requirements: [QUICK-260725-LME]
mode: quick

must_haves:
  truths:
    - "With INFOTRIAGE_PREFILTER_THRESHOLD unset, an item whose best CCIR cosine similarity is 0.69 is SKIPPED by the pre-filter (the LLM scorer is never called)."
    - "With INFOTRIAGE_PREFILTER_THRESHOLD unset, an item whose best CCIR cosine similarity is 0.71 PASSES the pre-filter and reaches the LLM scorer."
    - "Every item in the live 0.743-0.848 corpus band still passes the gate — production filtering behavior is unchanged by this fix (intentional)."
    - "A future accidental revert of the default back to 0.50 fails the test suite."
    - "The inline comment at the threshold definition records the corpus evidence, the 0.7452 floor, and that true recalibration is out of scope (tracked with backlog 999.2)."
  artifacts:
    - apps/triage/worker.py
    - tests/test_prefilter.py
    - .planning/STATE.md
  key_links:
    - "process_item() default env fallback -> pre_filter_passes comparison -> skip/pass branch"
    - "tests/test_prefilter.py regression tests -> the default literal in worker.py (behavioral pin, not a source grep)"
    - ".planning/STATE.md note -> .planning/phases/999.2-dedup-threshold-calibration-on-larger-corpus/ (cross-reference only, no new backlog file)"
---

<objective>
Replace the unvalidated `INFOTRIAGE_PREFILTER_THRESHOLD` default (0.50, picked at Phase 9
design time with zero corpus calibration) with an evidence-anchored value of 0.70, record
the supporting corpus evidence at the definition site, and pin the new default with a
behavioral regression test.

Purpose: the CCIR pre-filter has never skipped a single item in production (zero
`pre_filter_skip` audit rows ever; 1254+ PASS / 0 SKIP on 2026-07-24) because τ=0.50 was
trivially satisfied by every item. Live evidence (423 items, mE5-large, 13 CCIR topic
vectors) shows the ENTIRE corpus — genuine signal and structural junk alike — clusters in
0.743-0.848, and the two INTERLEAVE (lowest genuine CCIR match 0.7452 sits *below* junk at
0.7485). There is no safe cut point in that band today, so this task deliberately does NOT
change production filtering behavior. It replaces a baseless constant with one anchored to
measured evidence (strictly below the lowest observed similarity for any item, on-topic or
not), preserving the pre-filter's documented "never silently drop real signal" property
from 09-01-SUMMARY.md.

Output: one code change + one comment rewrite + two regression tests + one STATE.md
cross-reference line, all green under pytest/mypy/black.
</objective>

<scope_boundary>
EXPLICITLY OUT OF SCOPE — do not attempt, do not "improve" on:

- Finding a τ that actually starts skipping items today. The evidence shows this is not
  safely possible without more calibration work. A value tuned to catch a few known junk
  items in the current 423-item sample would be overfit noise, not a fix.
- Full recalibration (larger corpus + synthetic negative controls, or moving from absolute
  cosine to relative/rank-based scoring). That is already tracked as backlog phase
  `.planning/phases/999.2-dedup-threshold-calibration-on-larger-corpus/`.
- Creating a new backlog phase directory or ROADMAP phase. Item 5 below is a ONE-LINE
  cross-reference in STATE.md, nothing more.
- Touching `INFOTRIAGE_DEDUP_THRESHOLD` (0.90) or the `_clean_for_embedding()` path. They
  are adjacent in the same function and are NOT part of this task.
- Re-deriving the root cause. It is empirically confirmed against the live prod DB and 3
  days of `triage.log`. Use it as given.
</scope_boundary>

<execution_context>
@$HOME/.claude/gsd-core/workflows/execute-plan.md
@$HOME/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@apps/triage/worker.py
@tests/test_prefilter.py

Interface notes (already verified — do not re-derive):
- The threshold lives inline in `process_item()` in `apps/triage/worker.py` (~line 171-174),
  as `float(os.environ.get("INFOTRIAGE_PREFILTER_THRESHOLD", "0.50"))`. It is read per-item,
  so tests can set/unset the env var per test without module reload.
- Gate semantics: `pre_filter_passes = ccir_lookup_failed or best_ccir is None or
  _prefilter_sim >= _prefilter_threshold` — inclusive `>=`, and both failure modes
  fall THROUGH to the LLM (D-07). Do not alter any of that logic.
- `InMemoryStore.find_similar_ccir(vector)` (`libs/store/src/store/_inmemory.py:390`)
  returns `{"ccir_id", "similarity"}` for the max `_cosine_sim` over `put_ccir_vector()`
  entries, or `None` when the table is empty. Cosine, not normalized-dot — so with an item
  embedding of `[1.0, 0.0]`, a CCIR vector `[c, sqrt(1 - c*c)]` yields similarity == c.
- Skip path writes `enrichment.why = f"pre-filter: max_cosine={...:.3f} < threshold"` and
  an audit row with `op="pre_filter_skip"` (worker.py:252, :266). Existing tests assert both.
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Raise the pre-filter default to 0.70 with evidence comment + behavioral regression tests</name>
  <files>apps/triage/worker.py, tests/test_prefilter.py</files>
  <behavior>
    Two new tests in `tests/test_prefilter.py`, both with `INFOTRIAGE_PREFILTER_THRESHOLD`
    explicitly UNSET (use `monkeypatch.delenv(..., raising=False)` so an operator's ambient
    env cannot mask a regression):

    - Test 1 — `test_prefilter_default_threshold_skips_below_070`: item embedding `[1.0, 0.0]`,
      one CCIR vector at cosine 0.69. Expect: LLM scorer NOT called; `enrichment["bucket"] == "skip"`;
      `"pre-filter" in enrichment["why"]`; exactly one audit row with `op == "pre_filter_skip"`.
      This test FAILS against the old 0.50 default (0.69 >= 0.50 would pass the gate) — that
      failing-first property is the whole point of the test, so confirm RED before the fix.
    - Test 2 — `test_prefilter_default_threshold_passes_at_071`: same item, one CCIR vector at
      cosine 0.71. Expect: LLM scorer called exactly once; no audit rows.

    Together these pin the default into (0.69, 0.71] — i.e. exactly 0.70 — behaviorally, so
    a future revert to 0.50 (or a drift to 0.75) fails the suite. Prefer this over asserting
    on the source literal: it survives reformatting and actually exercises the gate.
  </behavior>
  <action>
Follow the repo's existing test style in `tests/test_prefilter.py` (module-level `VEC`,
`_item()` helper, `asyncio.run(process_item(...))` with `embed=lambda text: VEC` and a
closure-captured `score_calls` list).

1. Add a small module-level helper next to `VEC` that builds a CCIR vector at an exact
   target cosine against `VEC`: given `c`, return `[c, math.sqrt(1.0 - c * c)]` (add
   `import math`). Do not hardcode the second component — let math produce it.
2. Write the two tests described in `<behavior>`, using `monkeypatch` rather than the
   manual `os.environ` save/restore dance used by the older tests in this file (do not
   refactor the older tests — leave them as they are).
3. THEN make the fix in `apps/triage/worker.py`: change the `os.environ.get(
   "INFOTRIAGE_PREFILTER_THRESHOLD", ...)` fallback from the old value to `"0.70"`. Change
   ONLY the default literal — the surrounding gate logic, the `>=` comparison, the two
   fall-through conditions, and the PASS/SKIP logging all stay byte-identical.
4. Replace the one-line `# Phase 9: CCIR pre-filter` comment above the threshold with a
   short block (keep it under ~10 lines, match the style of the existing dedup-threshold
   comment at worker.py:209-217) recording: that the prior default was set at design time
   with no corpus calibration; that a 2026-07-25 measurement over 423 live items with
   mE5-large found the whole corpus — signal and junk alike — inside 0.743-0.848 with the
   two interleaving, lowest genuine CCIR match at 0.7452; that the new value is a safe
   evidence-anchored floor sitting strictly below every observed similarity, so it does not
   change filtering behavior today and cannot drop real signal; and that a functional
   recalibration needs the larger-corpus + synthetic-negative-control methodology already
   tracked as backlog phase 999.2 (or a move to relative/rank-based scoring instead of an
   absolute cosine cutoff), which is out of scope here.
5. Sanity-sweep the rest of the suite for fixtures that sit in the newly-active 0.50-0.70
   band: `grep -rn "put_ccir_vector\|INFOTRIAGE_PREFILTER_THRESHOLD" tests/`. Any test whose
   item/CCIR pair now lands below 0.70 and that expected a PASS must be made explicit (set
   the env var in that test, or move its vectors) rather than left to inherit the default.
   Note in the SUMMARY if none needed changes.
  </action>
  <verify>
    <automated>INFOTRIAGE_PG_DSN=postgresql://infotriage:infotriage_dev@127.0.0.1:22000/infotriage python -m pytest tests/test_prefilter.py -q</automated>
  </verify>
  <done>All tests in `tests/test_prefilter.py` pass, including the two new ones; the two new tests were observed RED against the pre-fix default before the worker.py change landed; the pre-filter gate logic is unchanged apart from the default literal and its comment.</done>
  <reversibility rating="reversible">A single env-var default; overridable at runtime via INFOTRIAGE_PREFILTER_THRESHOLD and revertible in one line.</reversibility>
</task>

<task type="auto">
  <name>Task 2: Cross-reference the miscalibration class in STATE.md</name>
  <files>.planning/STATE.md</files>
  <action>
Append ONE bullet to the `### Just-completed` list of the TOP-MOST session entry in
`.planning/STATE.md` (currently `## Session: 2026-07-24 — CCIR registry shipped; ...`; if a
newer session entry has since been added above it, use that one instead).

The bullet must: name `INFOTRIAGE_PREFILTER_THRESHOLD` and the 0.50 -> 0.70 change; state
that the gate has never skipped an item in production (zero `pre_filter_skip` audit rows
ever); state that the new value is an evidence-anchored floor that does NOT change
filtering behavior today; and cross-reference that this is the same class of issue as
backlog phase `999.2` (uncalibrated absolute-cosine threshold needing a larger corpus with
synthetic negative controls), citing the string `999.2` literally so the link is greppable.

Do NOT create a new backlog phase directory, do NOT add a ROADMAP phase, do NOT edit the
999.2 phase directory, and do NOT rewrite any other part of STATE.md. Use Edit (scoped
replacement) — never Write — on this file.
  </action>
  <verify>
    <automated>grep -c "999\.2" .planning/STATE.md</automated>
  </verify>
  <done>`grep -c "999\.2" .planning/STATE.md` returns >= 1 (it returned 0 before this task); exactly one bullet was added; no other STATE.md content changed (`git diff --stat .planning/STATE.md` shows a small single-hunk insertion).</done>
</task>

<task type="auto">
  <name>Task 3: Full validation gate and atomic commits</name>
  <files>apps/triage/worker.py, tests/test_prefilter.py, .planning/STATE.md</files>
  <action>
Run the full gate — all three must be green before this task is done. Fail loud: if any
step is red, fix it or stop and report; do not proceed to commit with a skipped or failing
check, and do not claim green without pasting the actual counts into the SUMMARY.

1. Full suite with the DSN set (required by `tests/test_recall.py`'s pre-existing env
   dependency):
   `INFOTRIAGE_PG_DSN=postgresql://infotriage:infotriage_dev@127.0.0.1:22000/infotriage python -m pytest tests/ -q`
   Compare pass/skip/fail counts against the last recorded baseline in STATE.md. Zero new
   failures. Any pre-existing failure must be named explicitly as pre-existing, not waved past.
2. `python -m mypy apps/triage/worker.py tests/test_prefilter.py` — clean. (`pyproject.toml`
   `[tool.mypy].files` covers libs + tests but not `apps/`, so pass the paths explicitly, as
   prior sessions did for changed app files.)
3. `python -m black --check apps/triage/worker.py tests/test_prefilter.py` — clean. Run
   `black` on those two files first if needed.

Then commit with explicit file paths — no `git add .`, per project rule. Two commits,
matching the repo's existing imperative `type(scope): ...` style:
  - `fix(triage): anchor CCIR pre-filter threshold to corpus evidence (0.50 -> 0.70)`
    staging `apps/triage/worker.py tests/test_prefilter.py`
  - `chore(planning): note pre-filter threshold miscalibration alongside 999.2 backlog`
    staging `.planning/STATE.md` and this plan directory

Do NOT push. `main` is already well ahead of `origin/main` and pushing is an explicit
operator action per project rule.
  </action>
  <verify>
    <automated>INFOTRIAGE_PG_DSN=postgresql://infotriage:infotriage_dev@127.0.0.1:22000/infotriage python -m pytest tests/ -q && python -m mypy apps/triage/worker.py tests/test_prefilter.py && python -m black --check apps/triage/worker.py tests/test_prefilter.py</automated>
  </verify>
  <done>Full suite green with zero new failures vs. baseline; mypy clean on both changed files; black --check clean; two commits exist with explicitly staged paths; nothing pushed; working tree contains no unintended stray changes (`git status --short` reviewed).</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| operator env -> triage worker | `INFOTRIAGE_PREFILTER_THRESHOLD` is operator-supplied; this task changes only its fallback, not its parsing or trust level. |
| ingested item text -> CCIR similarity gate | Unchanged by this task; the gate's fail-open behavior (D-07) is deliberately preserved. |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-LME-01 | Denial of Service (signal loss) | `process_item` pre-filter gate | high | mitigate | New default (0.70) sits strictly below the lowest similarity ever observed for any live item (0.7430 junk / 0.7452 genuine), so no real signal can be dropped. Task 1 forbids any change to the `>=` comparison or the two fall-through conditions. |
| T-LME-02 | Tampering | `INFOTRIAGE_PREFILTER_THRESHOLD` env var | low | accept | An operator who can set the worker's env can already alter triage behavior arbitrarily; the override is an intentional ops knob and its parse path is untouched. |
| T-LME-03 | Repudiation | `infotriage.audit` `pre_filter_skip` rows | low | accept | Skip-path audit + `enrichment.why` logging already exist (worker.py:252, :266) and are unchanged; Task 1 tests assert both still fire. |
| T-LME-SC | Tampering | package installs | n/a | n/a | No npm/pip/cargo installs in this task — no new dependencies. |
</threat_model>

<verification>
1. `INFOTRIAGE_PG_DSN=postgresql://infotriage:infotriage_dev@127.0.0.1:22000/infotriage python -m pytest tests/ -q` — zero new failures vs. baseline.
2. `python -m mypy apps/triage/worker.py tests/test_prefilter.py` — clean.
3. `python -m black --check apps/triage/worker.py tests/test_prefilter.py` — clean.
4. `grep -c "999\.2" .planning/STATE.md` >= 1.
5. Manual read-back of the worker.py diff: exactly one literal changed plus one comment block; gate logic byte-identical.
</verification>

<success_criteria>
- Default `INFOTRIAGE_PREFILTER_THRESHOLD` is 0.70, pinned behaviorally by tests that fail at 0.50.
- The threshold definition carries the corpus evidence and the out-of-scope note for recalibration.
- Production filtering behavior is unchanged (all live-band items still pass) — by design.
- STATE.md carries a one-line cross-reference to the 999.2 backlog class of issue.
- Full suite + mypy + black green; two explicit-path commits; nothing pushed.
</success_criteria>

<output>
Create `.planning/quick/260725-lme-fix-ccir-pre-filter-threshold-miscalibra/260725-lme-SUMMARY.md` when done.
Record in it: the observed RED output of the two new tests before the fix, the exact
pytest/mypy/black counts, whether any existing test needed a fixture adjustment (Task 1
step 5), and the two commit SHAs.
</output>
