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
  - `make -f ops/Makefile ntfy-acl-check` live operator smoke of the SPEC R6 matrix — confirmed PASS 3/3 against the operator's real persisted NTFY_TOKEN
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
  - "Task 3 (operator confirmation) closed by the continuation agent without ever reading or echoing the token value: verification ran ntfy-acl-check (which reads NTFY_TOKEN from the operator's real .env internally) and inspected only its PASS/FAIL stdout, plus a git-grep for the tk_ token-value pattern across tracked files. .env itself was never opened by any tool."

requirements-completed: [ADR-003]

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
    requirement: "ADR-003"
    verification:
      - kind: integration
        ref: "make -f ops/Makefile ntfy-acl-check, re-run by the continuation agent against the container the operator confirmed was rebuilt/up with their own persisted NTFY_TOKEN in .env: PASS: unauthenticated publish -> 403 / PASS: authenticated publish -> 200 / PASS: unauthenticated read -> 403"
        status: pass
      - kind: unit
        ref: "python -m pytest tests/test_alerting_auth.py -q -> 3 passed, 1 skipped (real-token case skips because NTFY_TOKEN is not exported into the ambient/test-safe shell env by design, not because auth failed)"
        status: pass
      - kind: manual
        ref: "git grep -nE 'tk_[A-Za-z0-9]{8,}' -- ops/ docs/ apps/ .env.example .planning/ -> no output (token value never landed in a tracked file); git status --short -> clean; git check-ignore -v .env -> matched by .gitignore:2:'.env*'"
        status: pass
    human_judgment: true
    rationale: "Operator confirmed via chat ('token pasted, now you continue') that they minted their own NTFY_TOKEN and placed it into their real gitignored .env. The continuation agent never read or echoed .env's contents (respecting the global tool-permission deny-rule on .env* paths) — it verified success only through ntfy-acl-check's PASS/FAIL stdout and a git-grep for the token-value pattern, which is the correct verification surface for a value that must never be read by automation."

patterns-established:
  - "Post-boot mint-and-print for any future server-generated credential ntfy or similar services require (tokens, API keys minted by the service itself rather than chosen by the operator)."
  - "Closing a human-action checkpoint for a secret value: verify via the tool's PASS/FAIL exit code and a negative grep for the value's shape, never by reading the secret file directly — even as the trusted continuation agent."

# Metrics
duration: 29min
completed: 2026-08-01
status: complete
---

# Phase 12 Plan 03: ntfy Bearer-Token ACL Summary

**Tightened ntfy's topic ACL from a wildcard grant to the SPEC R6 explicit per-topic matrix, shipped an idempotent post-boot bearer-token provisioning flow, and closed the operator-only checkpoint that placed the real token into the operator's `.env` — full matrix proven live end-to-end with 0 test regressions.**

## Performance

- **Duration:** 29 min total across 2 sessions (18:31–18:55 Tasks 1-2; Task 3 closeout ~5 min in this continuation)
- **Started:** 2026-08-01T16:31:00Z (approx.)
- **Completed:** 2026-08-01 (Task 3 closeout, this continuation)
- **Tasks:** 3 of 3 completed
- **Files modified:** 6 (2 modified in Task 1, 4 modified/created in Task 2; Task 3 modified no source files)

## Accomplishments

- Replaced `apps/ntfy/Dockerfile`'s 2 wildcard ACL grants with 4 explicit per-topic grants matching SPEC R6 exactly (producer read-write on the primary topic, write-only on `-debug`/`-test`; reader read-only on the primary topic only). Verified by a real `docker compose build ntfy` whose build log lists exactly the intended 4 grants.
- Recorded `.planning/phases/12-cnr-alerting-dissemination/COVERAGE.md`, the ntfy capability matrix for the phase (publish/auth/priority/tags/click-action integrated; attachment/delayed-delivery/email-forward/websocket/message-caching/icon-buttons opted out, each with a one-line SPEC/prohibition-anchored reason).
- Added `make -f ops/Makefile ntfy-token` — idempotent bearer-token mint-or-reveal against the running container (parses `tk_...` from `ntfy token list producer` / `ntfy token add producer` stdout), and `make -f ops/Makefile ntfy-acl-check` — a live curl-based proof of the full SPEC R6 matrix.
- Amended `docs/adr/ADR-018-phase-12-dockerfile-buildkit-secrets.md` with a new "Amendment — bearer token provisioning (Phase 12)" section explaining why the BuildKit-secret pre-bake path used for passwords doesn't apply to a server-generated token, and recording the resulting post-boot flow.
- Added `tests/test_alerting_auth.py` (4 pytest cases: unauthenticated publish denied, wrong-token publish denied, real-token publish accepted, unauthenticated read denied), module-skipped cleanly when ntfy is unreachable and skipping the real-token case individually when `NTFY_TOKEN` is unset.
- **Task 3 closed this continuation:** the operator confirmed they minted their own persistent `NTFY_TOKEN` and pasted it into their real gitignored `.env`. This agent re-ran `make -f ops/Makefile ntfy-acl-check` (3/3 PASS against the operator's real token), `python -m pytest tests/test_alerting_auth.py -q` (3 passed, 1 skipped — the skip is the ambient-shell-env design behavior, not an auth failure), a full `make -f ops/Makefile test-safe` (723 passed, 1 skipped — identical to the Task 2 baseline, 0 regressions), and confirmed via `git grep`/`git status`/`git check-ignore` that the token value never landed in any tracked file. At no point did this agent open, read, or echo `.env`'s contents.

## Task Commits

Each task was committed atomically:

1. **Task 1: Tighten the ntfy topic ACL and record the ntfy capability matrix** - `dfcc195` (feat)
2. **Task 2: Idempotent make ntfy-token target, ADR-018 amendment, and the live ACL test** - `195b8d2` (feat)
3. **Task 3: Operator mints the ntfy bearer token into .env and confirms the ACL** - operator action performed outside version control (writes to gitignored `.env` only, by design); this continuation agent's closeout is captured in this SUMMARY.md's final `docs(12-03): complete ...` commit.

Interim checkpoint artifacts from the prior session (`669c311` checkpoint SUMMARY, `8084dff` STATE.md update) are superseded by this final SUMMARY.

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
- Closed Task 3 without ever reading `.env`: verification relied exclusively on `ntfy-acl-check`'s PASS/FAIL stdout (which internally reads `NTFY_TOKEN` from `.env` on the operator's behalf), a `git grep` for the token-value shape across tracked files, and `git status`/`git check-ignore` to confirm `.env` stayed untracked. This is the correct verification surface for a secret an automation agent must never itself read.

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

None remaining. The operator completed the one required manual step this plan called for:

1. `make -f ops/Makefile ntfy-build` (rebuilt the image with the new ACL grants)
2. `make -f ops/Makefile ntfy-up`
3. `make -f ops/Makefile ntfy-token` — minted/revealed the token
4. Pasted it into the gitignored `.env` as `NTFY_TOKEN=<the tk_ value>`
5. Confirmed via chat: "token pasted, now you continue"

This continuation agent independently re-ran `make -f ops/Makefile ntfy-acl-check` (3/3 PASS) against the operator's real running container/token to confirm step 5 mechanically, without reading `.env` itself.

## Self-Check: PASSED

- `apps/ntfy/Dockerfile` — FOUND
- `ops/Makefile` — FOUND
- `docs/adr/ADR-018-phase-12-dockerfile-buildkit-secrets.md` — FOUND
- `tests/test_alerting_auth.py` — FOUND
- `.planning/phases/12-cnr-alerting-dissemination/COVERAGE.md` — FOUND
- Commit `dfcc195` — FOUND in git log
- Commit `195b8d2` — FOUND in git log
- `make -f ops/Makefile ntfy-acl-check` — PASS (3/3, re-run live this session)
- `python -m pytest tests/test_alerting_auth.py -q` — 3 passed, 1 skipped (exit 0)
- `make -f ops/Makefile test-safe` — 723 passed, 1 skipped, 0 failed (matches Task 2 baseline, 0 regressions)
- `git grep -nE 'tk_[A-Za-z0-9]{8,}' -- ops/ docs/ apps/ .env.example .planning/` — no output (clean)

## Next Phase Readiness

- All 3 tasks fully shipped, committed, and live-verified end-to-end, including the operator-only Task 3 checkpoint.
- `ADR-003` requirement marked complete.
- Plans 12-04 through 12-09 (dedupe/throttle wiring, digest, prohibition tests, final wiring) can now proceed with a fully live, real `NTFY_TOKEN` in the operator's environment — the emitter (`apps/alerting/outbox.py`) already sends the correct `Authorization: Bearer` header per the 12-01 tracer, and it is now proven to authenticate successfully against the real server.

---
*Phase: 12-cnr-alerting-dissemination*
*Completed: 2026-08-01*
