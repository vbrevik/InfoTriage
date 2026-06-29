---
phase: 5
slug: triage-app
status: draft
nyquist_compliant: false
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
| **Quick run command** | `pytest services/triage/ -x -q` |
| **Full suite command** | `pytest services/triage/ -v` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest services/triage/ -x -q`
- **After every plan wave:** Run `pytest services/triage/ -v`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 05-01-01 | 01 | 1 | ADR-004 | — | DB migration idempotent | unit | `pytest services/triage/tests/test_migration.py -x -q` | ❌ W0 | ⬜ pending |
| 05-02-01 | 02 | 2 | ADR-004 | — | consume() persistent loop | unit | `pytest services/triage/tests/test_bus_consume.py -x -q` | ❌ W0 | ⬜ pending |
| 05-03-01 | 03 | 3 | ccir.md | — | scoring produces verdict | integration | `pytest services/triage/tests/test_score.py -x -q` | ❌ W0 | ⬜ pending |
| 05-04-01 | 04 | 4 | ccir.md | — | dedup blocks duplicate items | unit | `pytest services/triage/tests/test_dedup.py -x -q` | ❌ W0 | ⬜ pending |
| 05-05-01 | 05 | 5 | ADR-004 | — | shadow-run matches old path | integration | `pytest services/triage/tests/test_shadow.py -x -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `services/triage/tests/__init__.py` — package init
- [ ] `services/triage/tests/test_migration.py` — DB migration stubs
- [ ] `services/triage/tests/test_bus_consume.py` — consume() loop stubs
- [ ] `services/triage/tests/test_score.py` — scoring stubs
- [ ] `services/triage/tests/test_dedup.py` — dedup stubs
- [ ] `services/triage/tests/test_shadow.py` — shadow-run stubs

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Shadow-run matches Fever poll output end-to-end | ADR-004 | Requires live RabbitMQ + Postgres + qwen36 | Run both paths on 20 items, compare `verdict.ready` payloads |
| Fever poll removed cleanly (no dead code) | ADR-004 | Structural check | `grep -r "fever" services/ --include="*.py"` returns 0 hits |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
