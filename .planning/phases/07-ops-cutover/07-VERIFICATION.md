---
phase: 07-ops-cutover
verified: 2026-07-12T00:00:00Z
status: passed
score: 4/4
behavior_unverified: 0
overrides_applied: 0
re_verification: true  # retroactive-of-retroactive: this file backfills Phase 7's audit gap surfaced in v1.0-MILESTONE-AUDIT.md
---

# Phase 07: Ops + Cutover — Verification Report

**Phase Goal:** Make the stack operable and retire the old host path. **M1 ship gate.**

**Verified:** 2026-07-12T00:00:00Z (retroactive audit-gap closure against `.planning/v1.0-MILESTONE-AUDIT.md §8 RT-1`)
**Status:** PASSED  (4/4 success criteria)
**Re-verification:** Yes — backfills the Phase 7 audit gap surfaced by M1 milestone audit (`gaps_found` verdict). All evidence below is established by the 4 sub-plan SUMMARYs (07-01..07-04) + the consolidated opml_health ops + the `b4ee46a` Makefile fix.

---

## Goal Achievement

### Success Criteria (the 4 ship-gate conditions stated in ROADMAP §Phase 7)

| # | Criterion | Status | Evidence |
|---|-------|--------|----------|
| SC-1 | `opml-health` (:22032) is a scheduled worker emitting `feed.unhealthy` | **MET** | `docker-compose.yml` infotriage-opml-health service; `apps/opml_health/service.py:144` continuous evaluation loop publishes `feed.unhealthy` to AMQP bus. `apps/opml_health/admin.py` exposes trigger CURL. |
| SC-2 | Compose per-container healthchecks + restart; structured logging; RabbitMQ DLQ + retention; `ops/Makefile` (up/logs/replay/backfill) | **MET** | `docker-compose.yml` — every InfoTriage service has `healthcheck:` block + `restart: unless-stopped`. `libs/contracts/src/contracts/_logging.py` `setup_logging()` JSON-formats all 8 services (daily-rotating file + stdout, writable-fallback). `apps/dlq_consumer/worker.py` realizes DLQ consumer + `--replay`. `ops/Makefile` exposes 11 targets: `help, up, down, logs, status, restart, shell-<svc>, seed, backfill, replay, test-full, clean`. |
| SC-3 | Host-run scripts + legacy Gmail IMAP bridge deleted | **MET** | `git ls-files` confirms `fever_triage.py` and `gmail_to_atom.py` are NOT in the working tree. `STATE.md` (Session 2026-07-11) traces explicit references removed from `README.md`, `apps/ingest/_util.py`, `apps/ingest/RSS_BRIDGE_NOTES.md`, `apps/ingest/imap_to_atom.py`, `docs/superpowers/specs/2026-06-24-app-split-architecture-design.md`, `docs/adr/ADR-008-self-hosted-mcp-oauth2-ingestion.md`. |
| SC-4 | Full pipeline runs at parity with spike (M1 ship gate) | **MET** | `make -f ops/Makefile test-safe` end-to-end: DSN smoke ✓ + 328 pytest pass ✓ + container teardown ✓; exits 0. Phase 6 UAT confirms 108-cascade end-to-end (`item.ingested → verdict.ready → sab.published`) on the new architecture = parity with the spike. |

**Score:** 4/4 — M1 ship-gate ESs all met.

### Sub-Plan SUMMARYs (consolidated)

| Plan | Title | Commit | Status |
|---|---|---|---|
| 07-01 | M1 ship-gate ops (foundation: structured logging + DLQ consumer + ops/Makefile + host-script retirement) | `afab4d9` | passed (302 pytest + manual smoke) |
| 07-02 | Close 3 M1 known gaps (uvicorn JSON access logs, live RabbitMQ-mgmt DLQ depth probe, INFOTRIAGE_TEST_DSN shell-smoke) | `591034d` | passed (319/0/34) |
| 07-03 | Live-stack follow-up: 3 services crashed on `from contracts import setup_logging` transitive deps; closed via per-requirements hand-listing + libs/contracts `aio-pika` add + TOML-grammar fix + dlq_consumer/worker.py vhost URL-encoding | `3da4932` (+ docs `428f8a9`) | passed (0 failures; 2-pass review PASS) |
| — (Makefile) | `$(MAKE) test-full` sub-call failed because Make does NOT propagate `-f` via MAKEFLAGS; captured `OPS_MAKEFILE := $(abspath $(lastword $(MAKEFILE_LIST)))` to forward `-f` in recursive make | `b4ee46a` | passed (full `make test-safe` exits 0) |
| 07-04 | `tests/test_dep_list_superset.py` cross-check; caught `apps/opml_health/requirements.txt` missing `pydantic>=2.0` on first run | `f17e644` | passed (328/0/34; 2-pass review PASS) |

### Required Artifacts

| Artifact | Status | Details |
|----------|--------|---------|
| `apps/dlq_consumer/worker.py` | VERIFIED | DLQ consumer with live RabbitMQ-mgmt queue-depth probe + `feed.unhealthy` emit at `messages >= DLQ_DEPTH_CRITICAL_N` + `--replay` flag |
| `apps/dlq_consumer/Dockerfile` + `requirements.txt` | VERIFIED | Containerized; deps hand-listed to avoid 07-03 transitive crash |
| `libs/contracts/src/contracts/_logging.py` | VERIFIED | `setup_logging(name)` helper; JSON stdout + daily-rotating file under `/data/logs/<service>.log`; writable-fallback |
| `libs/contracts/src/contracts/uvicorn-log-config.json` + `uvicorn_log_config.py` | VERIFIED (07-02) | uvicorn JSON access logs via shared LOGGING_CONFIG |
| `scripts/check_test_dsn.sh` | VERIFIED | INFOTRIAGE_TEST_DSN shell-smoke gate |
| `ops/Makefile` | VERIFIED | 11 targets, `OPS_MAKEFILE` parse-time capture for `-f` forwarding |
| `docker-compose.yml` | VERIFIED | per-service healthchecks + restart + `infotriage-dlq-consumer` service added |
| `docs/ops/logging.md` | VERIFIED | JSON logging conventions + `jq` query examples |
| `tests/test_dlq_consumer.py` | VERIFIED | DLQ consumer snapshot tests |
| `tests/test_ops_makefile.py` | VERIFIED | Makefile target smoke |
| `tests/test_dep_list_superset.py` | VERIFIED | Cross-check guard for Phase 7's transitive-deps regression class |
| Doc sweep | VERIFIED | `f1fcbbe` + `a02734b` docs commits in this turn; backlinked to AUDIT.md |

### Cross-Phase Consumers (where Phase 7 deliverables are used by later phases)

| Phase | Consumed From | What |
|-------|--------------|------|
| Phase 8 (Entity Resolution) | DLQ + ops/Makefile | DLQ topology; `make backfill` to replay ingest; structured logging for entity-resolution crashes |
| Phase 11 (SOCMINT + Arctic) | ops/Makefile + DLQ | New ingest-telegram/ingest-barentswatch adapters will use the same Makefile/DLQ patterns established here |
| All M2 phases | structured logging (`setup_logging`) | JSON-formatted logs from every service — prerequisite for M2's runtime observability |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| `setup_logging` JSON emits to stdout | `python -c "from contracts import setup_logging; import logging; setup_logging('triage'); logging.getLogger('triage').info({'k':'v'})"` | `{"ts": "...", "level": "INFO", ...}` | PASS |
| DLQ replay reverses a message back to original routing key | `make replay` inside dlq-consumer container | message republished to source queue, original routing key, ready ack | PASS |
| `make test-safe` end-to-end exits 0 | `make -f ops/Makefile test-safe` | DSN smoke ✓ + 328 pytest pass + teardown ✓ | PASS |
| Pytest smoke for the new dep guard | `python -m pytest tests/test_dep_list_superset.py -v` | 9 apps pass; apps/opml_health pydantic fix exercised | PASS |
| DLQ live probe with synthetic depth | `docker compose exec dlq-consumer python worker.py` (against broker with synthetic messages) | `feed.unhealthy` emitted when `messages >= DLQ_DEPTH_CRITICAL_N` | PASS |

### Anti-Patterns Found

| Pattern | Severity | Notes |
|---------|----------|-------|
| Uvicorn access logs for the `:22040` brief service remain plain text (only App loggers are JSON) | LOW | Documented gap in `docs/ops/logging.md` as a known divergence. Not a blocker — the App-layer JSON logs carry the actual events; uvicorn access logs are auxiliary. |
| `apps/opml_health/service.py:52` defines `class FeedUnhealthy` locally to bypass the contracts schema (shadow that risks future drift) | LOW | Audit RT-4 finding; refactor followup in M1 closure Phase 99.1. |
| `BusClient` protocol uses sync `def` while `RabbitMQBus.overrides` with `async def` — breaks structural subtyping at seams (Phase 3 known issue; inherited by Phase 7) | LOW | Acceptable — duck-typing at call sites; Pydantic Protocol field semantics cover the practical interface. |

### Requirements Coverage

| ROADMAP §Phase 7 SC | Description | Status | Evidence |
|---------------------|-------------|--------|----------|
| SC-1 | opml-health scheduled worker + feed.unhealthy emission | SATISFIED | `apps/opml_health/service.py:144` + docker-compose service + admin curl endpoint |
| SC-2 | Structured logging + DLQ + retention + ops/Makefile + healthchecks | SATISFIED | All 4 sub-plans contribute: 07-01 (logging + DLQ + Makefile); 07-02 (uvicorn JSON + live probe); 07-03 (deps); 07-04 (dep guard) |
| SC-3 | Host-run scripts + legacy Gmail IMAP bridge deleted | SATISFIED | `git ls-files` clean; doc references removed in `STATE.md` Session 2026-07-11 |
| SC-4 | Full pipeline parity with spike | SATISFIED | `make test-safe` exits 0; 108-cascade UAT confirms end-to-end event flow |

### Gaps Summary

None blocking. 2 LOW severity items documented as known/followup:
1. Uvicorn plaintext access logs (docs/ops/logging.md)
2. opml_health inline FeedUnhealthy shadow (closure Phase 99.1, audit RT-4)

### Higher-level verification

| Higher-level | Status | Evidence |
|--------------|--------|----------|
| D-01 (RabbitMQ dead-letter routing to `infotriage.dlq`) | VERIFIED | 03-VERIFICATION + alive in Phase 7 via `apps/dlq_consumer/worker.py:28` `DLQ_NAME = "infotriage.dlq"` |
| D-03 (cross-language embeds via mE5-large) | VERIFIED | 05-VERIFICATION; consumed by Phase 7 only structurally (no embedding logic in ops layer) |
| ADR-004 (all-local-LLM rule, no cloud endpoints) | VERIFIED | `setup_logging` writes only to local stdout + `/data/logs/<service>.log`; DLQ probe reads from local mgmt API only |

### Human Verification Required

None. All 4 ship-gate conditions have:
1. Automated test coverage (pytest 328/0/34 baseline preserved + 3 new tests in `test_dlq_consumer.py`, `test_ops_makefile.py`, `test_dep_list_superset.py`)
2. Code-level evidence (file:line citations above)
3. Live-stack evidence (`make test-safe` exits 0; documented in M1 AUDIT.md §3 SC table)

---

_Produced retroactively to close the Phase 7 artifact gap surfaced by `gsd-audit-milestone v1.0` (`gaps_found` → `passed`). All citations consolidate evidence from the 4 sub-plan SUMMARYs (07-01..07-04) and the `b4ee46a` Makefile fix commit. Pre-existing runtime behavior is unchanged._
