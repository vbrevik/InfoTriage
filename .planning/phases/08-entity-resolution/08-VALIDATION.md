---
phase: 08
slug: entity-resolution
status: approved
nyquist_compliant: true
wave_0_complete: true
created: 2026-07-13
---

# Phase 08 — Entity Resolution Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`) |
| **Quick run command** | `pytest tests/test_triage_entities.py tests/test_store_entities.py tests/test_triage_worker.py tests/test_vault_writer.py tests/test_brief_consumer.py tests/test_validate_entity_threshold.py -q` |
| **Full suite command** | `pytest tests/ -q` |
| **Estimated runtime** | ~30 seconds (inmemory); ~60 seconds with db_live |

---

## Sampling Rate

- **After every task commit:** Run the quick Phase 8 subset above.
- **After every plan wave:** Run `pytest tests/ -q`.
- **Before `/gsd-verify-work`:** Full suite must be green.
- **Max feedback latency:** 60 seconds.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 08-01-01 | 01 | 1 | R1 NER | T-08-01 | NER output stored in Postgres only | unit | `pytest tests/test_triage_entities.py -q` | ✅ | ✅ green |
| 08-01-02 | 01 | 1 | R2 Entity embedding | T-08-03 | Embedding failure caught; entity stored with NULL vector | unit | `pytest tests/test_triage_entities.py::test_embed_entity_name_returns_none_on_failure -q` | ✅ | ✅ green |
| 08-01-03 | 01 | 2 | R3 Entity linking | T-08-02 | ON CONFLICT / delete-before-insert prevents duplicate links on re-process | unit + contract | `pytest tests/test_triage_entities.py tests/test_store_entities.py -q` | ✅ | ✅ green |
| 08-01-04 | 01 | 2 | R4 Store protocol methods | T-08-02 | Idempotent upserts; no duplicate entity_links | contract | `pytest tests/test_store_entities.py -q` | ✅ | ✅ green |
| 08-01-05 | 01 | 3 | R5 Triage worker integration | T-08-04 | Entity resolution failure does not block verdict.ready | unit | `pytest tests/test_triage_worker.py -q` | ✅ | ✅ green |
| 08-01-06 | 01 | 4 | R6 Obsidian projection | T-08-02 | Postgres remains system of record; vault is projection only | unit | `pytest tests/test_vault_writer.py tests/test_brief_consumer.py -q` | ✅ | ✅ green |
| 08-01-07 | 01 | 5 | mE5-large threshold re-validation | — | Threshold documented and validated on cross-language corpus | integration | `pytest tests/test_validate_entity_threshold.py -q` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements.

- [x] `tests/test_triage_entities.py` — unit tests for `apps/triage/entities.py`
- [x] `tests/test_store_entities.py` — contract tests for Store entity methods
- [x] `tests/test_triage_worker.py` — regression tests for worker integration
- [x] `tests/test_vault_writer.py` — vault projection tests
- [x] `tests/test_brief_consumer.py` — consumer view-filter tests
- [x] `tests/test_validate_entity_threshold.py` — threshold validation script tests

---

## Manual-Only Verifications

All phase behaviors have automated verification.

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 60s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-07-13
