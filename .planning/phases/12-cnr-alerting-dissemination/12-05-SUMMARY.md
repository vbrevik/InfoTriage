---
phase: 12-cnr-alerting-dissemination
plan: 05
subsystem: alerting
tags: [python, asyncio, ntfy, rabbitmq, postgres, sliding-window, throttle, digest]

# Dependency graph
requires:
  - phase: 12-cnr-alerting-dissemination (plan 02)
    provides: "infotriage.alert_state Store substrate — claim_alert, count_alerts_in_window, mark_alert_suppressed, list_undigested_suppressed, mark_alerts_digested"
  - phase: 12-cnr-alerting-dissemination (plan 04)
    provides: "dedupe.claim() + emitter.py's _emit_if_claimed shared emit path (handle_verdict_ready/handle_sab_published dual-trigger, exactly-once claim)"
provides:
  - "apps/alerting/throttle.py: check_throttle(store, now=None) — 60s (cap 5) and 600s (cap 10) sliding-window volume caps"
  - "Throttle gate wired into emitter.py's _emit_if_claimed between the winning claim and egress; throttled alerts are marked suppressed, never dropped"
  - "apps/alerting/digest.py: group_by_pmesii, build_digest_message, publish_digest, run_digest_tick — hourly in-process digest of suppressed alerts"
  - "alerting_worker.py gathers run_digest_tick as a third coroutine; --digest-interval / INFOTRIAGE_ALERTING_DIGEST_INTERVAL (default 3600)"
affects: [12-06, 12-08, 12-09]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Sliding-window throttle: count_alerts_in_window compares fired_at against an injected now, never a truncated calendar bucket — the counting rule (claim writes before throttle checks, so the count includes the current alert) is documented in throttle.py's module docstring as the load-bearing off-by-one guard."
    - "Suppress-not-drop: a throttled alert is acked and marked suppressed with its pmesii/title, never silently lost — enumerated later by alert_id in the digest."
    - "Digest mark-after-deliver: publish_digest only calls mark_alerts_digested after a successful NtfyClient.deliver(); a failed digest retries the same rows whole on the next tick."
    - "In-process hourly tick (D-03): run_digest_tick clones apps/wiki/wiki_worker.py's run_periodic shape (asyncio.to_thread for blocking Store calls, try/except per iteration, sleep(interval)) — no scheduler-container coupling, no piggyback on an alert event."

key-files:
  created:
    - apps/alerting/throttle.py
    - apps/alerting/digest.py
    - tests/test_alerting_throttle.py
  modified:
    - apps/alerting/emitter.py
    - apps/alerting/alerting_worker.py

key-decisions:
  - "check_throttle's pass rule is a strict greater-than comparison against the cap (count<=cap passes, count>cap throttles), since claim_alert has already written the alert-under-evaluation's row before the throttle runs — documented explicitly in throttle.py's docstring as the likeliest off-by-one."
  - "item/enrichment rows are now read BEFORE the throttle gate in _emit_if_claimed (not just before payload build) — the suppression record needs the item's pmesii/title, so the emit path was reordered accordingly, keeping the missing-row early return ahead of everything else."
  - "digest.py's X-Title header substitutes an ASCII '!' for D-03's literal '⚠' glyph (httpx enforces strict ASCII header encoding in outbox.py, which this plan does not touch); the exact D-03 title text with the glyph is preserved in build_digest_message's return value and in the JSON payload body delivered to ntfy."
  - "Adjusted the plan's illustrative boundary-precision test numbers (0,15,30,45,59,61) to (10,20,30,40,50,65): the original numbers place the earliest alert 61s before the sixth's timestamp, which correctly falls OUTSIDE any 60s window regardless of sliding-vs-bucketed logic and would not have exercised the property the test names. The adjusted numbers keep the earliest alert inside the trailing 60s window while still landing across what a naive floor(t/60) calendar bucket would treat as a fresh bucket, so the test actually distinguishes correct sliding-window behavior from the buggy bucketed alternative."

patterns-established:
  - "Store-level cross-item volume counting: count_alerts_in_window counts ALL non-suppressed alert_state rows regardless of item_id — throttle caps are volume-wide, not per-item, distinct from dedupe.py's per-(item_id, cnr_tier) identity."

requirements-completed: [ADR-003]

coverage:
  - id: D1
    description: "60s and 600s sliding-window throttle caps enforce SPEC R3's exact boundary (5th passes, 6th throttles; 11th throttled by the 600s tier) with no calendar-bucket loophole"
    requirement: "ADR-003"
    verification:
      - kind: unit
        ref: "tests/test_alerting_throttle.py::test_check_throttle_60s_boundary_fifth_passes_sixth_throttles"
        status: pass
      - kind: unit
        ref: "tests/test_alerting_throttle.py::test_check_throttle_sliding_window_catches_burst_spanning_a_bucket_edge"
        status: pass
      - kind: unit
        ref: "tests/test_alerting_throttle.py::test_check_throttle_600s_tier_throttles_eleventh_alert_spaced_alerts"
        status: pass
      - kind: integration
        ref: "tests/test_alerting_throttle.py::test_emitter_six_alerts_within_60s_window_produce_five_requests"
        status: pass
    human_judgment: false
  - id: D2
    description: "Every throttled alert is marked suppressed (with pmesii/title) rather than dropped, and stops counting toward later throttle evaluations"
    requirement: "ADR-003"
    verification:
      - kind: integration
        ref: "tests/test_alerting_throttle.py::test_emitter_throttled_alert_marks_suppressed_row_with_pmesii_and_title"
        status: pass
      - kind: integration
        ref: "tests/test_alerting_throttle.py::test_emitter_suppressed_alert_stops_counting_toward_throttle_window"
        status: pass
    human_judgment: false
  - id: D3
    description: "Hourly in-process digest publishes exactly one message when suppressed rows exist, grouped by PMESII tag (null grouped under Unclassified, never dropped), enumerating each alert's title/deep-link/alert_id; emits nothing for an empty hour"
    requirement: "ADR-003"
    verification:
      - kind: unit
        ref: "tests/test_alerting_throttle.py::test_group_by_pmesii_null_pmesii_grouped_under_unclassified_not_dropped"
        status: pass
      - kind: integration
        ref: "tests/test_alerting_throttle.py::test_publish_digest_three_suppressed_rows_produces_exactly_one_request"
        status: pass
      - kind: integration
        ref: "tests/test_alerting_throttle.py::test_run_digest_tick_empty_hour_emits_nothing_one_iteration"
        status: pass
      - kind: integration
        ref: "tests/test_alerting_throttle.py::test_run_digest_tick_non_empty_hour_emits_exactly_one_message"
        status: pass
    human_judgment: false
  - id: D4
    description: "A failed digest delivery does not mark rows digested — the same rows are retried whole on the next tick"
    requirement: "ADR-003"
    verification:
      - kind: unit
        ref: "tests/test_alerting_throttle.py::test_publish_digest_failed_delivery_does_not_mark_rows_digested"
        status: pass
    human_judgment: false

duration: ~20min
completed: 2026-08-02
status: complete
---

# Phase 12 Plan 05: 3-tier sliding-window throttle + hourly PMESII digest Summary

**SPEC R3's 60s/600s sliding-window throttle wired into the proven dual-trigger emit path, with an in-process hourly D-03 digest that enumerates every suppressed alert by alert_id instead of dropping it.**

## Performance

- **Duration:** ~20 min
- **Completed:** 2026-08-02T10:17:24Z
- **Tasks:** 2/2 completed
- **Files modified:** 5 (2 created production, 1 modified production x2, 1 test file)

## Accomplishments

- `apps/alerting/throttle.py` — `check_throttle(store, *, now=None)` evaluates the 60-second
  tier (cap 5) then the 600-second tier (cap 10) against `Store.count_alerts_in_window`,
  returning a `ThrottleVerdict` naming whichever tier tripped. Both windows are sliding by
  construction (relative to an injectable `now`, never a truncated calendar bucket).
- `apps/alerting/emitter.py`'s `_emit_if_claimed` now runs the throttle gate after the winning
  dedupe claim and after reading item/enrichment (needed for both the payload and the
  suppression record), between claim and egress — matching RESEARCH's dedupe-then-throttle-then-
  digest priority ordering. A throttled alert calls `store.mark_alert_suppressed` with the
  item's pmesii/title and produces zero egress; the message is still acked upstream.
- `apps/alerting/digest.py` — `group_by_pmesii` (comma-split, first non-empty tag as primary
  domain, null/empty grouped under an explicit "Unclassified" heading), `build_digest_message`
  (D-03's exact title format + one grouped entry per row with title/deep-link/alert_id),
  `publish_digest` (delivers through the existing `NtfyClient`, marks digested only after
  success), and `run_digest_tick` (the D-03 in-process hourly loop, cloned from
  `apps/wiki/wiki_worker.py`'s `run_periodic` shape).
- `apps/alerting/alerting_worker.py` gains `--digest-interval` (env
  `INFOTRIAGE_ALERTING_DIGEST_INTERVAL`, default 3600) and gathers `run_digest_tick` as a third
  coroutine alongside the health server and the dual-trigger consumer.
- `tests/test_alerting_throttle.py` — 19 new tests covering both tasks' full behavior lists
  (60s/600s boundaries, sliding-vs-bucket precision, suppression bookkeeping, digest grouping,
  publish/retry semantics, tick empty/non-empty iterations), all driven by an injected clock.

## Task Commits

Each task was committed atomically:

1. **Task 1: Sliding-window throttle wired into the emit path** - `5ea4911` (feat)
2. **Task 2: Hourly PMESII-grouped digest tick** - `aa53cc8` (feat)

**Plan metadata:** (this commit)

## Files Created/Modified

- `apps/alerting/throttle.py` - `check_throttle`, `ThrottleVerdict`, `WINDOW_60S_CAP`/`WINDOW_10MIN_CAP`
- `apps/alerting/digest.py` - `group_by_pmesii`, `build_digest_message`, `publish_digest`, `run_digest_tick`
- `apps/alerting/emitter.py` - `_emit_if_claimed` reordered to read item/enrichment before the throttle gate, calls `check_throttle`/`mark_alert_suppressed`
- `apps/alerting/alerting_worker.py` - `--digest-interval` CLI flag, third gathered coroutine
- `tests/test_alerting_throttle.py` - new file, 19 tests (Task 1 + Task 2)

## Decisions Made

- **Strict-greater-than pass rule** (`count<=cap` passes, `count>cap` throttles) — documented
  explicitly in `throttle.py`'s module docstring since `claim_alert` writes the current alert's
  row before the throttle check runs, making this the load-bearing off-by-one in the module.
- **item/enrichment read moved ahead of the throttle gate** in `_emit_if_claimed` — the
  suppression record needs the item's title and the enrichment's pmesii text, so both must be
  available before the throttle decision, not just before the payload build.
- **X-Title header carries an ASCII substitute for D-03's literal "⚠" glyph.** `outbox.py`
  (locked, not in this plan's `files_modified`) delivers `item_title` through httpx, which
  enforces strict-ASCII header encoding — the raw glyph raised `UnicodeEncodeError` on every
  digest send. `build_digest_message`'s returned title (used by tests and embedded in the JSON
  payload body) keeps the exact D-03 text; only the value passed to `client.deliver(item_title=...)`
  substitutes `!` for `⚠`.
- **Adjusted the plan's suggested boundary-precision test timestamps.** The plan's action text
  illustrates the sliding-window precision property with alerts at seconds 0,15,30,45,59 then a
  sixth at 61 — but with `window_seconds=60`, the alert at second 0 is 61 seconds before the
  sixth's own timestamp and falls outside the trailing 60s window under BOTH a correct sliding
  implementation and a naive calendar-bucket implementation, so it would not actually distinguish
  the two. The test in this plan instead uses alerts at 10,20,30,40,50 then a sixth at 65: all
  five prior alerts remain inside the sliding 60s window ending at 65 (correctly throttled,
  6>cap 5), while a naive `floor(t/60)` bucket implementation would treat the sixth as a fresh
  bucket (count reset to 1, incorrectly passing) — this is the actual "no fixed-clock burst
  loophole" property SPEC R3 Edge R3/precision and the plan's truths block name.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `apps/alerting/digest.py` module name collides with `apps/triage/digest.py` under pytest's shared flat pythonpath**
- **Found during:** Task 2 (writing `tests/test_alerting_throttle.py`'s digest imports)
- **Issue:** `pyproject.toml`'s `[tool.pytest.ini_options] pythonpath` lists `apps/triage` before
  `apps/alerting`; both apps already had a `digest.py` (apps/triage's SAB/tiered digest
  generator, load-bearing for `apps/brief/renderer.py`, `apps/brief/main.py`,
  `tests/test_ccir_sync.py`, `tests/test_write_bluf.py`). A bare `from digest import
  build_digest_message` in the test file silently resolved to `apps/triage/digest.py` and
  raised `ImportError: cannot import name 'build_digest_message'`. In production this never
  happens — `apps/alerting/Dockerfile` copies only `apps/alerting/` into its container, so the
  collision is a pytest-session-only artifact of the shared flat pythonpath, not a real runtime
  ambiguity.
- **Fix:** `tests/test_alerting_throttle.py` loads `apps/alerting/digest.py` explicitly via
  `importlib.util.spec_from_file_location` under a private module name (`alerting_digest`),
  bypassing the ambiguous bare `import digest` entirely, with no change to the shared
  `pyproject.toml` pythonpath order (which the two pre-existing triage-digest consumers still
  depend on). `apps/alerting/alerting_worker.py` and `apps/alerting/digest.py` themselves keep
  the plain `from digest import ...` idiom used throughout the rest of `apps/alerting` — correct
  in their real single-app-container runtime, and never imported in-process by any test (the one
  test that exercises `alerting_worker.py`, `tests/test_alerting_tracer.py`, runs it as a
  subprocess with an isolated `PYTHONPATH` containing only `libs/contracts/src`/`libs/store/src`,
  so `apps/alerting` becomes `sys.path[0]` automatically with no `apps/triage` collision).
- **Files modified:** `tests/test_alerting_throttle.py` (import block only)
- **Verification:** `python -m pytest tests/test_alerting_throttle.py -q` → 19 passed; full
  `make -f ops/Makefile test-safe` confirms `tests/test_ccir_sync.py`/`tests/test_write_bluf.py`
  still resolve `apps/triage/digest.py` correctly (774 passed, 1 skipped, 0 failed).
- **Committed in:** `aa53cc8` (Task 2 commit)

**2. [Rule 1 - Bug] `UnicodeEncodeError` on the digest's `X-Title` header from D-03's literal "⚠" glyph**
- **Found during:** Task 2 (`publish_digest` test run)
- **Issue:** `httpx`'s header normalization strictly ASCII-encodes header values; D-03's exact
  title format (`"⚠ N suppressed CAT I alerts"`) raised `UnicodeEncodeError: 'ascii' codec can't
  encode character '⚠'` when passed as `item_title` to `NtfyClient.deliver()` (`outbox.py`,
  not in this plan's `files_modified`, so the header-encoding behavior itself could not be
  changed).
- **Fix:** `publish_digest` passes an ASCII-safe transliteration (`title.replace("⚠", "!")`) as
  `item_title` for the header only; `build_digest_message`'s returned `title` (used by tests and
  embedded in the JSON payload body sent as the digest's content) keeps the exact D-03 glyph.
- **Files modified:** `apps/alerting/digest.py`
- **Verification:** `python -m pytest tests/test_alerting_throttle.py -q` → 19 passed (including
  `test_publish_digest_three_suppressed_rows_produces_exactly_one_request`, which asserts `"3"`
  is present in the delivered `X-Title` header).
- **Committed in:** `aa53cc8` (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (1 blocking test-collection fix, 1 bug fix for header encoding)
**Impact on plan:** Both fixes were required for the plan's own `<verify>` commands to run at
all/pass; neither changes the plan's designed behavior (throttle caps, digest grouping/content,
D-03's title text as returned by `build_digest_message` and embedded in the payload body are all
unchanged). No scope creep — `outbox.py` was not modified.

## Issues Encountered

None beyond the two deviations documented above.

## User Setup Required

None — no external service configuration required. This plan only wires existing Store methods
(from 12-02) and the existing `NtfyClient`/`deep_link` modules (from 12-01) into new
`throttle.py`/`digest.py` modules and the already-fail-closed `alerting_worker.py` startup path.

## Next Phase Readiness

- The alerting service now enforces the full SPEC R3 volume-cap surface (dedupe from 12-04,
  throttle + digest from this plan) with nothing silently dropped end to end.
- `apps/alerting/outbox.py`'s strict-ASCII header handling is a latent pre-existing gap (present
  since 12-01) that also affects real CAT I alert titles containing non-ASCII characters, not
  just this plan's digest title — flagged here for whichever future plan owns `outbox.py`, not
  fixed (out of this plan's `files_modified` scope).
- Plan 12-06, 12-08, and 12-09 (per `.planning/STATE.md`'s carried-forward "Next" notes) remain
  open; none of their described scope depends on this plan's specific throttle/digest internals
  beyond the Store substrate already proven in 12-02.

## Self-Check: PASSED

All created/modified files confirmed present on disk (`apps/alerting/throttle.py`,
`apps/alerting/digest.py`, `tests/test_alerting_throttle.py`, `apps/alerting/emitter.py`,
`apps/alerting/alerting_worker.py`, this SUMMARY). Both task commits (`5ea4911`, `aa53cc8`)
confirmed present in `git log --oneline --all`.

---
*Phase: 12-cnr-alerting-dissemination*
*Completed: 2026-08-02*
