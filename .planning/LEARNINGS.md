---
created: 2026-07-31
kind: cross-session concept-spike learnings
status: active
---
# InfoTriage — Cross-Session Learnings

> Project-level retention for patterns, pitfalls, preferences, and open
> questions surfaced across sessions. Each dated session below is a *layer*;
> staleness gets pruned via `/learn prune` (gstack skill) or via individual
> revisit. New sessions are pre-pended above older ones so most-recent
> context stays at the top.

## How to add a new session

1. Surface patterns manually, OR at session close reflect and run `learn`.
2. Add a new `### YYYY-MM-DD — <title>` section below `## Sessions`
   in reverse-chronological order.
3. Tag each entry with a type: **pattern** / **pitfall** / **preference** /
   **open-question** / **arch**.
4. Cross-link to the artifact the entry came from (commit SHA, file path,
   test name) so future readers can reproduce.
5. Skip one-time transient errors (network blips, rate limits). Only log
   genuine operational or domain discoveries that would save 5+ minutes in
   a future session.

---

## Sessions

### 2026-07-31 — Phase 8 Nyquist audit + Phase 11 sibling debt flag

Scope: `/gsd-validate-phase 8` (State A: existing `08-VALIDATION.md`,
`status: validated`, `nyquist_compliant: true`). Audit closed cleanly after
three amend iterations. Phase 8 UAT continuation paused mid-flight at
Test 2 of 5 awaiting verdict. Phase 11 sibling debt (`articles.discipline
= 0 across 499 rows despite column existing`) flagged out-of-band.

#### Patterns

- **State-A re-audit amend ceiling = 2-3 iterations.** Pattern: append
  audit block (iter 1) → surface API drift / map-row omission (iter 2) →
  polish + add in-session verification qualifier (iter 3). Plan for
  multi-amend; landmark commit message carries metric snapshot + "no
  gaps" for traceability. Source: Phase 8 commit chain
  `ab40b5d` → `887fe7f` → `69c27d0` on
  `.planning/phases/08-entity-resolution/08-VALIDATION.md`.

- **`Store.get_active_entities` vs `Store.get_all_entities` are siblings,
  not a rename.** Both methods coexist on the protocol
  (`libs/store/src/store/_protocol.py`) plus Postgres + InMemory
  implementations. Production callers (`apps/brief/vault_writer.py:368` +
  `apps/wiki/wiki_worker.py`) use the active-entities view; full-aggregation
  `get_all_entities` remains the canonical sibling. Audit-maps need BOTH
  rows. Detection: when suspecting rename, grep for both names in protocol
  + tests + callers; if both exist, they're siblings. Phase 8 map gained
  row 08-02-06 to capture the active-entities view alongside row 08-02-03.

- **Nyquist closeout signal is unambiguous.** Three amend iterations on
  the same `docs(phase-XX)` milestone commit, with explicit reviewer
  verdict "PHASE N IS NYQUIST-COMPLIANT (State A satisfied)". Closing
  reviewer pass issues the declaration; that's the green light to flip
  `*-UAT.md` frontmatter `status: testing → complete` on the final UAT
  test verdict.

- **`State A Step 6` map updates can ADD rows, not just flip checkboxes.**
  When re-auditing, `Step 6: Update Per-Task Map statuses` is permissive
  about *new* rows — protocol surfaces that evolve post-closeout
  (e.g., `get_active_entities` landing alongside `get_all_entities`)
  should be captured with their own map row + tests + callers, not
  retroactively folded into the original row. Source: this session's
  row 08-02-06 addition.

- **Mechanism-pass + live-data-caveat is a valid close posture when
  audit history documents the same observation.** Phase 8 close pattern:
  mechanism fully validated on injected data (`test_entity_links_cross_language`
  passes, HNSW index live, `LINK_THRESHOLD=0.92` verified); live corpus
  doesn't exercise the path because of an *upstream* weakness (language
  detector returning `und` for 98% of entities). Cross-check the audit
  history before deciding escalate-or-close; if a prior audit block
  already documents the matching observation, mechanism-pass + flag is
  the right close posture, not a parallel-debug invocation.

- **Live-verify any figure I'm citing in audit work.** State-A audit
  blocks tend to inherit historical numbers from prior audit blocks;
  those are file-readable but the *current session's* claim needs
  verification in-session. Pattern: include "(verified in-session
  YYYY-MM-DD via `docker exec infotriage-postgres psql …`)" qualifier
  next to figures the audit asserts.

#### Pitfalls

- **Don't trigger debug agents when audit history already names the
  limitation.** Cross-language linking — mechanism tested green
  (`tests/test_store_entities.py::test_entity_links_cross_language`
  passes, HNSW index live on `infotriage.entities.embedding` with
  `vector_cosine_ops m=16 ef_construction=64`, `LINK_THRESHOLD=0.92`
  confirmed at `apps/triage/entities.py:33`). Live corpus shows
  0 cross-language merges attributable to upstream language detector
  returning `und` for 98% of entities. Same observation documented in
  `08-VALIDATION.md` "Validation Audit 2026-07-24" audit-block
  "Separately observed" paragraph. Cost of gratuitous parallel-debug
  spawn: 5+ min agent time per case. The user's discriminator on
  similar issues going forward: "if you consider this a real issue
  (not a known limitation), I'll spawn parallel debug agents." Use it.

- **Cross-phase verification cycles don't cross-contaminate.** Phase 11
  `articles.discipline = 0 across 499 rows despite the column existing`
  surfaced out-of-band during Phase 8 verification; held for Phase 11's
  own verification cycle rather than folded into Phase 8. Discipline:
  acknowledge in conversation, park debt for the owning phase's verify
  step (most likely `/gsd-validate-phase 11` given Phase 11's existing
  VERIFICATION.md-missing debt per cross-phase audit).

#### Preferences

- **One-test-per-response pacing for conversational UAT.** Subjective
  verdicts want evidence-rich per-test presentation: header → expected →
  mechanism table → data table → reading → verdict options (pass / issue
  / skip / blocked). Don't bundle tests; user drives the cadence. Bundle
  evidence collection but not verdict adjudications.

#### Open questions

- **Test 5 scope for Phase 8 UAT.** Default: vault note `[[Name]]`
  wikilinks + cosmetic dup-name deferred. Two cleaner paths: Path A
  (narrow — wikilinks only; clean close with cosmetic staying deferred)
  vs Path B (wider — bug-fix `_entity_names()` dedup in
  `apps/brief/vault_writer.py` first, then Test 5 covers both; closes
  latent cosmetic surface). Pre-decide at Test 4 verdict time, not
  under pressure at Test 5.

### 2026-08-01 (phase-11-taxonomy) — INT-taxonomy backfill landed; debt item #1 closed

Scope: Closed parked-debt item #1 from
`.planning/phases/11-socmint/11-VALIDATION.md` §1 — "Schema-discipline
backfill debt (PARKED FROM PHASE 8 AUDIT)" — by adding
`libs/store/sql/010-backfill-discipline.sql` (idempotent + implicitly
atomic UPDATE), `SOURCE_TYPE_TO_INT_DISCIPLINE` +
`VALID_INT_DISCIPLINES` constants in
`libs/contracts/src/contracts/_phase11_gates.py`, and a per-ingest
contract test `test_all_source_types_mapped_to_valid_int_discipline`
in `tests/test_phase11_gates.py`. One atomic milestone commit; 3 code
files + 2 doc files.

#### Patterns

- **Source-of-truth mapping lives in TWO surfaces — Python dict (runtime)
  + SQL CASE (one-shot backfill) — with comment-based lock-step
  enforcement.** Per-ingest contract test asserts the Python dict is
  internally consistent (every value passes Pydantic regex + lives in
  `VALID_INT_DISCIPLINES`). The SQL file's header comment cites the
  Python dict as the canonical reference; future drift between them
  is mitigated by the comment but not enforced automatically until the
  parity test ships.

- **`ELSE NULL` (no fallback) surfaces drift loudly.** When a future
  adapter introduces a new `source_type` not in the dict, the migration
  leaves `discipline` NULL for those rows — the per-ingest contract
  test fails (subset check + Pydantic regex check + vocabulary
  membership check) rather than silently labeling everything OSINT.
  Pattern: prefer explicit failure over silent fallback for taxonomy
  backfills where the corpus is small enough to audit by hand.

- **Single-statement UPDATE is implicitly atomic — drop BEGIN/COMMIT.**
  Initial draft had `BEGIN; ... COMMIT;` wrapper for safety (mirroring
  how the operator might write multi-statement work). code-reviewer
  flagged this as a NEW pattern in the project (existing migrations
  001-009 don't wrap transactions). Dropped the wrapper after
  confirming: a single UPDATE on `infotriage.articles` is one
  transaction at the SQL level (Postgres wraps it implicitly); the
  BEGIN/COMMIT was redundant surface.

- **`acled → OSINT`, NOT `OSINT/DOCEX`.** Initial draft used the
  sub-discipline `OSINT/DOCEX` to capture ACLED's open-source-curated
  conflict-data nature. Pytest failed: the `Item.discipline` Pydantic
  regex `^(OSINT|SOCMINT|MASINT|GEOINT|SIGINT|HUMINT|MASINT/AIS)$`
  rejects `OSINT/DOCEX` (only `MASINT/AIS` is allowed as a
  sub-discipline form). The fix: drop the sub-discipline refinement;
  `OSINT` is the correct umbrella. Lesson: regex constraints enforce
  taxonomy at test time; if you can't name a discipline that fits the
  regex, the question "should I have a sub-discipline here?" is the
  wrong question — the right question is "is this really a sub-discipline
  of OSINT, or is the macro-discipline precise enough?"

#### Pitfalls

- **Pydantic regex enforcement IS the safety net for taxonomy
  drift.** Caught the `OSINT/DOCEX` mistake at test time before any
  production data was committed to `discipline` column. Discipline:
  trust the regex; let it surface ambitious sub-discipline designs
  that don't fit the canonical vocabulary.

- **Initial bulky multi-file str_replace failed because str_replace
  operates ONE file at a time (the tool's contract).** First attempt
  packed 4 replacements targeting 3 different files into one call;
  only the file whose path was specified had its sub-edits attempted,
  and the rest were silently skipped because the OLD string wasn't
  found in that specific file. Lesson: when you need to fix N files,
  you need N separate str_replace calls (or use write_file + careful
  re-read for tiny files). Don't trust the human-readable description
  in the str_replace prompt — the tool's path argument defines the
  single target.

- **Defer automated Python↔SQL parity test to a follow-up.** Both
  surfaces have the mapping; only the Python side has automated
  enforcement. A future addition to the SQL without a corresponding
  dict update will go undetected. Acceptable risk for this commit
  (well-flagged in the SQL header comment + 11-VALIDATION.md); but
  `tests/test_phase11_parity.py` should land in the next session or
  the lock-step drift hazard silently returns.

#### Preferences

- **Per-ingest contract test = 3 layered assertions: subset + value
  vocabulary + Pydantic regex.** Single test function asserts (a)
  expected source_types in the dict subset, (b) every value in
  `VALID_INT_DISCIPLINES`, (c) every value passes `Item.discipline`
  regex via Pydantic Item construction. Three failure-modes
  distinguished (missing source_type vs off-vocabulary discipline
  vs regex-rejected) clearly from the assert messages.

- **Drift-detection surfaces loud, not silent.** When taxonomy
  decisions have a "what if a future case arrives?" dimension,
  prefer the design that surfaces the unknown loudly (NULL > OSINT;
  assert > log-and-continue) over the design that silently paper-
  over the gap.

#### Open questions

- **`tests/test_phase11_parity.py` deferred.** Python↔SQL bytecode-
  level parity test — read the SQL file, regex-parse
  `(WHEN 'x' THEN 'y')` tuples, assert byte-equivalence with
  `SOURCE_TYPE_TO_INT_DISCIPLINE`. ~20 lines. Flag on next session;
  README mentions this in 11-VALIDATION.md parked debt note. Until
  landed, lock-step drift hazard is ACCEPTED — the per-ingest
  Python test catches dict-side mistakes; SQL-side additions don't
  trip any test today.

- **`barentswatch` vs `ais` source_type alias.** The dict carries
  both as → `MASINT/AIS`. If production code (per the
  `apps/ingest-barentswatch/` adapter) only ever emits one, the
  other is either a legacy alias (correct for backfill) or dead code.
  Need a `git grep 'source_type.*=\s*["\']?ais["\']?'` for
  ground truth. Cheap investigation; resolution: keep both if
  legacy rows exist.

### 2026-08-01 (flip) — 3 test-side bug fixes landed; baseline flipped 674/3/0 → 677/0/0

Scope: Closed the open debt documented in
`.planning/phases/11-socmint/11-INGEST-TEST-FIXES-PLAN.md` from the
2026-08-01 earlier-cycle session. Operator chose **fix-then-push
(option (a))** as the resolution to Open Question #1 previously
recorded in this file. Result: 674/3/0 baseline at `6dbac4b`
flipped cleanly to 677/0/0 in 43.97s; 0 production-code regressions.

#### Patterns

- **TIME-BOMB test fixture = relative-to-now with defensive margin,
  never absolute calendar date.** The hardcoded `datetime(2026,7,21)`
  in `tests/test_ingest_telegram.py::fake_message` went stale on
  2026-07-25 against the `parse_since("7d")` filter window. Fix shape
  is ALWAYS relative (`datetime.now(tz=utc) - timedelta(minutes=N)`).
  Margin choice: 5 minutes — clears any typical `since` window
  (`7d`, `24h`, `1h`) AND is forward-safe against hypothetical tighter
  windows. Width (1m vs 5m vs 1h) trades off between maximally-fresh
  fixture state vs boundary-edge risk for future tight `since`
  values; 5 minutes is the sweetspot per `thinker-with-files-gemini`
  recommendation. The bytes-only invariant: a fixture that doesn't
  advance with the calendar will eventually go stale silently;
  only `make test-safe` (full live-Postgres run) catches it because
  narrower `pytest -k foo` invocations don't exercise the path that
  fails first.

- **env-var leak in pytest = autouse fixture at module level, not
  inline `monkeypatch.delenv` per test.** The `INFOTRIAGE_YOUTUBE_TRANSCRIBE`
  env-var leaked from ambient shell/project-`.env` into the dry-run
  test path at `tests/test_ingest_youtube.py::test_ingest_r2_dual_output`,
  routing the production code at
  `apps/ingest-youtube/youtube_ingest.py` into audio/STT. Inline fix
  = 1 line of `monkeypatch.delenv`, but only covers the failing test.
  Side-channel risk: 3 OTHER tests in the same file (`r2_idempotent_rerun`,
  `r2_empty_channel`, `max_n_config_reaches_yt_dlp_list`) would also
  attempt the audio/download path if the env var leaks — they pass
  today because the env var isn't set in our local shell. Autouse
  fixture covers all 9 tests at once (1 edit, future-proof) AND
  carries a docstring pointing future maintainers to
  `monkeypatch.setenv` for tests that DO want the var. Choice =
  autouse scope (file-wide) unless a single test in the file needs
  env-var *between* tests (false here).

- **Test-side bug class taxonomy.** When `make test-safe` surfaces
  failures, classify each as one of: TIME-BOMB (hardcoded date goes
  stale with calendar), env-var-leak (ambient shell/repo state
  unread by `monkeypatch`), parametric-skip (`@pytest.mark.skipif`
  becomes permanent suppression instead of live exercise). Different
  classes have different fix shapes. The 3 surfaced failures here
  split as 1 TIME-BOMB (affecting 2 tests via shared fixture) + 2
  env-var-leak (1 test directly, 3 tests indirectly). Pattern:
  classify the bug, then the fix design follows from the class.

- **`monkeypatch.setenv` layers correctly over `@pytest.fixture(autouse=True)`
  that does `delenv`.** The autouse fixture runs first with its own
  monkeypatch instance; the test function's `monkeypatch.setenv`
  runs later and overrides for the test scope. Both undo at
  teardown. So tests that explicitly want the env var set (e.g.,
  `test_transcribe_default_env_var`, `test_ingest_transcribe_env_var_enables_transcription`)
  don't break when the autouse fixture is added. Confirmed via 21/21
  green on the file post-fix.

#### Pitfalls

- **Don't bundle test fix + unrelated work in one commit.** Per
  project milestone-commit policy, scope each fix to the bug class.
  This commit bundles code (2 test files) + docs (STATE.md +
  LEARNINGS.md) ONLY because the docs ground the baseline flip
  in-file; an unrelated fix would force a second commit.

- **Re-derive the Open Question resolution path.** Open Question #1
  (this file) was "fix-bugs before or after the next push?" The
  answer chosen (fix-then-push) was driven by prior LEARNINGS.md
  `Preferences -> Pre-push canonical order`: `make test-safe`
  must precede push. Doing push-then-fix would create a drift window
  where the unpushed chain has a 674/3 baseline that no longer
  reflects ground truth. Pick fix-then-push unless explicitly
  countermanded.

- **Avoid code-only `git commit` bodies that don't capture the
  pre-fix baseline.** Future maintainers reading the diff need the
  prior baseline (`6dbac4b` = 674/3/0/66s) shown explicitly in the
  commit message body, not just "fix is good." Discipline: cite
  the prior SHA + prior numbers in the body, so the commit is
  self-documenting.

#### Preferences

- **Bug-fix commit message body = pre-fix baseline + post-fix
  baseline + verification gates + thinker/reviewer verdicts.** Tested
  pattern in this commit: the body quotes 674 / 3 / 0 / 66s as
  pre-state, 677 / 0 / 0 / 43.97s as post-state, names the thinker
  and reviewer SHIP verdicts, and references
  `.planning/phases/11-socmint/11-INGEST-TEST-FIXES-PLAN.md` for
  full root-cause analysis. Future commits in this class should
  match this template unless the bug class changes (e.g.,
  parametric-skip fix doesn't need a "tests currently suppressed"
  reference).

#### Resolved (formerly Open Questions)

- **Fix the 3 surfaced test-side bugs before or after the next push?**
  — RESOLVED **fix-then-push (option (a))**, this commit. Cleanup
  rationale + verification steps preserved above (Patterns + Pitfalls
  bullets). See `.planning/phases/11-socmint/11-INGEST-TEST-FIXES-PLAN.md`
  for the original analysis.

### 2026-08-01 (push gate) — `make test-safe` as canonical pre-push verification

Scope: Ran `make -f ops/Makefile test-safe` end-to-end against a
throwaway test Postgres (port 22062, distinct from prod 22000); used
the resulting 674 passed / 3 failed / 0 regressions baseline as the
canonical pre-push gate for the operator-authorized push that landed
3 commits to origin/main. Recorded for next-session pre-push ritual.

#### Patterns

- **`make test-safe` = canonical PRE-PUSH gate.** Spawns a throwaway
  Postgres test container on port 22062 (NOT prod 22000), runs the
  full `pytest tests/` matrix against it with
  `INFOTRIAGE_TEST_DSN` set, then trap-teardowns the container.
  Belt-and-suspenders DSN safety: `scripts/check_test_dsn.sh`
  (shell-layer DSN-port guard, called by the Makefile before docker
  compose up) + `tests/test_dsn_safety.py` (always-run pytest guard
  that fails on any prod-port DSN under `tests/`). Three layers
  because prod-DSN reachability from a test container is
  catastrophic — a single `pytest` run connecting to prod wipes
  live data. Source: `ops/Makefile` target `test-safe:`,
  `scripts/check_test_dsn.sh`, `tests/test_dsn_safety.py`. Run it
  before every `git push origin main`.

- **`make test-safe` < `make integration` (scoping, not quality).**
  test-safe = throwaway Postgres + pytest only (fast path, single
  observed runtime = 66s on the 2026-08-01 674-test baseline).
  integration = test-safe plus RabbitMQ live consumer contention
  (broader scope; runtime + test-count not observed this session
  — see `ops/Makefile` `integration:` target for ground truth).
  Structural discriminator: integration's stdout adds a
  `infotriage-rabbitmq-test` container lifecycle block that
  test-safe lacks. Pattern: `test-safe` for every pre-push gate
  ritual; `integration` for full-stack rehearsal before milestone cuts.

- **2026-08-01 baseline = 674 / 3 / 0 / 66s.** Full pytest matrix through
  test-safe = 674 passed, 3 failed, 0 production-code regressions,
  66s elapsed (baseline pinned at `208a598`; pre-`208a598` lines
  may differ). The 15 parametric Postgres variants in
  `tests/test_store_entities.py` that were previously carry-over-skipped
  fired for the first time and all 15 PASSED — InMemoryStore/db_live
  path equivalence asserted by `08-VALIDATION.md` (6959e4d) is now
  ground truth, not assertion. The 3 failures are pre-existing test-side
  bugs classified in `.planning/phases/11-socmint/11-INGEST-TEST-FIXES-PLAN.md`
  (open at `da2ca0d`): 2 TIME-BOMB telegram `fake_message` fixtures
  (hardcoded date 2026-07-21, stale vs 2026-08-01 via `parse_since("7d")`)
  + 1 `INFOTRIAGE_YOUTUBE_TRANSCRIBE` env-var leak in youtube dry-run
  test (needs `monkeypatch.delenv`). Zero `.py`/`.sql`/`.yml`
  production-code regressions — all test-side.

- **THREE-LAYER DSN safety defense.** Three independent layers:
  (1) `scripts/check_test_dsn.sh` — shell-side port guard that
  runs before compose-up, rejects prod-port / unparseable DSN;
  (2) `tests/test_dsn_safety.py` — always-run pytest guard that
  fails any future prod-port regression at unit-test time;
  (3) throwaway Postgres uses port 22062 (NOT prod 22000) so the
  test container cannot physically reach prod by socket even if
  Layers 1+2 both fail. Defense in depth: shell + always-run +
  port distinct. Don't remove Layer 3 assuming Layers 1+2 are
  "enough" — the three layers cover different failure modes
  (operator misconfig / accidental regression in code /
  reachability-by-socket).

#### Pitfalls

- **Pre-existing 3-failure baseline can mask shipped-code regressions.**
  The 674/3 baseline is the new normal for any future pre-push run.
  If future `make test-safe` returns 671/6 instead of 674/3, that
  delta = 3 new failures = real regression. Don't accept the 3
  pre-existing failures as "the baseline;" accept them ONLY as
  "this phase's acknowledged debt" counted from the SPECIFIC
  baseline of `da2ca0d` / `208a598` / after the 11-INGEST-TEST-FIXES
  Plan lands. Pattern: diff future test-safe output against THE
  baseline, not the historical "approximately N passed" figure.

- **Don't conflate `make test-safe` and `make integration` durations.**
  Only the 66s observation for test-safe is grounded (this session);
  integration runtime + test-count are unobserved here — defer
  duration claims until an integration run is captured. Pick the
  path explicitly per task: pre-push ritual = test-safe; full-stack
  rehearsal (e.g., before milestone cut) = integration.
  Cleanest discriminator: test-safe shows Postgres spin-up +
  tear-down lines in stdout; integration adds
  `infotriage-rabbitmq-test` container lifecycle lines. Watch for
  those in the invocation output to know which path ran.

#### Preferences

- **Pre-push canonical order = `make test-safe` → `git status` →
  `git log origin/main..HEAD` → operator push.** test-safe runs
  first (catches any shipped-code regressions the prior baseline
  wouldn't have caught), then a triple-check of working-tree state
  (no secret-leaks / uncommitted binaries), then drift count
  (re-fetched immediately before push, not at session start), then
  operator is delegated. The 12+ commits ahead of origin/main
  pre-existing in earlier sessions was a project-rule signal —
  not a push trigger. The push is gated on fresh test-safe output.

#### Open questions

- **Fix the 3 surfaced test-side bugs before or after the next push?**
  Two paths: (a) fix-then-push — cleanly flip 674/3 → 677/0
  baseline before more code lands, preventing drift; (b)
  push-then-fix — risk the baseline silently drifting while
  Phase 12 work proceeds. Operator call required. Tracked in
  `.planning/phases/11-socmint/11-INGEST-TEST-FIXES-PLAN.md`.

### 2026-08-01 — Phase 8/9/10 audit-chain full closure + Phase 11 validation (State B) + push pack

Scope: Continued Phase 8 UAT, Phase 9 / Phase 10 VALIDATION.md reopen
(State B for both — no prior VALIDATION.md, only PLAN + SUMMARY(s)),
Phase 11 VALIDATION.md State B reconstruction with the parked
schema-discipline gap analysis (root-cause + falsification + backfill
debt), and operator-authorized push of the catchup chain to
`origin/main`. Audit chain now in sync with `origin/main` at SHA
`e3e7880`.

#### Patterns

- **State B reconstruction follows the same amend ceiling as State A.**
  Phase 9 + Phase 11 both lacked any prior `*-VALIDATION.md` despite
  having PLAN + SUMMARY(s). Reconstruction took 3 amend iterations
  per phase: initial write → reviewer-caught factual fix
  (Phase 11: migration slot 009→010; §1(a) historical-data framing
  softening) → final polish (Phase 10: angle-bracket literal removal;
  Phase 11: dry-run honesty about 2 pre-existing env-dependent
  failures). Budget 3 amend rounds per State B flagship.

- **Push pack atomization = one commit per domain, not one mega-commit.**
  The catchup chain shipped as 3 atomic commits:
  `acf6783 docs(phase-08): UAT live verification snapshot (2026-07-31)`
  + `dab7a52 docs(readme): refresh test suite status (671 passed / 3
  failed, 2026-07-31)` + `e3e7880 chore(planning): add LEARNINGS.md
  cross-session retention file`. Same domain-per-commit pattern as
  the earlier `docs(readme)` vs `docs(codebase)` split — easier to
  grep back from `origin/main` and easier to selectively revert.
  Source: post-push `code-reviewer-minimax-m3` verdict PASS with
  atomization discipline explicitly praised.

- **Live `pytest` output grounds any audit/UAT/VALIDATION citation.**
  Pattern: for any figure appearing in a docs-only audit artifact
  (counts, durations, percentages), cite the verbatim stdout from a
  real `python -m pytest` invocation executed in the same turn.
  The Phase 10 UAT Test 4 note initially cited "7/7 passed in 0.28s"
  — fabricated; replaced with `7 passed, 667 deselected in 0.50s`
  from a live `pytest -q -k <selector>` invocation. Closed by the
  reviewer in one round-trip; the discipline going forward is
  run-then-write, never write-then-extrapolate.

- **Subagent hypothesis must be falsified before committing to a
  planning artifact.** planner-with-files-gemini ranked H1
  (Postgres UPSERT path omits `discipline` column) as highest prior
  for Phase 11 schema-discipline gap analysis. Ground-truth via
  `grep -nE 'discipline|admiralty_reliability'
  libs/store/src/store/_postgres.py` showed H1 was FALSIFIED: UPSERT
  path *does* write the column correctly. True root cause: legacy
  ingest adapters (pre-007) never populated `Item.discipline`, so
  existing rows have NULL and new ingest paths (telegram,
  barentswatch) tag correctly. Backfill is the fix, not a write-path
  bug. Without this falsification discipline, Phase 11 VALIDATION.md
  would have falsely attributed the gap to the wrong layer →
  false-positive regression investigation.

- **Migration slot factual accuracy = grep before naming.** First-pass
  VALIDATION.md drafted named `libs/store/sql/009-backfill-discipline.sql`
  but `009-articles-body.sql` already exists; real slot = `010`.
  Pattern: before naming any new migration path in a planning doc,
  verify the slot number via `ls libs/store/sql/`. This caught a
  would-have-shipped filename error before commit.

- **pytest `-k` substring counting = enumerate substrings, then
  verify via `--collect-only`.** Phase 10 UAT Test 4 cites 7 named
  tests across 5 substrings: `test_dgx_backend` (2),
  `test_select_backend` (1), `test_recall_dgx_cross_language` (1),
  `test_recall_synthesis_uses_dgx` (1), `test_recall_synthesis_prompt_`
  (2) = 7. Verify total via
  `pytest --collect-only -q -k '<selectors>'` before claiming the
  figure in audit notes — substring overlaps can inflate or deflate
  the count.

- **Angle-bracket placeholder literals break Markdown rendering —
  always write the verbatim flag.** Audit note originally cited
  `pytest -q -k [N selectors]` (square-bracket shorthand standing
  in for the unshown 5-substring selector). Some Markdown→HTML
  pipelines (pandoc `markdown_strict`, GitLab `:render_as_plain_text`,
  some Obsidian export pipelines) interpret angle-bracket syntax as
  raw HTML and strip contents. Replaced with the verbatim `-k`
  substring used in the live invocation. Pattern: planning artifacts
  show real command syntax (backtick-wrapped verbatim flags), never
  angular placeholders. Self-defeating when the bullet teaching the
  rule contains the very literals it warns against.

- **LEARNINGS.md update cadence = single pre-pend per session.** Each
  session adds one `### YYYY-MM-DD — <title>` block in
  reverse-chronological order; entries tagged
  **pattern** / **pitfall** / **preference** / **open-question** /
  **arch**; cross-linked to commit SHA + file path + test name so
  future readers can reproduce. Atomic pre-pend keeps audit trail
  clean and makes git-fast-forward easy.

#### Pitfalls

- **LLM-estimated test durations are not test results.** "0.28s"
  elapsed-time was fabricated from a smaller test baseline; real
  elapsed time was 0.50s across 7 named tests + 667 deselected. Cost:
  one reviewer round-trip to ground-truth. Discipline: cite only
  numbers from `python -m pytest` stdout captured in this turn.

- **`-M` vs `-m` flag typo silently kills a git commit.** `git commit
  -M '<msg>' -m '<body>'` (uppercase M) is NOT a recognized commit
  subflag — git prints help, leaves the file staged, no commit
  lands. Discipline: lowercase `-m` for all multi-paragraph commit
  messages; verify with `git log -1 --oneline <file>` immediately
  after every commit.

- **3-failure baseline can confuse new test selectors.** Phase 11
  pytest run surfaced 2 pre-existing env-dependent failures
  (`test_ingest_emits_item_with_discipline_and_reliability` +
  `test_ingest_dry_run_does_not_persist`) that are part of the
  committed 3-failure baseline. Audit note must explicitly name them
  as pre-existing and matching the committed baseline so a future
  audit doesn't conflate them with new Phase 11 regressions.

- **Already-committed → don't re-commit.** Mid-session the user
  asked to commit `.planning/LEARNINGS.md` "as a docs-only milestone
  commit." File was already part of the push pack at `e3e7880`.
  Discipline: before any commit action, `git log --oneline -- <file>`
  + `git status --short` to verify it's actually uncommitted; if
  already committed, flag the redundancy rather than blindly
  emit an empty commit (which would break Milestone-commit
  discipline). Pattern preserves audit trail integrity.

- **Pre-flighting push = catch all uncommitted state before
  delegating.** Operator-authorized push preceded by reading all
  uncommitted working-tree files for size + secret-scan + diff-stat
  check; explicit `merge-base HEAD origin/main` divergence check
  confirmed purely-ahead (no divergent commits to reconcile).
  Without this pre-flight, a push with unexpected binary blobs or
  credentials would only surface after the chain landed.

#### Preferences

- **`code-reviewer-minimax-m3` closeout is policy, not optional.**
  Any docs-only milestone commit touching `*-VALIDATION.md` /
  `*-UAT.md` / `README.md` / `.planning/LEARNINGS.md` gets a final
  reviewer pass before the commit lands. Cost: one round-trip;
  benefit: catches migration-number typos, angle-bracket
  placeholders, pre-existing-baseline-vs-new-regression conflations,
  and atomization slips before push. Single-knob config: spawn it
  after every `docs(...)` / `chore(planning...)` commit.

- **Write artifacts from real test output this turn; never cite a
  number not produced by `basher` in the same session.** Goes
  hand-in-hand with the falsification discipline above. Concrete
  rule: in any `*-VALIDATION.md` / `*-UAT.md` / `LEARNINGS.md`
  pattern bullet that mentions a count or duration, the prior turn
  must contain a `basher` invocation whose stdout includes the
  exact figure.

- **Push is operator-authored only, except where explicitly
  consented.** Per CLAUDE.md + project rule, push to `origin/main`
  is operator-only — never auto-push even when local is 12+ commits
  ahead. The exception: user message includes the literal phrasing
  "Push to origin/main" without re-asserting the operator-only rule,
  which means it IS explicit consent. Use that phrasing discriminator
  rather than guessing. Without it, the right move is `git status`
  + `git log origin/main..HEAD --oneline` summary + delegate decision
  to the operator.

#### Open questions

- **Phase 11 backfill taxonomy: INT collection disciplines vs
  PMESII-PT hybrid.** Validation draft assumes INT taxonomy (OSINT,
  HUMINT, SIGINT, MASINT, GEOINT, SOCMINT) consistent with what the
  Phase 11 ingest adapters (telegram = SOCMINT, barentswatch =
  MASINT/AIS) actually emit. But `.planning/research/pmesii-hybrid-definitions.md`
  aligns with PMESII-PT (PMESII+Political). Mismatch is real; need
  operator decision before `libs/store/sql/010-backfill-discipline.sql`
  ships. Default-fallback: INT taxonomy (matches adapter emission
  already in production rows); wider alternative: PMESII-PT hybrid
  (research-favored but requires schema-mapping work + alignment
  with existing `_phase11_gates.py` constants). Pre-decide before
  `/gsd-discuss-phase 12` reopens Phase 11's backfill work.

- **Phase 8 UAT Tests 2-5 still queued.** Phase 8 verification
  paused in 07-31 at Test 2/5 (vault wikilinks + cosmetic dup-name
  decision); Test 5 scope decision (Path A vs Path B) from the
  07-31 open question still pending. Resume with `/gsd-verify-work
  8` at Test 2 verdict when ready.

- **Local main vs origin/main drift posture.** Post-push `LOCAL ==
  ORIGIN` at SHA `e3e7880`; any new work adds community commits
  again until next push. Per project rule, push is operator-only;
  new sessions should flag drift on `git status` pre-flight.

---

## Cross-references

- **Phase 8 validation (closed, Nyquist-compliant, awaiting UAT test
  continuations):** `.planning/phases/08-entity-resolution/08-VALIDATION.md`
- **Phase 8 UAT (in flight, paused at Test 2 of 5 awaiting verdict):**
  `.planning/phases/08-entity-resolution/08-UAT.md`
- **Phase 11 sibling debt (held for Phase 11's verification cycle):**
  `articles.discipline` column-population gap — 499 of 499 articles
  have `discipline = 0` despite the column existing. Suspected ingest
  path: `apps/ingest-acled/` or whichever ingest surface is responsible
  for discipline-mapping. Needs root-cause + backfill + per-ingest
  contract test when Phase 11 opens.

- **Phase 11 verify-work bug-fix sub-task (3 surfaced test-side bugs):**
  `.planning/phases/11-socmint/11-INGEST-TEST-FIXES-PLAN.md` —
  documents the 3 pre-existing failures surfaced by `make test-safe`
  on 2026-08-01 (2 TIME-BOMB telegram fixtures in
  `tests/test_ingest_telegram.py` + 1 `INFOTRIAGE_YOUTUBE_TRANSCRIBE`
  env-var leak in `tests/test_ingest_youtube.py`). Fix paths in the
  plan; expected effort ≤15 minutes; verification gate = same
  `make test-safe` baseline flipped to 677/0.
- **Pre-push gate ritual:** `make -f ops/Makefile test-safe` →
  `git status` → `git log origin/main..HEAD` → operator push.
  Belt-and-suspenders DSN safety =
  `scripts/check_test_dsn.sh` + `tests/test_dsn_safety.py` + throwaway
  Postgres on port 22062 (NOT prod 22000). Baseline 66s/674-pass/3-fail
  pinned at `208a598` (post-this-commit).

## Versioning

This file was created 2026-07-31. Future sessions pre-pend their dated
section above the current top entry. Stale entries should be pruned via
`/learn prune` when the underlying code changes (e.g., LINK_THRESHOLD
moves off 0.92, oracle re-validation reaches a different conclusion,
the `apps/ingest-acled/` discipline pipeline gets fixed or split).
