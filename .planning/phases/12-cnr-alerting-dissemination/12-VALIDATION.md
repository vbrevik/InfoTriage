---
phase: 12
slug: cnr-alerting-dissemination
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-08-01
---

# Phase 12 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Synced from `12-RESEARCH.md` §Validation Architecture (2026-08-01); per-task detail lives in each plan's `<verify><automated>` blocks.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (project-wide; `tests/` at repo root) |
| **Config file** | none dedicated — `tests/conftest.py` provides `db_live`/`pg_store` fixtures |
| **Quick run command** | `pytest tests/test_alerting_*.py -q` |
| **Full suite command** | `make -f ops/Makefile test-safe` (throwaway Postgres; baseline 685/0/0) |
| **Estimated runtime** | quick: sub-second–low-seconds · full: ~35–45 s |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_alerting_*.py -q` (InMemoryStore-first)
- **After every plan wave:** Run `make -f ops/Makefile test-safe`
- **Before `/gsd-verify-work`:** Full suite must be green (685+N passed, 0 failed)
- **Max feedback latency:** 60 seconds

---

## Per-Requirement Verification Map

Plan-level map (task-level `<verify>` commands are inside each PLAN.md):

| Req | Behavior | Plans | Test Type | Automated Command | File Exists | Status |
|-----|----------|-------|-----------|-------------------|-------------|--------|
| R1 | Dual-trigger exactly-once | 12-01, 12-04 | unit (mocked Store+bus) | `pytest tests/test_alerting_emitter.py -x` | ❌ W0 | ⬜ pending |
| R2 | Dedupe 24h TTL, injected clock | 12-02, 12-04 | unit | `pytest tests/test_alerting_dedupe.py -x` | ❌ W0 | ⬜ pending |
| R3 | Sliding-window throttle + hourly digest | 12-05 | unit + `db_live` | `pytest tests/test_alerting_throttle.py -x` | ❌ W0 | ⬜ pending |
| R4 | Outbox retry + DLX + broker restart | 12-06 | unit (mocked ntfy) + integration | `pytest tests/test_alerting_outbox.py -x` | ❌ W0 | ⬜ pending |
| R5 | `obsidian://` URI matches vault-writer | 12-01 | unit (cross-module contract) | `pytest tests/test_alerting_deeplink.py -x` | ❌ W0 | ⬜ pending |
| R6 | ntfy ACL 403/200 + fail-closed startup | 12-01, 12-03 | integration + unit | `pytest tests/test_alerting_auth.py -x` | ❌ W0 | ⬜ pending |
| R7 | 7-adapter body UPSERT, NULL vs body-bearing, >1MB backstop | 12-07, 12-08 | unit per-adapter + `db_live` | `pytest tests/test_ingest_*_body.py -x` | ❌ W0 | ⬜ pending |
| R8 + P1–P5 | SAB canonical, `articles.body` NULL isolation, prohibitions | 12-09 | negative/structural tests | `pytest tests/test_alerting_prohibitions.py -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_alerting_emitter.py` — R1 (dual-trigger exactly-once)
- [ ] `tests/test_alerting_dedupe.py` — R2 (24h TTL, injected clock)
- [ ] `tests/test_alerting_throttle.py` — R3 (sliding windows + hourly digest)
- [ ] `tests/test_alerting_outbox.py` — R4 (retry/DLX/restart redelivery)
- [ ] `tests/test_alerting_deeplink.py` — R5 (`obsidian://` URI construction)
- [ ] `tests/test_alerting_auth.py` — R6 (ACL 403/200, fail-closed startup)
- [ ] `tests/test_ingest_{gmail,imap,youtube,telegram,barentswatch,acled,obsidian}_body.py` (or extend existing per-adapter files) — R7
- [ ] `tests/test_alerting_prohibitions.py` — R8 negatives + prohibitions P1–P5
- [ ] `libs/store/sql/011-alert-state.sql` — migration; smoke assertion that table exists post-`init_schema()`
- [ ] `apps/alerting/requirements.txt` + `apps/alerting/Dockerfile` — `docker compose config` + smoke target (no pre-build test possible)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| ntfy bearer token minted into `.env` | R6 | Token is server-generated at runtime (`ntfy token add`), cannot be pre-baked | 12-03 `checkpoint:human-verify`: run token mint flow, capture into `.env`, restart consumer |
| Deep-link tap-through opens item note (A-01/A2 `vault=` semantics) | R5 | Obsidian URI handling only observable on operator device | 12-09 operator UAT: tap push notification, confirm correct note opens |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies (plan-checker Dimension 8 pass, 2026-08-01)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 60s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
