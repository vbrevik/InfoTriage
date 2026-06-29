---
phase: 5
slug: triage-app
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-06-29
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | pytest.ini / pyproject.toml |
| **Quick run command** | `pytest tests/ -x -q -k "triage or bus_consume"` |
| **Full suite command** | `pytest tests/ -v -k "triage or bus_consume"` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/ -x -q -k "triage or bus_consume"`
- **After every plan wave:** Run `pytest tests/ -v -k "triage or bus_consume"`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 05-01-01 | 01 | 1 | ADR-004 | — | DB migration idempotent | unit | `pytest tests/test_triage_enrichment.py -x -q` | ❌ W0 | ⬜ pending |
| 05-02-01 | 02 | 1 | ADR-004 | — | consume() persistent loop | unit | `pytest tests/test_bus_consume.py -x -q` | ❌ W0 | ⬜ pending |
| 05-03-01 | 03 | 2 | ccir.md | — | scoring produces verdict | integration | `pytest tests/test_triage_worker.py -x -q` | ❌ W0 | ⬜ pending |
| 05-04-01 | 04 | 3 | ADR-004 | — | health endpoint returns 200 | unit | `pytest tests/test_triage_health.py -x -q` | ❌ W0 | ⬜ pending |
| 05-05-01 | 05 | 4 | ADR-004 | — | shadow-run matches old path | integration | `pytest tests/test_triage_score_hotread.py -x -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_triage_enrichment.py` — Store extension + migration stubs
- [ ] `tests/test_bus_consume.py` — consume() loop stubs
- [ ] `tests/test_triage_worker.py` — worker process_item stubs
- [ ] `tests/test_triage_health.py` — health endpoint stubs
- [ ] `tests/test_triage_score_hotread.py` — ccir hot-read stubs

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Shadow-run matches Fever poll output end-to-end | ADR-004 | Requires live RabbitMQ + Postgres + qwen36 | Run worker against 20 items, run `scripts/shadow_run.py`, compare `verdict.ready` buckets |
| Fever poll removed cleanly (no dead code) | ADR-004 | Structural check | `grep -r "fever" services/ --include="*.py"` — only `fever_triage.py` (kept as import dep) acceptable |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 60s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
