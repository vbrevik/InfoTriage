---
phase: 07-ops-cutover
plan: 07-01
status: complete (verified + reviewed; commits pending)
goal: M1 ship-gate ops — structured container logging, DLQ consumer, ops/Makefile, retire host scripts
verified: 2026-07-11
verified_by: full pytest 302 passed / 34 skipped / 0 failed; code-reviewer PASS
---

# 07-01-SUMMARY.md — M1 ship-gate ops (complete)

This plan rolls up the original Phase 7 07-02..07-04 (07-01 FreshRSS/rss-bridge
ops was already done in commit `316a20f`) plus a gap-closure pass after
self-review. The work landed in the working tree, all four tasks are green,
and the final review pass returned PASS with one resolved blocker.

## What shipped

### Task 1 — Retire host scripts (doc-only)

Per-session verification: `apps/triage/fever_triage.py` and
`apps/ingest/gmail_to_atom.py` were BOTH already absent from disk before this
plan's work began. `fever_to_atom.py` was retired in commit `66477b8` (Phase 4
close-out, chore(04-05)); `fever_triage.py` was retired alongside the Phase 5
Fever cutover (commit `1849f2a`, HANDOFF R6) — not preserved as STATE.md
previously believed (that note predated digest.py's import refactor).
This plan removed all stale doc references in:

- `README.md` — removed the `**Retired:**` paragraph that said "do not delete
  it"; the file is gone and the warning is no longer load-bearing.
- `apps/ingest/_util.py` — updated header comment from "three bridge entry
  points" to two (imap + yt).
- `apps/ingest/RSS_BRIDGE_NOTES.md` — replaced the three-path list with the
  current two-path list + a note that Gmail moved to the OAuth2/MCP path.
- `apps/ingest/imap_to_atom.py` — removed the Gmail filename-collision note.
- `docs/superpowers/specs/2026-06-24-app-split-architecture-design.md` —
  refreshed the "retired legacy Gmail IMAP bridge" line.
- `docs/adr/ADR-008-self-hosted-mcp-oauth2-ingestion.md` — same refresh.

### Task 2 — Structured container logging

- `libs/contracts/src/contracts/_logging.py` (NEW) — `setup_logging(name)`
  emits JSON to stdout + a daily-rotating file at
  `/data/logs/<service>.log` (overridable via `INFOTRIAGE_LOG_DIR`). Falls
  back to a temp dir (`/tmp/infotriage-logs`) when the host dir is not
  writable, with a printed warning to stderr. Uses `json_log_formatter` when
  installed, drops to a stdlib `_PlainJSONFormatter` fallback otherwise.
  Idempotent via a module-level `_LOGGING_CONFIGURED` guard so per-module
  import-time calls do not race/erase handlers.
- `libs/contracts/pyproject.toml` — declares `json-log-formatter>=1.1`. A new
  `# NOTE:` block documents the `--no-deps` propagation caveat (see
  Gap-closure below).
- `libs/contracts/src/contracts/__init__.py` — exports `setup_logging`.
- `libs/ingest_common/src/ingest_common/trigger.py` — invokes `setup_logging(name)`
  inside `make_trigger_app()` so every FastAPI adapter gets it for free.
- Wired into services (one call at module level):
  `apps/brief/main.py`, `apps/triage/worker.py`,
  `apps/scheduler/main.py`, `apps/scheduler/scheduler_main.py`,
  `apps/opml_health/service.py`, `apps/opml_health/admin.py`.
- `docker-compose.yml` — every InfoTriage container gets `LOG_LEVEL:
  ${LOG_LEVEL:-INFO}`. A top-of-file comment block documents that this is the
  intentional operator knob (host and container meanings agree; not the
  `LLM_BASE_URL`-style collision from HANDOFF).
- `docs/ops/logging.md` (NEW) — `jq` cookbook (filter by level, by service, by
  event type), env-var reference, docker-compose `jq` pipeline examples.

### Task 3 — ops/Makefile

`ops/Makefile` now exposes `help` (auto-extracted from `## ` doc-comment
trailers), `up`, `down`, `logs`, `status`, `restart`, `shell-<service>`,
`seed`, `backfill`, `replay`, `test-full`, `clean`. Compose invocation lives
under `ops/Makefile` (locator-relative) so `make` works from anywhere.

- `make status` probes every container's `/health` endpoint + `feeds`. New
  host port `127.0.0.1:22041:80` for the `feeds` (static Atom-file-server)
  container so it can be probed.
- `make replay` delegates to the new DLQ consumer's `--replay` mode (Task 4).
- `make backfill` POSTs `/run` on each ingest adapter and handles the 409
  already-running backstop (no false-fail).
- `make test-full` boots `docker-compose.test.yml`, waits for the throwaway
  pgvector Postgres on `:22062`, runs `pytest tests/ -q` with
  `INFOTRIAGE_TEST_DSN` set, then tears down.

### Task 4 — DLQ consumer

- `apps/dlq_consumer/` (NEW):
  - `worker.py` — consumes `infotriage.dlq`, logs each poison at ERROR,
    emits `feed.unhealthy` per message, and after 10 consecutive messages
    logs CRITICAL and resets the counter. `aio-pika.RobustConnection`
    wraps the consumer for `connect_robust` auto-reconnect. Replay mode
    (`python worker.py --replay`) reads `x-death` headers and republishes
    each message to the original exchange/routing-key (uses
    `idempotency_count=N` for tracked dedup at downstream).
  - `Dockerfile` — mirrors the other service Dockerfiles: contracts as
    `--no-deps`, then `pip install -r requirements.txt`, then source, then
    non-root `USER dlq-consumer`.
  - `requirements.txt` — `aio-pika>=9.6`, `json-log-formatter>=1.1`.
- `docker-compose.yml` adds the `dlq-consumer` service (no published port;
  AMQP-only; depends on `rabbitmq: service_healthy`).
- Tests:
  - `tests/test_dlq_consumer.py` — replays a poisoned message, validates
    extraction of `original_exchange` / `original_routing_key` from
    `x-death`, validates consecutive-error CRITICAL threshold.
  - `tests/test_ops_makefile.py` — confirms `make help` parses the doc
    comments, validates `make status`'s health-port mapping against the
    compose file.

## Gap-closure (post self-review)

After the broad reviewer pass identified THREE blockers + several advisories,
this summary lists the fixes actually applied during this session:

| ID | Issue | Resolution |
|----|-------|-----------|
| B1 | `${LOG_LEVEL:-INFO}` "anti-pattern" | Kept (intentional operator knob; new top-of-file comment in `docker-compose.yml` clearly distinguishes it from the HANDOFF-flagged `LLM_BASE_URL` collision case). |
| B2 | `README.md` removed the "do not delete" preservation warning for `fever_triage.py` despite it being live | Resolved by fresh grep evidence: `digest.py` has NO `fever_triage` references (the warning's premise was obsolete post-digest.py-import refactor). The file IS gone. The removal is correct. |
| B3 | Plan called for `docs/ARCHITECTURE.md`, `ccir.md`, `.env.example` cleanups that the diff didn't cover | `ARCHITECTURE.md` and `ccir.md` are already clean (no stale references). `.env.example` had `FRESHRSS_FEVER_*` orphan vars (no Python caller); dropped in this session with a 9-line comment block citing the Phase 5 cutover. |
| Adj | `json-log-formatter` declared in `libs/contracts/pyproject.toml` but only ONE of NINE service `requirements.txt` files re-declared it | Added `json-log-formatter>=1.1` to ALL 8 missing service `requirements.txt` files (per Dockerfiles' `--no-deps` install pattern, the dep cannot propagate transitively). Documented the versioning policy in `libs/contracts/pyproject.toml`. Kept `apps/opml_health/requirements.txt` line as it was (already correct). Removed the now-redundant `json-log-formatter` from `apps/ingest-gmail/Dockerfile`'s `pip install` line. |
| Adj | `apps/dlq_consumer/requirements.txt` had a redundant `contracts` line + misleading "kept for symmetry" rationale (no other service lists `contracts`) | Dropped the offending line; the final `apps/dlq_consumer/requirements.txt` matches the structural pattern of the other 7 service files (a single comment + two deps: `aio-pika` + `json-log-formatter`). |

## Deviations

- **Plan-vs-actual on retire host scripts:** the plan listed "DELETE
  `apps/triage/fever_triage.py` + DELETE `apps/ingest/gmail_to_atom.py`".
  Both files were already absent. The plan's literal intent (retire the host
  paths) is satisfied; the doc-reference cleanup is the only surviving work
  for this task. Plan text needs an amendment note (proposed for follow-up).
- **Plan-vs-actual on `apps/dlq_consumer/Dockerfile`:** the plan called for
  port `22033` for the consumer's health endpoint. The shipped service has
  no published port (AMQP-only, no HTTP server) — `make status` therefore
  shows "n/a" for it. This is intentional; the consumer's health is its
  AMQP-level connection state. If the operator wants an HTTP /health, it's
  a small follow-up edit (one route + port), outside M1 ship-gate scope.
- **DLQ depth:** the plan called for "after N consecutive errors, page the
  operator" with a queue-depth probe as one option. The shipped
  implementation uses the consecutive-msg threshold (documented in the
  worker docstring) rather than a live queue-depth probe (no
  RabbitMQ-mgmt-API integration in M1; tracked as future-work).

## Decisions recorded

- `json-log-formatter` is a contracts-runtime dep and CANNOT propagate via
  the `--no-deps` install pattern. **Each `apps/*/requirements.txt` MUST
  re-list `json-log-formatter>=1.1`.** Future services should copy the
  pattern from `apps/ingest-imap/requirements.txt`.
- The `${LOG_LEVEL:-INFO}` pattern across every InfoTriage container is the
  intentional operator knob. Unlike HANDOFF's `LLM_BASE_URL` collision
  (where host and container values mean different things), `LOG_LEVEL` has
  a consistent meaning in both contexts — Compose's auto `.env`
  substitution is therefore a feature, not a footgun. (See new
  `docker-compose.yml` top-of-file comment.)
- `setup_logging()` MUST be idempotent. The shipped implementation uses a
  module-level `_LOGGING_CONFIGURED` flag so that per-module import-time
  calls accumulate correctly even in tests that import multiple modules
  in sequence.
- DLQ "queue depth" in M1 is a consecutive-message threshold (10) at the
  CRITICAL log level — NOT a live RabbitMQ-management-API queue-depth
  probe. This is documented in the worker docstring.

## Tests / verification

- `pytest tests/ -q` → **302 passed, 34 skipped, 0 failed**. (Latest run:
  2026-07-11.)
- `tests/test_dsn_safety.py` passes — bare `pytest` is safe; db_live tests
  skip cleanly when `INFOTRIAGE_TEST_DSN` is not set.
- New tests added in this plan:
  - `tests/test_dlq_consumer.py` — replay correctness, consecutive-error
    threshold, x-death header extraction.
  - `tests/test_ops_makefile.py` — `make help` parses correctly, status-port
    mapping lines up with compose, idempotency smoke (`make up; make up`).
- `tests/baselines/triage_sample_baseline.txt` was previously untracked;
  this summary endorses adding it to the repo as a stable regression
  baseline for `apps/triage` digest output.

## Files in this plan

### New
- `apps/dlq_consumer/__init__.py`
- `apps/dlq_consumer/Dockerfile`
- `apps/dlq_consumer/requirements.txt`
- `apps/dlq_consumer/worker.py`
- `docs/ops/logging.md`
- `libs/contracts/src/contracts/_logging.py`
- `tests/test_brief_consumer.py` (residual from prior Phase 6 close-out;
  included in this PR to avoid leaving it uncommitted in the working tree)
- `tests/test_brief_main_views.py` (same)
- `tests/test_dlq_consumer.py`
- `tests/test_ops_makefile.py`
- `tests/baselines/triage_sample_baseline.txt`

### Modified
- `README.md` — drop `**Retired:**` fever_triage/gmail_to_atom paragraph.
- `apps/brief/main.py` — wire `setup_logging("brief")`.
- `apps/ingest/_util.py` — doc-only ref to 2 bridges.
- `apps/ingest/RSS_BRIDGE_NOTES.md` — Gmail → OAuth2/MCP routing.
- `apps/ingest/imap_to_atom.py` — drop Gmail filename-collision note.
- `apps/opml_health/admin.py` — wire `setup_logging("opml-health-admin")`.
- `apps/opml_health/service.py` — wire `setup_logging("opml-health")`.
- `apps/scheduler/main.py` — wire `setup_logging("scheduler")`.
- `apps/scheduler/scheduler_main.py` — wire `setup_logging("scheduler")`.
- `apps/triage/worker.py` — wire `setup_logging("triage")`.
- `docker-compose.yml` — `LOG_LEVEL` env, `dlq-consumer` service, `feeds`
  host port `127.0.0.1:22041`, top-of-file LOG_LEVEL policy comment.
- `docs/adr/ADR-008-self-hosted-mcp-oauth2-ingestion.md` — drop Gmail
  IMAP-path references.
- `docs/superpowers/specs/2026-06-24-app-split-architecture-design.md` —
  same.
- `libs/contracts/pyproject.toml` — `json-log-formatter` dep + the
  `# NOTE:` propagation-caveat doc.
- `libs/contracts/src/contracts/__init__.py` — export `setup_logging`.
- `libs/ingest_common/src/ingest_common/trigger.py` — wire
  `setup_logging(name)` in `make_trigger_app`.
- `ops/Makefile` — full operator-tool rewrite.
- `apps/ingest-gmail/Dockerfile` — drop redundant `json-log-formatter`
  pip-install (now in `requirements.txt`).
- `apps/ingest-gmail/requirements.txt` — add `json-log-formatter>=1.1`.
- `apps/ingest-imap/requirements.txt` — add `json-log-formatter>=1.1`.
- `apps/ingest-obsidian/requirements.txt` — add `json-log-formatter>=1.1`.
- `apps/ingest-youtube/requirements.txt` — add `json-log-formatter>=1.1`.
- `apps/scheduler/requirements.txt` — add `json-log-formatter>=1.1`.
- `apps/triage/requirements.txt` — add `json-log-formatter>=1.1`.
- `apps/brief/requirements.txt` — add `json-log-formatter>=1.1`.
- `apps/dlq_consumer/requirements.txt` — add `json-log-formatter>=1.1` +
  drop the redundant `contracts` line + its misleading comment.
- `.env.example` — drop `FRESHRSS_FEVER_*` vars, add the Phase 5-cutover
  explanation comment.

### Modified (planning files)
- `.planning/ROADMAP.md` — flip `07-01-PLAN.md` to `[x]` (already done in
  the working tree).
- `.planning/STATE.md` — close-out entry for this session.

## Excluded from commit (per USER-PROFILE anti-patterns)

- 17 untracked top-level debug scripts (`test_check.py`, `test_check2.py`,
  `test_cluster.py`, `test_cluster2.py`, `test_cluster3.py`,
  `test_debug.py`, `test_debug2.py`, `test_debug3.py`, `test_emb.py`,
  `test_final.py`, `test_items.py`, `test_semantic.py`,
  `test_similarity.py`, `test_similarity2.py`, `test_similarity3.py`,
  `test_verify.py`, `test_verify2.py`, `test_verify3.py`).
- `.env.bak-channels` and `.omo/run-continuation/ses_*.json` (secrets /
  session artifacts — never to be committed).

## Operator runbook

1. `docker compose up -d` (or `make up`) — bring up the stack.
2. `make status` — confirm all 8 services healthy.
3. `make logs | jq` — confirm JSON output parses.
4. `make seed` — populate the corpus for first-time run.
5. `make backfill` — re-run all 4 ingest adapters (idempotent).
6. If you see ERROR lines with `"original_exchange":"infotriage.events"`,
   that's DLQ traffic. `make replay` to drain.
7. If the alert page in `make logs | jq 'select(.level=="CRITICAL")'`
   matches `dlq-consumer`, the 10-consecutive threshold fired — drain
   with `make replay` to reset.

## M1 ship gate

After this plan lands and is committed, the M1 foundation milestone is
feature-complete:

- ✅ M1 Phases 0–7 all closed (Phase 0 spike, 1 contracts, 2 store, 3 bus,
  4 ingest, 5 triage, 6 brief, 7 ops).
- ✅ All 7 phase success criteria met per ROADMAP.md §M1 ship gate.
- ✅ Full pytest suite green (302 passed, 0 failed).
- ✅ DLQ bounded-depth policy in place.
- ✅ Logging structured + JSON-parseable for ops/dashboards.
- ✅ Operator toolset (`make help` is self-documenting).

The stack is at parity with the Phase 0 spike and ready to ship M1. M2 work
(Phases 8–12: Entity resolution, RAG recall, Wiki-LLM, SOCMINT + Arctic,
CNR alerting) is unblocked.
