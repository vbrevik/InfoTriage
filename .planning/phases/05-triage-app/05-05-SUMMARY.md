---
phase: 05-triage-app
plan: 05
subsystem: shadow-run-parity-fever-cutover
tags: [parity-check, dedup, fever-retirement, R6, D-08, D-09]

requires:
  - phase: 05-04
    provides: infotriage-triage container (event-driven worker.py, /health, live-verified)
provides:
  - "scripts/shadow_run.py — reads infotriage.enrichment joined to infotriage.articles, re-runs score_item() standalone per non-dedup row, prints side-by-side bucket table + parity totals (D-08)"
  - "Parity gate MET: 14/14 genuinely-scored buckets matched (100%), 29 dedup short-circuits correctly excluded from the count (D-09)"
  - "Fever retired from the production scoring path: README documents the triage container as the scoring path; host crontab has no fever_triage.py entry (verified empty, R6)"
affects: []

tech-stack:
  added: []
  patterns:
    - "shadow_run.py excludes enrichment rows where why starts with 'duplicate of' from the parity comparison — dedup short-circuits (D-01) never call the LLM, so comparing them against a rescore that has no dedup awareness measures dedup logic, not scoring agreement"

key-files:
  created:
    - scripts/shadow_run.py
  modified:
    - README.md
    - docker-compose.yml

key-decisions:
  - "docker-compose.yml's LLM_BASE_URL must be hardcoded to http://host.docker.internal:8000/v1, not ${LLM_BASE_URL:-...} — Compose auto-loads the project .env for substitution, and .env's LLM_BASE_URL=http://127.0.0.1:8000/v1 (correct for host-side scripts like triage_score.py) silently overrode the container default, making every embed call fail with Connection refused."
  - "shadow_run.py must exclude dedup rows (bucket=skip, why='duplicate of <id>') from the parity count — including them as mismatches is a methodology bug, not a real scoring disagreement. Corrected count: 14/14 genuinely-scored rows matched, comfortably clearing the >=10 bar."
  - "Missing enrichment rows were populated by re-publishing item.ingested directly to infotriage.events (routing_key=item.ingested, headers={item_id}) for existing infotriage.articles rows via rabbitmqadmin — the documented workaround (persist_and_publish does not re-publish for already-existing items) rather than waiting on new ingest content."
  - "Host crontab fever entry: verified already absent (crontab -l -> 'no crontab for vidarbrevik'). No removal action was needed or taken; R6's cutover prohibition is satisfied by the current empty state."

requirements-completed: [R6]

coverage:
  - id: D1
    description: "scripts/shadow_run.py reads enrichment+articles, re-runs score_item(), prints side-by-side table with match column"
    requirement: "R6"
    verification:
      - kind: manual_procedural
        ref: "python3 scripts/shadow_run.py run against 43 live enrichment rows; table + totals printed correctly, dedup rows labeled DEDUP (excluded)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Parity = matching bucket (not exact score), >= 10 matching buckets required before cutover"
    requirement: "R6"
    verification:
      - kind: manual_procedural
        ref: "Parity verdict: MET (14 >= 10 matching buckets) printed by the corrected script"
        status: pass
    human_judgment: true
    rationale: "Operator explicitly instructed the crontab removal after reviewing the parity result presented in-session."
  - id: D3
    description: "After operator confirmation, fever_triage.py retired from production path (crontab + README)"
    requirement: "R6"
    verification:
      - kind: manual_procedural
        ref: "README.md already documents retirement (commit e846d94, prior session); crontab -l confirms no fever entry exists"
        status: pass
    human_judgment: true
    rationale: "Operator directed the crontab removal step; verification found the entry already absent."

duration: continuation session (Tasks 1-2 committed in prior session; Task 3 diagnosis, fixes, and closeout this session)
completed: 2026-07-02
status: complete
---

# Phase 5 Plan 05: Shadow-Run Parity + Fever Cutover Summary

**Fixed two real bugs blocking Task 3 (container env leak, parity script's dedup-blindness), got the parity gate to a legitimate MET (14/14), and confirmed the Fever crontab cutover was already in the target end-state.**

## Performance

- **Tasks:** 3 completed (Tasks 1-2 in a prior session; Task 3 diagnosed, fixed, and closed out this session)
- **Files modified:** 2 (docker-compose.yml, scripts/shadow_run.py)

## Accomplishments

- Redeployed the `infotriage-triage` container with the previously-committed `on_message` header fix (`89d6496`, landed but not yet deployed at session start) — confirmed via `docker exec` grep that the running image now reads `message.headers["item_id"]`.
- Found and fixed a second real bug: `docker-compose.yml`'s `LLM_BASE_URL: ${LLM_BASE_URL:-http://host.docker.internal:8000/v1}` was resolving to the host `.env`'s `LLM_BASE_URL=http://127.0.0.1:8000/v1` (meant for host-side scripts) via Compose's automatic `.env` substitution — every embed call inside the container hit `Connection refused` against its own loopback. Hardcoded the container-only URL.
- Got enrichment rows flowing: re-triggered ingest, then republished `item.ingested` directly (via `rabbitmqadmin publish` to `infotriage.events`, routing_key `item.ingested`, `item_id` in headers) for existing unenriched `infotriage.articles` rows — 43 enrichment rows total, 0 DLQ failures.
- Ran `scripts/shadow_run.py`: initial result showed 6/15 matching, apparently failing the R6 bar. Diagnosed the real cause — 9-29 of the enrichment rows across runs were dedup short-circuits (`bucket=skip`, `why="duplicate of <id>"`, no LLM call per D-01), which a naive rescore always disagrees with since it has no concept of "duplicate of X". Fixed `shadow_run.py` to exclude dedup rows from the parity count and report them separately.
- Corrected run: **14/14 genuinely-scored buckets matched (100%)** — parity verdict MET.
- Verified the crontab cutover: `crontab -l` returns "no crontab for vidarbrevik" — the fever entry is already absent. Nothing to remove; R6's end-state is already satisfied.

## Task Commits

1. **Task 1: Build scripts/shadow_run.py parity comparison tool (D-08)** - `49f1822` (feat, prior session)
2. **Task 2: Retire fever from the documented production path (README)** - `e846d94` (docs, prior session)
3. **Task 3: [BLOCKING] Shadow-run parity gate + Fever cutover (R6)** - `d9714fc` (fix: docker-compose LLM_BASE_URL), `f7430ef` (fix: shadow_run.py dedup exclusion) — operator confirmed parity MET and directed the crontab check; no crontab commit needed (entry was already absent). Closed out via this SUMMARY + tracking commit.

## Files Created/Modified

- `docker-compose.yml` - `LLM_BASE_URL` hardcoded to `http://host.docker.internal:8000/v1`, no longer reads the host `.env` value
- `scripts/shadow_run.py` - excludes dedup rows (`why` starts with `"duplicate of"`) from the parity comparison; reports `Total rows / Dedup (excluded) / Compared / Matching buckets` separately

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking issue] docker-compose.yml LLM_BASE_URL silently overridden by host .env**
- **Found during:** Task 3 (attempting to get the first enrichment row after redeploying the 05-03 on_message fix)
- **Issue:** `${LLM_BASE_URL:-http://host.docker.internal:8000/v1}` is resolved by Docker Compose using its own automatic `.env`-file substitution, independent of the `env_file:` directive already present in the triage service block. The project's `.env` (host-only, gitignored) sets `LLM_BASE_URL=http://127.0.0.1:8000/v1` for scripts run directly on the Mac (e.g. `triage_score.py`). That value leaked into the container's environment, where `127.0.0.1` refers to the container itself — every `get_embedding()` call failed with `Connection refused`.
- **Fix:** Hardcoded `LLM_BASE_URL: http://host.docker.internal:8000/v1` in `docker-compose.yml`, removing the `${...}` substitution entirely so the container-only value can never be shadowed by host config.
- **Files modified:** `docker-compose.yml`
- **Verification:** `docker exec infotriage-triage env | grep LLM_BASE_URL` -> `http://host.docker.internal:8000/v1`; subsequent `item.ingested` events processed with enrichment rows landing (no more `Connection refused` in `docker logs infotriage-triage`).
- **Committed in:** `d9714fc`

**2. [Rule 3 - Blocking issue] shadow_run.py counted dedup short-circuits as scoring mismatches**
- **Found during:** Task 3 (first parity run showed 6/15 — apparently failing the >=10 bar)
- **Issue:** The worker's dedup path (`find_near_duplicate` hit -> `bucket=skip`, `why="duplicate of <id>"`, score never computed, LLM never called — this is correct, intended behavior per D-01) was indistinguishable in `shadow_run.py`'s comparison from a real scoring disagreement. The standalone rescore has no dedup logic and independently re-scores every article, so it naturally disagrees with a dedup-skip's stored bucket. This made the parity number measure "how much of the corpus is near-duplicate" rather than "does the worker's LLM scoring agree with a fresh rescore" — the actual thing R6 needs confirmed.
- **Fix:** `shadow_run.py` now reads `e.why` and excludes any row where it starts with `"duplicate of"` from the parity comparison, printing it as `DEDUP (excluded)` and tallying it separately. The `>=10` bar now applies only to genuinely LLM-scored rows.
- **Files modified:** `scripts/shadow_run.py`
- **Verification:** Re-ran against the same 43 enrichment rows: `Total rows: 43  Dedup (excluded): 29  Compared: 14  Matching buckets: 14` — `Parity verdict: MET (14 >= 10 matching buckets)`.
- **Committed in:** `f7430ef`

---

**Total deviations:** 2 auto-fixed (both Rule 3 — blocking issues discovered while executing the Task 3 checkpoint, not scope creep). No architectural changes.

## Known Gaps

None. Both blockers carried over from the prior session's HANDOFF.json (uncommitted worker.py fix, unpopulated enrichment table) were resolved; the two new bugs found this session (env leak, dedup-blind parity script) were fixed and verified. `infotriage.dlq` is empty; `infotriage-triage` is healthy running the current image.

## Issues Encountered

- The prior session's `HANDOFF.json`/`.continue-here.md` (committed at `2c42d88`) described the `worker.py` fix as uncommitted, but git history showed it had already been committed (`89d6496`) seconds before that pause commit — a stale handoff snapshot. Resolved by verifying live state (git log, container image build time, `docker exec` grep) rather than trusting the handoff file at face value; the actual live gap (fix committed but not deployed) matched the file's substance even though the "uncommitted" framing was wrong.
- An earlier attempt to recover the original ~20 dead-lettered `item.ingested` messages via `rabbitmqadmin get ... ackmode=ack_requeue_false` consumed them without first saving the full payload (only a truncated preview was captured). No data was lost, since the underlying articles are safe in `infotriage.articles` — the documented workaround (republish `item.ingested` from existing article rows) was used instead, per the plan's own guidance for this exact scenario.

## User Setup Required

None. Host oMLX, RabbitMQ, and Postgres were already running and correctly configured; only the container-side Compose config needed a fix.

## Next Phase Readiness

- Phase 5 (Triage app) is now fully complete: all 5 plans (05-01 through 05-05) have commits and SUMMARY.md files.
- `infotriage-triage` is the live production scoring path; `fever_triage.py` is retired from production (file preserved for `digest.py`'s imports) and has no crontab entry.
- `docker-compose.yml`'s `LLM_BASE_URL` pattern (container-only, never falling back to host `.env`-scoped vars) should be the template for any future container that needs the host oMLX endpoint.

---
*Phase: 05-triage-app*
*Completed: 2026-07-02*

## Self-Check: PASSED

Both commit hashes (`d9714fc`, `f7430ef`) verified present in `git log`. `docker-compose.yml` and
`scripts/shadow_run.py` diffs match what this SUMMARY describes. Live re-verification this session:
`docker exec infotriage-triage env | grep LLM_BASE_URL` -> `http://host.docker.internal:8000/v1`;
`python3 scripts/shadow_run.py` -> `Parity verdict: MET (14 >= 10 matching buckets)`; `crontab -l` ->
`no crontab for vidarbrevik` (fever entry absent).
