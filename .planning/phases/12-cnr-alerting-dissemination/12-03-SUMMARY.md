---
phase: 12-cnr-alerting-dissemination
plan: 03
subsystem: infra
tags: [ntfy, docker, buildkit-secrets, bearer-token, acl, spec-r6]

# Dependency graph
requires:
  - phase: 12-cnr-alerting-dissemination (plan 01)
    provides: apps/alerting/outbox.py::NtfyClient sending Authorization Bearer + NTFY_TOKEN fail-closed startup guard
provides:
  - Explicit per-topic ntfy ACL (SPEC R6 matrix) replacing the prior wildcard grant, baked into apps/ntfy/Dockerfile
  - Idempotent `make -f ops/Makefile ntfy-token` bearer-token provisioning flow (post-boot, never image-baked)
  - `make -f ops/Makefile ntfy-acl-check` live operator smoke of the SPEC R6 matrix
  - tests/test_alerting_auth.py pytest coverage of the same matrix (skips cleanly when ntfy unreachable)
  - ADR-018 amendment documenting why bearer tokens can't ride the BuildKit-secret pre-bake path
  - COVERAGE.md ntfy capability matrix for the phase
affects: [12-04, 12-05, 12-06, 12-07, 12-08, 12-09]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Post-boot credential provisioning for server-generated values: mint via idempotent make target against the running container, print for manual .env placement, never bake into an image layer or write a tracked/gitignored file from automation."
    - "Reachability-probe skip marker for live-service pytest (mirrors tests/conftest.py::_test_db_reachable): module-wide pytestmark skipif on a 1s TCP connect, per-test skip for credential-dependent cases."

key-files:
  created:
    - tests/test_alerting_auth.py
    - .planning/phases/12-cnr-alerting-dissemination/COVERAGE.md
  modified:
    - apps/ntfy/Dockerfile
    - ops/Makefile
    - docs/adr/ADR-018-phase-12-dockerfile-buildkit-secrets.md
    - tests/test_ntfy_health.py

key-decisions:
  - "Amended the actual shipped ADR-018 file (docs/adr/ADR-018-phase-12-dockerfile-buildkit-secrets.md) rather than creating a new docs/adr/ADR-018-ntfy-dockerfile-prebake.md as the plan's files_modified listed — the ADR-018 filename in the plan didn't match what shipped in Plan 01/prior sessions; ADR numbers are not duplicated."
  - "ntfy-token mints/reveals by parsing `tk_[A-Za-z0-9]+` out of `ntfy token list producer` / `ntfy token add producer` stdout via docker exec, rather than attempting to write .env directly — the operator remains the only party who writes NTFY_TOKEN into their real .env (global permission deny-rule on .env* paths applies to this executor too, but the design intent independently requires operator-owned secret placement)."
  - "Retargeted the pre-existing '-smoke' topic smoke checks (ops/Makefile ntfy-publish-test, tests/test_ntfy_health.py) to the primary topic — the wildcard grant those checks depended on was removed by this plan's Task 1 ACL tightening, and SPEC R6 defines no '-smoke' topic."

requirements-completed: []  # ADR-003 requirement stays open — Task 3 (operator confirmation) is unresolved; see below

coverage:
  - id: D1
    description: "ntfy topic ACL tightened from 2 wildcard grants to 4 explicit per-topic grants matching SPEC R6 (producer rw primary / wo debug+test, reader ro primary only); ntfy capability matrix recorded in COVERAGE.md"
    requirement: "ADR-003"
    verification:
      - kind: integration
        ref: "docker compose -f docker-compose.yml build ntfy (exit 0, build log shows exactly the 4 intended grants)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Idempotent make ntfy-token target + make ntfy-acl-check live SPEC R6 matrix proof + tests/test_alerting_auth.py + ADR-018 amendment"
    requirement: "ADR-003"
    verification:
      - kind: integration
        ref: "make -f ops/Makefile ntfy-token (run twice — 2nd run confirmed idempotent, same tk_ value, no new token minted)"
        status: pass
      - kind: integration
        ref: "make -f ops/Makefile ntfy-acl-check (3/3 PASS: unauth publish 403, authed publish 200, unauth read 403)"
        status: pass
      - kind: unit
        ref: "tests/test_alerting_auth.py (4 passed with NTFY_TOKEN set, 3 passed + 1 skipped without)"
        status: pass
      - kind: unit
        ref: "tests/test_ntfy_health.py (6 passed after -smoke -> primary-topic retarget)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Operator mints their own persistent NTFY_TOKEN into their real gitignored .env and confirms ntfy-acl-check passes against it"
    verification: []
    human_judgment: true
    rationale: "ntfy generates the token value server-side; it cannot be chosen ahead of time or written into any tracked file by automation. This executor minted an ephemeral token during its own verification pass (never persisted to any file) — the operator must independently place their own token value into .env, which only they can do."

patterns-established:
  - "Post-boot mint-and-print for any future server-generated credential ntfy or similar services require (tokens, API keys minted by the service itself rather than chosen by the operator)."

# Metrics
duration: 24min
completed: 2026-08-01
status: checkpoint
---

# Phase 12 Plan 03: ntfy Bearer-Token ACL Summary

**Tightened ntfy's topic ACL from a wildcard grant to the SPEC R6 explicit per-topic matrix, and shipped an idempotent post-boot bearer-token provisioning flow — proven live end-to-end, paused at the operator-only checkpoint that puts the real token into the operator's own `.env`.**

## Performance

- **Duration:** 24 min (18:31–18:55, from first Dockerfile edit to Task 2 commit)
- **Started:** 2026-08-01T16:31:00Z (approx.)
- **Completed:** 2026-08-01T16:55:49Z (Task 2 commit; Task 3 checkpoint pending)
- **Tasks:** 2 of 3 completed (Task 3 is a blocking human-verify checkpoint)
- **Files modified:** 6 (2 modified in Task 1, 4 modified/created in Task 2)

## Accomplishments

- Replaced `apps/ntfy/Dockerfile`'s 2 wildcard ACL grants with 4 explicit per-topic grants matching SPEC R6 exactly (producer read-write on the primary topic, write-only on `-debug`/`-test`; reader read-only on the primary topic only). Verified by a real `docker compose build ntfy` whose build log lists exactly the intended 4 grants.
- Recorded `.planning/phases/12-cnr-alerting-dissemination/COVERAGE.md`, the ntfy capability matrix for the phase (publish/auth/priority/tags/click-action integrated; attachment/delayed-delivery/email-forward/websocket/message-caching/icon-buttons opted out, each with a one-line SPEC/prohibition-anchored reason).
- Added `make -f ops/Makefile ntfy-token` — idempotent bearer-token mint-or-reveal against the running container (parses `tk_...` from `ntfy token list producer` / `ntfy token add producer` stdout), and `make -f ops/Makefile ntfy-acl-check` — a live curl-based proof of the full SPEC R6 matrix.
- Amended `docs/adr/ADR-018-phase-12-dockerfile-buildkit-secrets.md` with a new "Amendment — bearer token provisioning (Phase 12)" section explaining why the BuildKit-secret pre-bake path used for passwords doesn't apply to a server-generated token, and recording the resulting post-boot flow.
- Added `tests/test_alerting_auth.py` (4 pytest cases: unauthenticated publish denied, wrong-token publish denied, real-token publish accepted, unauthenticated read denied), module-skipped cleanly when ntfy is unreachable and skipping the real-token case individually when `NTFY_TOKEN` is unset.
- **Live-verified the entire matrix end-to-end** against a rebuilt `infotriage-ntfy` container this session: minted a real token, confirmed idempotency (2nd `ntfy-token` run returned the identical value with no new mint), ran the curl matrix directly and via `ntfy-acl-check` (3/3 PASS), and ran the pytest suite both with and without `NTFY_TOKEN` set.

## Task Commits

Each task was committed atomically:

1. **Task 1: Tighten the ntfy topic ACL and record the ntfy capability matrix** - `dfcc195` (feat)
2. **Task 2: Idempotent make ntfy-token target, ADR-018 amendment, and the live ACL test** - `195b8d2` (feat)

**Task 3** (checkpoint:human-verify, `gate="blocking"`) is **not yet resolved** — see "Deviations from Plan" / checkpoint details below. No plan-metadata commit will be created until Task 3 completes; that final `docs(12-03): complete ...` commit is deferred to the continuation agent.

## Files Created/Modified

- `apps/ntfy/Dockerfile` - 2 wildcard `ntfy access` grants replaced with 4 explicit per-topic grants (SPEC R6 matrix); header comment documents the matrix and the reason no `ntfy token add` call lives here.
- `.planning/phases/12-cnr-alerting-dissemination/COVERAGE.md` - new ntfy capability matrix (INTEGRATE/OPT-OUT per capability) + ACL matrix table.
- `ops/Makefile` - new `ntfy-token` and `ntfy-acl-check` targets (registered in `.PHONY`); `ntfy-publish-test` retargeted from the now-ungranted `-smoke` topic to the primary topic.
- `docs/adr/ADR-018-phase-12-dockerfile-buildkit-secrets.md` - new "Amendment — bearer token provisioning (Phase 12)" section.
- `tests/test_alerting_auth.py` - new: 4 pytest cases proving the SPEC R6 ACL matrix live.
- `tests/test_ntfy_health.py` - `NTFY_TOPIC` retargeted from the ungranted `-smoke` suffix to the primary topic (Rule 1 fix; see Deviations).

## Decisions Made

- Amended the pre-existing `docs/adr/ADR-018-phase-12-dockerfile-buildkit-secrets.md` in place rather than creating a differently-named file, since the plan's `files_modified` path (`docs/adr/ADR-018-ntfy-dockerfile-prebake.md`) doesn't match what actually shipped for ADR-018 in prior sessions.
- `ntfy-token`'s idempotency check parses stdout for a `tk_[A-Za-z0-9]+` token rather than tracking any local state file — this correctly reflects the source of truth (the server's own auth.db) and requires no bookkeeping on the host.
- Left `NTFY_AUTH_DEFAULT_ACCESS=deny-all` and the serve-then-kill auth.db bootstrap in `apps/ntfy/Dockerfile` completely untouched, per the plan's explicit instruction — those remain load-bearing from ADR-018.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug, in-scope regression] Retargeted the `-smoke` topic checks that this plan's own ACL change orphaned**
- **Found during:** Task 2 verification (running `ntfy-acl-check`/pytest against the rebuilt image)
- **Issue:** The pre-Plan-03 wildcard grant (`"<prefix>*"`) covered an ad hoc `-smoke` topic used by `ops/Makefile`'s `ntfy-publish-test` target and `tests/test_ntfy_health.py`. Task 1's SPEC R6 explicit-grant replacement covers exactly 3 topics (primary, `-debug`, `-test`) and no `-smoke` topic, so both pre-existing smoke checks would silently start failing (deny-all, no grant) the moment the new image shipped — a regression directly caused by this plan's own Task 1 change.
- **Fix:** Retargeted both `ops/Makefile`'s `ntfy-publish-test` and `tests/test_ntfy_health.py`'s `NTFY_TOPIC` constant from `"<prefix>-smoke"` to `"<prefix>"` (the primary topic) — which is exactly the topic + identity pair those checks were always meant to exercise (producer write success / reader write denial).
- **Files modified:** `ops/Makefile`, `tests/test_ntfy_health.py`
- **Verification:** `python -m pytest tests/test_ntfy_health.py -q` → 6 passed against the rebuilt image.
- **Committed in:** `195b8d2` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 in-scope regression fix)
**Impact on plan:** Necessary to prevent a self-inflicted regression from Task 1's ACL tightening; no scope creep — both files were already in the plan's Task 2 blast radius (Makefile explicitly, and the sibling ntfy health-check test file shares the same topic-naming assumption this plan's Task 1 invalidated).

## Issues Encountered

None beyond the deviation above. `mypy --strict tests/test_alerting_auth.py` initially flagged 2 `no-any-return` errors on `resp.status`/`exc.code` (typeshed types `urllib.request.urlopen`'s return loosely) — fixed with explicit `int(...)` casts, then `black` reformatted the file; both re-verified clean.

## User Setup Required

**External service requires manual configuration — this plan's Task 3 checkpoint.** ntfy's bearer token is generated by the server, not chosen by the operator, so it cannot be pre-baked or written into any tracked file by automation (RESEARCH.md Pitfall 2 / Open Question 1). Per the plan's `user_setup` frontmatter:

1. `make -f ops/Makefile ntfy-build` (rebuilds the image with the new ACL grants — already done this session, image is current)
2. `make -f ops/Makefile ntfy-up` (already done this session — `infotriage-ntfy` is healthy on the new image)
3. `make -f ops/Makefile ntfy-token` — copy the printed token (this session already minted one: idempotent, so re-running now will reveal the same value rather than minting a new one)
4. Paste it into the gitignored `.env` as `NTFY_TOKEN=<the tk_ value>` (add the key if plan 12-01's `.env.example` addition — see `12-01-SUMMARY.md` Deviations item 3 — hasn't been mirrored into your `.env` yet)
5. `make -f ops/Makefile ntfy-acl-check` — expect PASS on all three cases
6. Confirm `git status` shows no modification to `.env` tracking and that the token appears in no tracked file

This executor already proved every one of the above mechanically works (steps 1–3 run this session; step 5's curl matrix proven both directly and via `ntfy-acl-check` with the token supplied as an environment variable) — the remaining gap is purely that only the operator can place the value into their own persistent `.env`.

## Next Phase Readiness

- Tasks 1 and 2 are fully shipped, committed, and live-verified. `make -f ops/Makefile test-safe` after both commits: **723 passed, 1 skipped** (baseline 720 → 724 total, +4 new tests from `tests/test_alerting_auth.py`, 0 regressions; the 1 skip is `test_real_bearer_token_accepted` since `NTFY_TOKEN` isn't exported in the ambient test-safe environment).
- **Blocked on Task 3** (operator confirmation) before this plan can be marked complete. `ADR-003` requirement completion, `STATE.md` plan-advance, and `ROADMAP.md` plan-progress update are deferred to the continuation agent that resumes after the operator approves the checkpoint.
- Plans 12-04 through 12-09 (dedupe/throttle wiring, digest, prohibition tests, final wiring) are unaffected by this plan's remaining Task 3 and can proceed once the operator's `NTFY_TOKEN` is live — the emitter (`apps/alerting/outbox.py`) already sends the correct `Authorization: Bearer` header per the 12-01 tracer.

---
*Phase: 12-cnr-alerting-dissemination*
*Completed: 2026-08-01 (Tasks 1-2; Task 3 checkpoint pending operator action)*
