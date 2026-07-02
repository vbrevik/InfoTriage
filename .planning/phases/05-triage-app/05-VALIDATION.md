---
phase: 5
slug: triage-app
status: verified
nyquist_compliant: true
wave_0_complete: true
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
| 05-01-01 | 01 | 1 | ADR-004 | T-05-01/T-05-02 | DB migration idempotent | unit | `pytest tests/test_triage_enrichment.py -x -q` | ✅ | ✅ green (12/12, incl. postgres param) |
| 05-02-01 | 02 | 1 | ADR-004 | T-05-03 | consume() persistent loop | unit | `pytest tests/test_bus_consume.py -x -q` | ✅ | ✅ green (2/2) |
| 05-03-01 | 03 | 2 | ccir.md | T-05-02/T-05-05 | scoring produces verdict | integration | `pytest tests/test_triage_worker.py -x -q` | ✅ | ✅ green (9/9) |
| 05-04-01 | 04 | 3 | ADR-004 | T-05-04/T-05-06 | health endpoint returns 200 | unit | `pytest tests/test_triage_health.py -x -q` | ✅ | ✅ green (1/1) |
| 05-05-01 | 05 | 4 | ADR-004 | T-05-07 | shadow-run matches old path | integration | `pytest tests/test_triage_score_hotread.py -x -q` | ✅ | ✅ green (1/1) + manual shadow-run parity 14/14 (05-UAT.md Test 5) |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `tests/test_triage_enrichment.py` — Store extension + migration (implemented, green)
- [x] `tests/test_bus_consume.py` — consume() loop (implemented, green)
- [x] `tests/test_triage_worker.py` — worker process_item (implemented, green)
- [x] `tests/test_triage_health.py` — health endpoint (implemented, green)
- [x] `tests/test_triage_score_hotread.py` — ccir hot-read (implemented, green)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Result |
|----------|-------------|------------|--------|
| Shadow-run matches Fever poll output end-to-end | ADR-004/R6 | Requires live RabbitMQ + Postgres + qwen36 | ✅ DONE — `scripts/shadow_run.py` run against 43 live enrichment rows, 14/14 genuinely-scored buckets matched (100%), Parity verdict MET. See `05-UAT.md` Test 5, `05-05-SUMMARY.md`. |
| Fever poll removed cleanly (no dead code) | ADR-004/R6 | Structural check | ✅ DONE — `apps/scheduler/scheduler_main.py`'s `ADAPTERS` dict has no fever entry (4 ingest adapters only, confirmed by `05-VERIFICATION.md`); host `crontab -l` has no fever entry; `apps/triage/fever_triage.py` preserved only for `digest.py`'s import. |

---

## Validation Audit 2026-07-02

| Metric | Count |
|--------|-------|
| Gaps found | 0 |
| Resolved | 5 (all Per-Task rows flipped from pending stub → green, using the now-implemented test files) |
| Escalated | 0 |

**Discovered while auditing:** `tests/test_triage_enrichment.py`'s `store` fixture parametrizes its `"postgres"` variant with `marks=_pg_live_skipif` (line 139) — a skipif-only helper, distinct from the file's own correctly-built `db_live` decorator (line 49, used by two standalone tests). This means `pytest -m "not db_live"` does NOT deselect the fixture's postgres-param tests, same footgun already found in `tests/test_store_contract.py` during this session's `/gsd-execute-phase 05` regression gate. Re-running the validation suite with `-m "not db_live"` still exercised the `[postgres]` fixture variants and left one stray test row in the live `infotriage.articles`/`embeddings` tables (cleaned up manually this session — `DELETE FROM infotriage.embeddings/articles WHERE ... source='TestSource'`). Flagged as a real, unfixed test-suite issue — same class of bug as the one already noted in `05-05-SUMMARY.md`'s Issues Encountered section.

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 60s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** verified 2026-07-02
