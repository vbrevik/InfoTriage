---
phase: 1
slug: contracts-monorepo-skeleton
status: ready
nyquist_compliant: true
wave_0_complete: false
created: 2026-06-27
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.3.3 (already installed — no download) |
| **Config file** | `pyproject.toml` (repo root) — `[tool.pytest.ini_options]`, created in plan 01-02 Task 1 |
| **Quick run command** | `pytest tests/ -x -q` |
| **Full suite command** | `pytest tests/ --tb=short` |
| **Estimated runtime** | ~2 seconds (all checks are unit-level) |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/ -x -q`
- **After every plan wave:** Run `pytest tests/ --tb=short`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 1-01-01 | 01 | 1 | R1, R2 | T-01-01 / T-01-02 | pydantic ValidationError on naive ts and invalid `cnr`/`bucket`/over-long reason; no secrets/endpoints in `libs/contracts` | unit | inline import-check (Task 1 verify, prints `TASK1 OK`); then `pytest tests/test_contracts.py -k "item or event" -q` | ❌ W0 (`tests/test_contracts.py`) | ⬜ pending |
| 1-01-02 | 01 | 1 | R3, R4 | T-01-01 | codec parses only with `yaml.safe_load`; lossless round-trip; bus dedup/FIFO/empty no-op | unit | inline codec+bus check (Task 2 verify, prints `TASK2 OK`); then `pytest tests/test_contracts.py -k "codec or bus" -q` | ❌ W0 (`tests/test_contracts.py`) | ⬜ pending |
| 1-01-03 | 01 | 1 | R1, R2, R3, R4 | — | N/A | unit | `pytest tests/test_contracts.py -q` | ❌ W0 (this task creates it) | ⬜ pending |
| 1-02-01 | 02 | 2 | R5 | — | N/A | config | `python3 -c "import tomllib; ..."` (Task 1 verify, prints `TASK1 OK`) | ✅ (creates root `pyproject.toml`) | ⬜ pending |
| 1-02-02 | 02 | 2 | R5 | T-02-PATH / T-02-SECRET | all 7 depth-fixed path constants resolve to repo-root artifacts; `.env` loads stay on the gitignored repo-root `.env`; no cross-app import | structural | STRUCT + 7 path greps + boundary greps (Task 2 verify, prints `STRUCT OK` then `PATHS+BOUNDARY OK`) | ✅ (re-homed scripts) | ⬜ pending |
| 1-02-03 | 02 | 2 | R5 | T-02-BOUND / T-02-SECRET | no `sys.path.insert`/`unittest.main()`; credential-leak guard preserved in `test_write_bluf.py` | regression | `pytest tests/ -q` (6 migrated files + `test_contracts.py`) | ✅ (migrated in place) | ⬜ pending |
| 1-03-01 | 03 | 3 | R6 | T-03-DOC | docs edits introduce no secret/token/credential | smoke | R6-DOCS grep set incl. `A-5`-not-`PLANNED` assertion (Task 1 verify, prints `R6-DOCS OK`) | ✅ (`.planning/REQUIREMENTS.md`) | ⬜ pending |
| 1-03-02 | 03 | 3 | R6 | T-03-DOC | N/A | smoke | README path grep set (Task 2 verify, prints `README-PATHS OK`) | ✅ (`README.md`) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_contracts.py` — stubs/tests for R1 (Item id/validation), R2 (4 event models), R3 (codec round-trip), R4 (bus dedup/FIFO/empty) — created in plan 01-01 Task 3.
- [ ] `pyproject.toml` (repo root) — `[tool.pytest.ini_options]` with `pythonpath = ["apps/triage","apps/opml","apps/ingest"]` and `testpaths = ["tests"]` — created in plan 01-02 Task 1.
- [ ] `libs/contracts/pyproject.toml` + `libs/contracts/src/contracts/__init__.py` — package definition + exports (editable install) — created in plan 01-01 Task 1.

*No `tests/conftest.py` is created — the `pyproject.toml` `pythonpath` option replaces every removed `sys.path.insert` (RESEARCH Open Question 2 RESOLVED).*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|

*None — all phase behaviors have automated verification (R6 doc corrections are grep-asserted, not manual).*

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (`tests/test_contracts.py`, root `pyproject.toml`, `libs/contracts` package)
- [x] No watch-mode flags
- [x] Feedback latency < 5s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-06-27
