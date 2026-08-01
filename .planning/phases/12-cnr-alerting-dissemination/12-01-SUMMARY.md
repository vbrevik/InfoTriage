---
phase: 12-cnr-alerting-dissemination
plan: 01
subsystem: infra
tags: [rabbitmq, ntfy, httpx, obsidian, docker-compose, alerting]

requires: []
provides:
  - "apps/alerting standalone service (worker, emitter, deep_link, outbox), containerized and wired into compose"
  - "q.alerting durable queue bound to verdict.ready via ROUTING_KEY_TO_QUEUE"
  - "7-field CAT I alert payload contract (SPEC R1) proven end-to-end against a stub ntfy server"
  - "obsidian:// deep-link path contract proven against apps/brief/vault_writer.py's actual output"
affects: [12-02, 12-03, 12-04, 12-05, 12-06, 12-09]

tech-stack:
  added: [httpx (already vetted, five sibling services)]
  patterns:
    - "Tracer-first vertical slice: one CAT I verdict -> one authenticated ntfy push, no batching/dedupe/throttle"
    - "HTTP presentation headers (X-Title, X-Tags, X-Click) built at the egress client from fields NOT in the locked JSON payload — keeps the 7-key SPEC contract stable while still carrying operator-facing metadata"
    - "Cross-module contract test: import the sibling module's real writer function and assert path equality, rather than asserting each module's derivation logic in isolation"

key-files:
  created:
    - apps/alerting/alerting_worker.py
    - apps/alerting/emitter.py
    - apps/alerting/deep_link.py
    - apps/alerting/outbox.py
    - apps/alerting/requirements.txt
    - apps/alerting/Dockerfile
    - tests/test_alerting_tracer.py
    - tests/test_alerting_deeplink.py
  modified:
    - libs/contracts/src/contracts/_bus_rabbitmq.py
    - docker-compose.yml

key-decisions:
  - "X-Title is an HTTP header set by NtfyClient.deliver(), not part of the 7-key JSON payload body — deliver() now takes item_title as a separate parameter rather than widening the SPEC R1-locked payload"
  - "Assumption A-01 confirmed as implemented: deep_link -> item's own vault note, item_link -> SAB note (per ADR-015 Decision 3), pending final operator confirmation at the 12-09 human-verify checkpoint"
  - "alerting compose service gets no vault volume mount — it only constructs obsidian:// URI strings, never writes files"

requirements-completed: [ADR-003]

coverage:
  - id: D1
    description: "A CAT I verdict.ready message produces exactly one authenticated POST carrying exactly the 7 SPEC-locked field names"
    requirement: "ADR-003"
    verification:
      - kind: unit
        ref: "tests/test_alerting_tracer.py#test_cat_i_produces_exactly_one_authenticated_post"
        status: pass
    human_judgment: false
  - id: D2
    description: "A non-CAT-I verdict (II, Routine) produces zero POSTs"
    requirement: "ADR-003"
    verification:
      - kind: unit
        ref: "tests/test_alerting_tracer.py#test_non_cat_i_produces_zero_posts"
        status: pass
    human_judgment: false
  - id: D3
    description: "The emitter refuses to start without a bearer token, non-zero exit, no connection opened first"
    requirement: "ADR-003"
    verification:
      - kind: unit
        ref: "tests/test_alerting_tracer.py#test_fail_closed_on_missing_ntfy_token"
        status: pass
    human_judgment: false
  - id: D4
    description: "The deep link's decoded vault-relative path equals the path apps/brief/vault_writer.py produces for the same item"
    requirement: "ADR-003"
    verification:
      - kind: unit
        ref: "tests/test_alerting_deeplink.py#test_item_note_link_matches_write_item_obsidian_output"
        status: pass
    human_judgment: false
  - id: D5
    description: "The alerting service builds and resolves in compose on a localhost-only 127.0.0.1:22050 port with postgres/rabbitmq/ntfy depends_on"
    requirement: "ADR-003"
    verification:
      - kind: other
        ref: "docker compose -f docker-compose.yml config --quiet (exit 0) + python3/yaml port + depends_on assertions"
        status: pass
    human_judgment: false
  - id: D6
    description: "X-Title header reflects the item title, not the sab_excerpt (operator-requested fix from the Task 1 checkpoint)"
    requirement: "ADR-003"
    verification:
      - kind: unit
        ref: "tests/test_alerting_tracer.py#test_cat_i_produces_exactly_one_authenticated_post (X-Title assertions)"
        status: pass
    human_judgment: false
  - id: D7
    description: ".env.example documented with NTFY_TOKEN/NTFY_URL/INFOTRIAGE_OBSIDIAN_VAULT_NAME/INFOTRIAGE_ALERT_NOTE_SUBDIR/INFOTRIAGE_ALERTING_HEALTH_PORT"
    verification: []
    human_judgment: true
    rationale: "Blocked by a global Claude Code permission deny rule (Read/.env.*) — could not be applied by the executor. Requires manual operator action; see Deviations."

duration: ~35min (across two sessions; this continuation ~15min for the X-Title fix + Tasks 2-3)
completed: 2026-08-01
status: complete
---

# Phase 12 Plan 01: CNR Alerting Tracer Summary

**Standalone `apps/alerting` service proving CAT I verdict.ready -> Store join -> 7-field payload -> authenticated ntfy Bearer POST -> obsidian:// deep link, end-to-end and containerized.**

## Performance

- **Duration:** ~35 min total (Task 1 in a prior session ending at a human-verify checkpoint; this continuation covered the operator-requested X-Title fix plus Tasks 2 and 3, ~15 min)
- **Completed:** 2026-08-01T16:16:48Z
- **Tasks:** 3/3 complete (plus 1 operator-requested fix between Task 1 and Task 2)
- **Files modified:** 9 (3 new production files' worth of edits across the session, 2 new test files, 1 new Dockerfile, docker-compose.yml, _bus_rabbitmq.py, .planning/STATE.md)

## Accomplishments

- Wired `q.alerting` into `ROUTING_KEY_TO_QUEUE['verdict.ready']` without touching the `sab.published` binding
- Built the emitter's exact 7-key SPEC R1 payload (`alert_id`, `sab_excerpt`, `dedupe_id`, `cnr_tier`, `item_link`, `pmseii_tags`, `deep_link`), sourced only from the enrichment `why`/`pmesii` and item `summary` fields, capped at 500 chars, never touching the article body column
- Built `NtfyClient.deliver()` — authenticated Bearer POST with ntfy presentation headers (`X-Title`, `X-Priority`, `X-Tags`, `X-Click`), never logging the token or Authorization header
- Built `deep_link.py`'s `obsidian://` URI construction, cross-verified against `apps/brief/vault_writer.py::write_item_obsidian`'s actual filename derivation and write path
- Cloned `apps/wiki/wiki_worker.py`'s shape into `alerting_worker.py`: three fail-closed startup guards (dsn, amqp-dsn, NTFY_TOKEN), health server, async consumer
- Fixed X-Title to derive from the item's own title (not `sab_excerpt`) per operator instruction at the Task 1 checkpoint, without widening the locked 7-key payload
- Containerized the service (`apps/alerting/Dockerfile`, cloned from `apps/wiki/Dockerfile`) and wired it into `docker-compose.yml` on a localhost-only `127.0.0.1:22050` port with `depends_on: postgres, rabbitmq, ntfy` (all healthy) and no vault mount

## Task Commits

Each task/fix was committed atomically:

1. **Task 1: Tracer — CAT I verdict.ready -> authenticated ntfy push** - `350a864` (feat) — completed in a prior session, ended at a human-verify checkpoint
2. **Operator fix: derive X-Title from item title, not sab_excerpt** - `20b19c8` (fix)
3. **Task 2: Lock the obsidian:// note path to the vault-writer's actual output** - `f1ab4de` (test)
4. **Task 3: Containerize apps/alerting and wire it into compose** - `a8de752` (feat)

_Note: Task 2 is `tdd="true"` but produced no additional GREEN commit — `deep_link.py`'s hardening was already correct from Task 1 (see Deviations); all 5 new tests passed on first run, investigated per the TDD fail-fast rule and confirmed as a valid cross-module contract, not a tautology._

## Files Created/Modified

- `libs/contracts/src/contracts/_bus_rabbitmq.py` - added `q.alerting` to the `verdict.ready` routing map entry
- `apps/alerting/alerting_worker.py` - CLI entrypoint, fail-closed startup, health server, consumer wiring
- `apps/alerting/emitter.py` - `build_alert_payload`, `handle_trigger`, `run_consumer`
- `apps/alerting/deep_link.py` - `obsidian_note_filename`, `obsidian_deep_link`, `item_note_link`, `sab_note_link`
- `apps/alerting/outbox.py` - `NtfyClient.deliver()`, now takes `item_title` as a separate param for `X-Title`
- `apps/alerting/requirements.txt` - mirrors `apps/wiki/requirements.txt` pin-for-pin + `httpx`
- `apps/alerting/Dockerfile` - cloned from `apps/wiki/Dockerfile`, non-root user, `EXPOSE 22050`
- `tests/test_alerting_tracer.py` - end-to-end tracer test against a stub ntfy server + fail-closed subprocess test
- `tests/test_alerting_deeplink.py` - cross-module contract test against `apps/brief/vault_writer.py::write_item_obsidian`
- `docker-compose.yml` - new `alerting` service block after `wiki`

## Decisions Made

- **X-Title source (operator-requested fix):** `X-Title` is an ntfy HTTP header set by `NtfyClient.deliver()`, not part of the 7-key JSON payload body (SPEC R1-locked). `deliver()` now accepts `item_title` as a separate parameter (single line, truncated to 80 chars) instead of deriving it from `sab_excerpt`'s first line, which would have conflated the excerpt (rationale text) with the item's own title.
- **Assumption A-01 held as implemented:** `deep_link` -> item's own vault note, `item_link` -> SAB note, per ADR-015 Decision 3. Still pending final operator confirmation at the 12-09 human-verify checkpoint per the plan's objective — not re-litigated here.
- **No compose volume mount for `alerting`:** the service only constructs `obsidian://` URI strings; it never writes files, so it gets no vault bind mount (matches the RESEARCH.md responsibility map).

## Deviations from Plan

### Auto-fixed Issues

**1. [Operator-directed fix, pre-Task-2] X-Title derived from item title instead of sab_excerpt**
- **Found during:** Checkpoint review after Task 1 (operator explicitly requested this fix before continuing)
- **Issue:** Task 1's tracer derived `X-Title` from `sab_excerpt`'s first line because the 7-key payload has no title field. This conflated the excerpt (rationale text) with the item's actual title, and the plan's Task 1 action text specified "derived from the item title."
- **Fix:** Widened `NtfyClient.deliver()` to accept `item_title` as a separate parameter used only for the `X-Title` header, without adding a field to the locked 7-key JSON payload. Updated the `emitter.py::handle_trigger` call site to pass `item.title` through. Added a test assertion (`X-Title == item.title`, `"rationale text" not in X-Title`).
- **Files modified:** `apps/alerting/outbox.py`, `apps/alerting/emitter.py`, `tests/test_alerting_tracer.py`
- **Verification:** `python -m pytest tests/test_alerting_tracer.py -x -q` — 6 passed
- **Committed in:** `20b19c8`

**2. [TDD fail-fast investigation, not a bug] Task 2 tests passed without further production-code changes**
- **Found during:** Task 2 (writing `tests/test_alerting_deeplink.py`)
- **Issue:** Per the TDD execution flow's fail-fast rule, a test passing unexpectedly during the RED phase requires investigation before proceeding.
- **Investigation:** `apps/alerting/deep_link.py`'s Task-1 implementation already read env at call time (not import time), already stripped leading/trailing subdir separators, and already percent-encoded with an empty safe set — because Task 1's `<read_first>` explicitly included `apps/brief/vault_writer.py` lines 78-100 to get the filename derivation right the first time. All 5 new cross-module contract tests passed on first run.
- **Conclusion:** This is the legitimate "feature may already exist" case the fail-fast rule calls out, not a weak/tautological test — the test compares two genuinely independent implementations (`deep_link.py`'s regex vs. `vault_writer.py`'s regex), so a future divergence between them would still be caught.
- **Files modified:** `tests/test_alerting_deeplink.py` only (no `deep_link.py` change needed)
- **Verification:** `python -m pytest tests/test_alerting_deeplink.py -x -q` — 5 passed
- **Committed in:** `f1ab4de`

**3. [Rule 3 - Blocking, could not auto-fix — environment permission, not a code bug] .env.example could not be updated**
- **Found during:** Task 2 (adding the new env keys to `.env.example`)
- **Issue:** This executor's global Claude Code permission settings (`~/.claude/settings.json`) contain a hard `deny` rule for `Read(.env.*)` (and by extension `Edit`/`Bash` content-aware access to the same path pattern). Read, Edit, and content-referencing Bash commands against `.env.example` are all blocked at the tool-permission layer, not by any project- or plan-level restriction.
- **Fix:** Not applied — this is a genuine tool-permission boundary, not a bug the executor can auto-fix under Rule 3 (package-install exclusion doesn't apply either; this isn't an install). Documented here instead of attempting to bypass an explicit `deny` rule via alternate tool paths, per the "no surprises" / boundary-conditions constraints.
- **Manual follow-up required** — add the following block to `.env.example`, adjacent to the existing `NTFY_BASE_URL` / `NTFY_TOPIC_PREFIX` lines (after the ACL-bootstrap comment block, before the `ACLED_LICENSE_KEY` section):
  ```
  # apps/alerting (Phase 12) — the bearer token minted by the ntfy-token
  # operator step (plan 12-03). The alerting service fails closed and refuses
  # to start when this is empty (SPEC R6).
  NTFY_TOKEN=
  # Compose-internal ntfy hostname:port used by apps/alerting; NTFY_BASE_URL
  # above stays the host-side value used by other clients/tooling.
  NTFY_URL=http://ntfy:80
  # Obsidian-registered vault display name (not a filesystem path).
  INFOTRIAGE_OBSIDIAN_VAULT_NAME=obsidian
  # Vault-relative note subdirectory the deep link points into — must track
  # the brief service's vault mount (${OBSIDIAN_VAULT_PATH}/brief-outbox).
  INFOTRIAGE_ALERT_NOTE_SUBDIR=brief-outbox
  INFOTRIAGE_ALERTING_HEALTH_PORT=22050
  ```
- **Files modified:** None (documented here only)
- **Verification:** N/A — cannot be verified until the operator applies the change
- **Committed in:** N/A

**4. [Informational only, no fix needed] Plan's literal port-check CLI snippet is stale against this docker compose v5 output schema**
- **Found during:** Task 3 verification
- **Issue:** The plan's acceptance-criteria one-liner (`assert all(str(x).startswith('127.0.0.1:') for x in p)`) assumes `docker compose config` emits ports as short strings. This installation runs Docker Compose v5.1.2, which emits the long-form dict schema (`{'host_ip': '127.0.0.1', ...}`) for every service in the file — confirmed identical behavior on the pre-existing `wiki` service, so this is a tooling-version mismatch affecting the whole file, not something introduced by this plan.
- **Fix:** None needed to the compose file itself. Verified the actual invariant (localhost-only binding) using the correct field for this schema (`entry['host_ip'] == '127.0.0.1'`), which passed.
- **Files modified:** None
- **Verification:** Corrected one-liner exits 0 with `host_ip == '127.0.0.1'` for the `alerting` service's port entry
- **Committed in:** N/A (verification-only finding)

---

**Total deviations:** 4 (1 operator-directed fix, 1 TDD fail-fast investigation with no code change needed, 1 blocked-by-environment-permission manual follow-up, 1 informational tooling-version note)
**Impact on plan:** All in scope. No architectural changes, no scope creep. The `.env.example` gap is the only item requiring operator action outside this executor's tool permissions.

## Issues Encountered

- Global Claude Code settings deny `Read`/`Edit`/content-aware `Bash` access to any `.env*` path (including `.env.example`, a template with no real secrets). Could not update `.env.example` per Task 2's action — see Deviations item 3 for the exact manual diff.

## User Setup Required

**Manual `.env.example` update required** — see "Deviations from Plan" item 3 above for the exact block to add. This does not block running the tracer test suite (which needs no env file), but does block a real `docker compose up` of the `alerting` service until `NTFY_TOKEN` is set in the operator's actual `.env`.

## Next Phase Readiness

- The tracer proves the two genuinely unproven architectural risks in this phase (authenticated ntfy egress, shared Obsidian note-path contract) before any expansion plan builds on top of it.
- Plan 12-02 (Postgres alert_state) and 12-03 (ntfy ACL + bearer token bootstrap) can now build on a proven emitter/outbox shape. Note: the current `ntfy` compose service uses `NTFY_AUTH_DEFAULT_ACCESS: deny-all` with Basic-Auth-only bcrypt credentials pre-baked per ADR-017/018 — plan 12-03 owns making the Bearer token this tracer already sends actually valid against the live ntfy server (RESEARCH.md Finding 3 / Pitfall 2).
- Assumption A-01 (`deep_link` vs `item_link` target) is implemented as specified but still awaits final operator confirmation at the 12-09 human-verify checkpoint.
- `.env.example` documentation gap (Deviations item 3) should be closed by the operator or a future plan with different tool permissions before this service is deployed for real.

---
*Phase: 12-cnr-alerting-dissemination*
*Completed: 2026-08-01*

## Self-Check: PASSED

All 8 created/modified artifact files found on disk; all 4 task/fix commit hashes (350a864, 20b19c8, f1ab4de, a8de752) found in git history.
