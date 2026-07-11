---
phase: 7
slug: ops-cutover
status: verified
nyquist_compliant: true
wave_0_complete: true
created: 2026-07-12
retroactive: true   # backfill for M1 audit gap (v1.0-MILESTONE-AUDIT.md RT-2)
---

# Phase 07 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution. This file was retroactively created during M1 closure Phase 99.1 to close the audit gap surfaced in `.planning/v1.0-MILESTONE-AUDIT.md` §6 — Phase 7 was the M1 ship-gate enforcer and was missing both a top-level `07-VERIFICATION.md` and this `07-VALIDATION.md`.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.3.3 |
| **Config file** | `pyproject.toml` (root) |
| **Quick run command** | `pytest tests/ -q -k "dlq_consumer or ops_makefile or dep_list_superset or logging"` |
| **Ops suite** | `pytest tests/test_dlq_consumer.py tests/test_ops_makefile.py tests/test_dep_list_superset.py -q` |
| **Cross-cutting** | `make -f ops/Makefile test-safe` (DSN smoke + pytest in container + teardown) |
| **Estimated runtime** | ~5 seconds (ops suite); ~120s (test-safe end-to-end with container) |

## Sampling Rate

- **After every task commit:** Run `pytest tests/ -q -k "dlq_consumer or dep_list_superset"`
- **After every plan wave:** Run `make -f ops/Makefile test-safe`
- **Before `/gsd-verify-work`:** `make -f ops/Makefile test-safe` exit 0 required
- **Max feedback latency:** ~5 seconds (pytest), ~120 seconds (test-safe)

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 07-01-01 | 01 | 1 | SC-1.opml-health scheduled worker | T-07-OPML | opml-health emits `feed.unhealthy` for stale feeds, Bounded depth alert | unit + integration | `pytest tests/test_opml_health.py -q` | ✅ | ✅ green |
| 07-01-02 | 01 | 1 | SC-2.structured logging | T-07-LOG | `setup_logging(name)` JSON-format all containers; `LOG_LEVEL` env honored | unit | `pytest tests/test_contracts.py -k "setup_logging or logging" -q` | ✅ | ✅ green |
| 07-01-03 | 01 | 1 | SC-2.ops/Makefile | — | `make help/up/down/logs/status/restart/replay/backfill/test-full` exit 0 | smoke | `tests/test_ops_makefile.py` | ✅ | ✅ green |
| 07-01-04 | 01 | 1 | SC-3.retire host scripts | T-07-CLEAN | `fever_triage.py` and `gmail_to_atom.py` are not in working tree | structural | `git ls-files \| grep -E 'fever_triage\|gmail_to_atom'` (negative) | ✅ | ✅ green |
| 07-02-01 | 02 | 2 | SC-2.uvicorn JSON access logs | T-07-UVI | `LOGGING_CONFIG` shared; uvicorn emits JSON | unit | `pytest tests/test_uvicorn_log_config.py -q` | ✅ | ✅ green |
| 07-02-02 | 02 | 2 | SC-2.live DLQ depth probe | T-07-DLQ-PROBE | periodic GET on `/api/queues/...`; `feed.unhealthy` on `messages >= DLQ_DEPTH_CRITICAL_N` | integration | `pytest tests/test_dlq_consumer.py::test_depth_probe_alert -q` | ✅ | ✅ green |
| 07-02-03 | 02 | 2 | SC-2.dsn smoke gate | T-07-DSN | `scripts/check_test_dsn.sh` rejects prod fallback | smoke | `make -f ops/Makefile test-safe` calls it | ✅ | ✅ green |
| 07-03-01 | 03 | 3 | (post-07-02 transitive-deps regression) | T-07-DEPS | every app's `requirements.txt` re-lists contracts deps | structural | `pytest tests/test_dep_list_superset.py -q` | ✅ | ✅ green |
| 07-03-02 | 03 | 3 | dlq-consumer vhost URL-encoding | T-07-VHOST | `apps/dlq_consumer/worker.py` mgmt URL uses `%2F` for vhost (not `///`) | structural | `pytest tests/test_dlq_consumer.py::test_vhost_url_encoding -q` | ✅ | ✅ green |
| 07-04-01 | 04 | 4 | dep-list-superset regression guard | — | pys/hard: every transitive contracts dep must be in every consumer `requirements.txt` | unit | `pytest tests/test_dep_list_superset.py -v` (param: 9 apps) | ✅ | ✅ green |
| 07-MAKE-01 | (b4ee46a) | post-07-03 | recursive make `-f` forwarding | T-07-MAKE | `OPS_MAKEFILE` parse-time capture; `make test-safe` sub-make forwards `-f` | integration | `make -f ops/Makefile test-safe` exit 0 | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

## Wave 0 Requirements

- [x] `tests/test_dlq_consumer.py` — DLQ consumer + replay + depth probe + vhost URL
- [x] `tests/test_ops_makefile.py` — Makefile target smoke
- [x] `tests/test_dep_list_superset.py` — Phase 7 transitive-deps regression guard
- [x] `scripts/check_test_dsn.sh` — DSN safety gate
- [x] `libs/contracts/src/contracts/_logging.py` — `setup_logging(name)` JSON helper
- [x] `libs/contracts/src/contracts/uvicorn-log-config.json` + `uvicorn_log_config.py` — uvicorn JSON access logs (07-02)
- [x] `ops/Makefile` — 11 targets (help/up/down/logs/status/restart/shell-<svc>/seed/backfill/replay/test-full/clean)

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Result |
|----------|-------------|------------|--------|
| `make -f ops/Makefile test-safe` end-to-end (DSN smoke + 328-pass pytest in container + teardown) | SC-4 parity | Cross-cutting; cross-app pytest in ephemeral test Postgres | ✅ DONE — exit 0; 328/0/34 |
| Stop+start RabbitMQ container mid-session to verify `connect_robust()` auto-reconnect (inherited from Phase 03) | SC-2 DLQ continuity | Requires TCP drop simulation; no safe pytest harness | ✅ DONE per Phase 3 — see `03-VALIDATION.md` row |
| 108-cascade end-to-end (Phase 6 UAT) covers SC-4 parity | SC-4 parity | Requires live RabbitMQ + Postgres + qwen36 | ✅ DONE — see Phase 6 UAT |
| Live DLQ depth probe with synthetic messages (`DLQ_DEPTH_CRITICAL_N = 10` triggered in test) | SC-2 live probe | Requires real RabbitMQ | LIVE — see `apps/dlq_consumer/worker.py` |

## Validation Audit 2026-07-12 (retroactive)

| Metric | Count |
|--------|-------|
| Gaps found | 0 |
| Resolved (automated) | 10 (mapping the 4 sub-plan SUMMARYs + b4ee46a to existing test files + new test_dep_list_superset.py) |
| Manual-only | 4 |
| Escalated | 0 |

**Note:** Phase 7 was executed incrementally across 4 sub-plans (07-01, 07-02, 07-03, 07-04) using Nyquist-aligned testing throughout. This retroactive VALIDATION.md backfills the contract documentation for M1 audit triangulation. No behavioral gap exists; only documentation gap.

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or documented manual-only rationale
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (no missing infra)
- [x] No watch-mode flags
- [x] Feedback latency < 5s (pytest), < 120s (test-safe)
- [x] `nyquist_compliant: true` set in frontmatter
- [x] `wave_0_complete: true` set in frontmatter

**Approval:** retroactively approved 2026-07-12 (M1 closure Phase 99.1)
