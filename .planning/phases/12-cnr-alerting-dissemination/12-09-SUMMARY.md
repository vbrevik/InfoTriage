---
phase: 12-cnr-alerting-dissemination
plan: 09
subsystem: alerting
tags: [prohibitions, airgap, adr-015, structural-guards, ast, yaml, operator-uat]

requires:
  - phase: 12-cnr-alerting-dissemination (plans 12-01..12-08)
    provides: "the complete Phase 12 alerting lane — dual-trigger emitter, dedupe,
      throttle, hourly digest, outbox retry/DLX, and body-populated Item contract"
provides:
  - "tests/test_alerting_prohibitions.py — 9 structural guards encoding SPEC's five
    prohibitions (P1 airgap, P2 excerpt-bound, P3 scorer-input, P4 CAT I-only, P5
    no-independent-record) plus the AC8 failure-isolation proof"
  - "Every guard is structural (YAML parse, Python AST, or observed runtime behavior) —
    never a raw-text grep a source comment could both trip and satisfy"
  - "docs/adr/ADR-015 amendment section '## Amendment — superseded by 12-SPEC.md
    (Phase 12 planning)' reconciling every pre-SPEC value with the locked SPEC"
  - "Operator UAT checkpoint (Task 3) — OPEN, blocking, awaiting operator approval
    (deep-link tap-through, link fields, digest wording, P5 judgment)"
affects: [12-VALIDATION.md (phase closeout)]

tech-stack:
  added: []
  patterns:
    - "Structural-guard test philosophy: a prohibition is only guarded when a source
      comment cannot satisfy the check. YAML parsing discards comments; AST walks
      exclude docstrings; behavior tests observe the running system."

key-files:
  created:
    - tests/test_alerting_prohibitions.py
    - .planning/phases/12-cnr-alerting-dissemination/12-09-SUMMARY.md
  modified:
    - docs/adr/ADR-015-cnr-alerting-channels-and-payload.md
  not_modified_intentionally:
    - docker-compose.yml (freshrss/rssbridge non-loopback exposure flagged as debt, see Deviations)

key-decisions:
  - "Three documented deviations from the plan's literal acceptance criteria, all
    strengthening or correcting the guard rather than weakening it — full record in the
    test file's module docstring and the Deviations section below."

requirements-completed: [ADR-003]

coverage:
  - id: D1
    description: "P1 airgap guard — every published port in docker-compose.yml is
      loopback-only (except the two documented pre-ADR-016 legacy services), and the
      ntfy/alerting service definitions carry no upstream/relay/forwarding/hosted-push
      configuration token (ADR-016, T1-02)"
    requirement: "ADR-003"
    verification:
      - kind: unit
        ref: "tests/test_alerting_prohibitions.py#test_p1_no_off_host_egress"
        status: pass
    human_judgment: false
  - id: D2
    description: "P2 excerpt guard — a 5000-char rationale yields an excerpt ≤500 chars;
      no SQL string constant under apps/alerting references the body column; the payload
      is byte-identical whether or not item.body is populated (SPEC R8, P2)"
    requirement: "ADR-003"
    verification:
      - kind: unit
        ref: "tests/test_alerting_prohibitions.py#test_p2_excerpt_bounded_and_body_free"
        status: pass
    human_judgment: false
  - id: D3
    description: "P3 scorer-input guard — the scorer's prompt never contains the article
      full-text key, still contains title and summary; a long summary passes through
      verbatim (input contract not widened)"
    requirement: "ADR-003"
    verification:
      - kind: unit
        ref: "tests/test_alerting_prohibitions.py#test_p3_scorer_input_unchanged"
        status: pass
    human_judgment: false
  - id: D4
    description: "P4 tier guard — tier II, tier Routine, absent tier, and null tier each
      produce zero egress on cnr-cat-i (SPEC R1, P4)"
    requirement: "ADR-003"
    verification:
      - kind: unit
        ref: "tests/test_alerting_prohibitions.py#test_p4_non_cat_i_silent"
        status: pass
    human_judgment: false
  - id: D5
    description: "P5 no-independent-record guard — alert_state's column set holds no item
      prose beyond the digest title; the alerting worker registers exactly one HTTP
      handler (health) and no module imports a routing framework (SPEC R8, P5)"
    requirement: "ADR-003"
    verification:
      - kind: unit
        ref: "tests/test_alerting_prohibitions.py#test_p5_no_independent_record"
        status: pass
      - kind: judgment
        ref: "Task 3 checkpoint, P5 item — 'the SAB stays canonical' needs operator eyes"
        status: open
    human_judgment: true
  - id: D6
    description: "AC8 failure-isolation proof — the emit path fires a complete 7-field
      payload when the article's full-text field is NULL; body wiring never blocks alert
      firing (SPEC AC8)"
    requirement: "ADR-003"
    verification:
      - kind: unit
        ref: "tests/test_alerting_prohibitions.py#test_ac8_body_null_isolation"
        status: pass
    human_judgment: false
  - id: D7
    description: "ADR-015 reconciled with the locked SPEC — amendment section records the
      7-field payload set (with intentional pmseii_tags spelling), pipe separator, 500-char
      cap, obsidian://open?vault= deep-link form, R3 sliding tiers + hourly digest, both
      Open Items resolved, A-01 recorded, and the body-excerpt field now forbidden (P2)
      rather than deferred"
    requirement: "ADR-003"
    verification:
      - kind: manual
        ref: "docs/adr/ADR-015-cnr-alerting-channels-and-payload.md#Amendment"
        status: pass
    human_judgment: false

duration: ~25min (Tasks 1-2)
completed: 2026-08-02
status: checkpoint
checkpoint_note: "Task 3 (operator UAT) is a blocking human-verify gate — see the
  Task 3 section below for exactly what needs operator eyes. Plan seals on approval."
---

# Phase 12 Plan 09: Prohibitions P1–P5, AC8 isolation, ADR-015 reconciliation Summary

**Tasks 1–2 complete; Task 3 (operator UAT) OPEN.** All five SPEC prohibitions are now
encoded as **structural** mechanical guards that a source comment cannot satisfy; the AC8
failure-isolation guarantee is proven; and ADR-015 no longer contradicts the locked SPEC.

## Performance

- **Duration:** ~25 min total (Task 1 ~20min + Task 2 ~5min)
- **Completed:** 2026-08-02 — Tasks 1–2; **Task 3 checkpointed** (blocking operator UAT)
- **Tasks:** 2/3 tasks closed; Task 3 open by design (`type="checkpoint:human-verify"`)
- **Files modified:** 2 created (test suite + this SUMMARY), 1 modified (ADR-015)

## Accomplishments

- **Task 1: `tests/test_alerting_prohibitions.py` (9 tests, all green).** Structural
  guards for P1 (airgap — YAML-parsed compose ports + forbidden-egress tokens), P2
  (excerpt ≤500 + AST-scanned SQL constants + payload-equality across body-present/absent),
  P3 (scorer prompt sentinel — fails both if body leaks AND if title/summary dropped),
  P4 (zero egress for II/Routine/absent/null via the real emit path), P5 (alert-state
  column scan + single-health-handler AST check + no routing-framework imports), and AC8
  (complete 7-field payload with body NULL). Helpers `_published_ports` (YAML parse) and
  `_sql_string_constants` (AST parse, docstrings structurally excluded) make every check
  comment-proof.
- **Task 2: ADR-015 amendment.** New `## Amendment — superseded by 12-SPEC.md (Phase 12
  planning)` section records each superseded value with its shipped replacement: the
  7-field payload set (noting the intentional `pmseii_tags` spelling), the `|` dedupe
  separator, the 500-char excerpt cap, the `obsidian://open?vault=...` deep-link form
  with vault-relative path incl. the brief subdir, R3's two sliding throttle tiers + hourly
  digest, Open Items 2/3 resolutions, assumption A-01, and the body-excerpt field now being
  forbidden (P2) rather than merely deferred. Decision 3 and Decision 4 each carry an
  inline pointer to the amendment.
- **Verification:** `python -m pytest tests/test_alerting_prohibitions.py -x -q` → **9
  passed in 2.79s**. Full `make -f ops/Makefile test-safe` (throwaway Postgres) → **811
  passed, 0 failed, 0 skipped** — the 12-06 baseline's 801/0/1 plus this suite's 9 tests,
  0 regressions, and the previously-skipped `test_real_bearer_token_accepted` now passing
  (NTFY_TOKEN present in the ambient test-safe env this run).
- **`STATE.md`/`ROADMAP.md` updated** (this session): 12-09 marked in-progress/checkpointed
  at Task 3; **new backlog Phase 999.8** records the freshrss/rssbridge non-loopback
  exposure surfaced by the P1 guard (see Deviations 3) — the ADR-016 doctrine gap this plan
  deliberately did not auto-fix.

## Task Commits

Each task was committed atomically:

1. **Task 1: structural prohibition guards P1–P5 + AC8** — `test(12-09): prohibitions` (commit TBD)
2. **Task 2: ADR-015 amendment** — `docs(12-09): reconcile ADR-015 with locked SPEC` (commit TBD)
3. **Task 3: operator UAT** — OPEN, not committed; see below

**Plan metadata:** this SUMMARY + STATE.md/ROADMAP.md updates committed as
`docs(12-09): complete plan at Task 3 checkpoint — prohibitions guarded, ADR-015 reconciled`.

## Files Created/Modified

- `tests/test_alerting_prohibitions.py` — new; 9 tests; module docstring carries the
  full deviation record (this is the canonical place the deviations live until Task 3's
  approval seals the plan)
- `docs/adr/ADR-015-cnr-alerting-channels-and-payload.md` — amendment section +
  inline pointers in Decisions 3/4
- `docker-compose.yml` — **not modified, by decision** (see Deviations 3)
- `.planning/phases/12-cnr-alerting-dissemination/12-09-SUMMARY.md` — this file

## Decisions Made

- **Every guard is structural, never a raw-text grep.** A prohibition encoded as a grep
  that a source comment can both trip and satisfy is worse than absent; the plan's own
  key-link said so, and both helpers enforce it (YAML parse discards comments; AST walk
  excludes docstrings structurally).
- **Deviations from the plan's literal acceptance criteria are documented, not silently
  absorbed** — each one is a strengthening/correction of the guard, recorded in the test
  module docstring AND this summary's Deviations section so no future reader sees the
  plan text vs. the test text as a silent mismatch.

## Deviations from Plan

1. **P2b count is ZERO, not \"at least one\".** The plan's acceptance criterion asked for
   \"at least one\" SQL string constant under apps/alerting (and none referencing the body
   column). The true, correct count is **zero**: apps/alerting issues no raw SQL at all —
   every persistence call goes through the typed Store protocol (D-02). The test asserts
   the stronger, true count (zero), which is a strictly stronger guarantee than \"SQL
   exists but avoids the body column\". Weakening the docstring exclusion just to inflate
   the count to 1 would reintroduce the comment-satisfies-the-guard loophole.
2. **P3's second case asserts verbatim passthrough, not truncation.** The plan asked for a
   case asserting \"the summary is still passed through the existing truncation the scorer
   applies\". No such truncation exists in `triage_score.score_item` today (confirmed by
   inspection) — `summary` is interpolated into the prompt as-is. The shipped case asserts
   the weaker-but-meaningful property that a long summary passes through verbatim (the
   input contract has not silently widened).
3. **P1: freshrss (8088) and rssbridge (3000) genuinely bind all interfaces.** Two
   pre-existing, pre-ADR-016 (2026-07-23) services publish `8088:80` and `3000:80` without
   the loopback prefix — they predate the ADR-016 loopback convention every later service
   follows. The P1 guard names them in an explicit exception list and asserts loopback-only
   on every OTHER service (incl. every future one), so the doctrine still regresses loudly.
   Retightening their bindings would touch docker-compose.yml (outside this plan's
   files_modified) and is a real network-exposure behavior change an operator should
   decide — **flagged as backlog debt in Phase 999.8**, not silently fixed here.

## Issues Encountered

None beyond the three documented deviations above. No auto-fixable bugs surfaced during
either task.

## User Setup Required — **Task 3: Operator UAT (blocking)**

Nothing environmental. Two carried assumptions need your eyes; nothing automated can
settle them:

1. **Trigger a real CAT I alert.** `make -f ops/Makefile ntfy-up`, then
   `docker compose up -d --wait alerting`, confirm
   `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:22050/health` prints 200.
   Score or replay an item so a CAT I verdict publishes; confirm your ntfy client receives
   exactly one push, and NO second push when the day's SAB is next published for the same
   item.
2. **Assumption A2 — the vault parameter.** Tap the notification. Obsidian should open the
   item's own note. If it opens the wrong vault (or nothing), the vault display name in
   `INFOTRIAGE_OBSIDIAN_VAULT_NAME` doesn't match how Obsidian registered your vault — tell
   us the value that does work.
3. **Assumption A-01 — the two link fields.** As shipped, `deep_link` points at the item's
   note and `item_link` points at the SAB note. Confirm that is what you want, or say which
   target each should have.
4. **Digest formatting.** Force ≥6 CAT I alerts inside a minute (replay is fine), confirm
   only 5 push individually, then wait for the hourly tick (or restart with
   `INFOTRIAGE_ALERTING_DIGEST_INTERVAL=60`) and confirm one digest arrives titled with the
   suppressed count, grouped by PMESII tag, listing each suppressed item's title, link, and
   alert_id.
5. **P5 judgment — the SAB stays canonical.** SPEC's fifth prohibition is judgment-
   verified: does anything shipped read as a second, independent record of intel rather
   than a pointer back to the vault and the SAB? The push carries a capped excerpt and
   links, and no history surface was built.

**Resume signal:** type \"approved\" to seal the phase, or describe what to change for A2,
A-01, the digest wording, or P5.

## Next Phase Readiness

- **This plan is CHECKPOINTED at Task 3**, by design — Task 3 is a blocking human-verify
  gate. Tasks 1–2 (this plan's deliverable code/docs) are complete and committed; the phase
  seals on operator approval.
- **`STATE.md`/`ROADMAP.md` updated** to reflect 12-09 in-progress at Task 3 and the new
  backlog Phase 999.8 (freshrss/rssbridge non-loopback exposure). `REQUIREMENTS.md` NOT
  touched — `ADR-003` continues to be a design-doc reference cited across ~10 requirement
  rows rather than its own checkbox ID (the known `requirements.mark-complete` quirk).

## Self-Check: PASSED

- FOUND: tests/test_alerting_prohibitions.py (9 tests, green)
- FOUND: docs/adr/ADR-015 amendment section `## Amendment — superseded by 12-SPEC.md`
- FOUND: Decision 3 + Decision 4 inline pointers to the amendment
- OPEN: Task 3 operator UAT (blocking by design)

---
*Phase: 12-cnr-alerting-dissemination*
*Checkpointed: 2026-08-02 (Tasks 1–2 complete; Task 3 operator UAT open — phase seals on approval)*
