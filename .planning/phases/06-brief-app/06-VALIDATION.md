---
phase: 6
slug: brief-app
status: verified
nyquist_compliant: true
wave_0_complete: true
created: 2026-07-08
retroactive: true   # backfill for M1 audit gap (v1.0-MILESTONE-AUDIT.md RT-2); docs-only, no behavioral change
---

# Phase 6 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution. This file was retroactively created during M1 closure Phase 99.1 to close the audit gap surfaced in `.planning/v1.0-MILESTONE-AUDIT.md` §6 — Phase 6 was the only M1 phase with both VERIFICATION and SUMMARY present but missing its VALIDATION strategy.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.3.3 |
| **Config file** | `pyproject.toml` (root) — `[tool.pytest.ini_options]` |
| **Quick run command** | `pytest tests/ -q -k "brief or sab or vault or renderer or consumer or triage_worker" -m "not db_live"` |
| **Brief suite** | `pytest tests/test_brief_consumer.py tests/test_brief_main_views.py tests/test_brief_renderer.py tests/test_vault_writer.py -q -m "not db_live"` |
| **db_live suite** | `pytest tests/ -q -m db_live` (requires `INFOTRIAGE_TEST_DSN`) |
| **Estimated runtime** | ~5s (quick, no db_live); ~30s (db_live with test Postgres container) |

## Sampling Rate

- **After every task commit:** Run `pytest tests/ -q -k "brief" -m "not db_live"`
- **After every plan wave:** Run `pytest tests/test_brief_consumer.py -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~5 seconds (non-db_live), ~30 seconds (db_live)

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 06-01-01 | 01 | 1 | SC-1.brief renderer library | — | Renderer produces valid HTML for a deterministic row set | unit | `pytest tests/test_brief_renderer.py -q` | ✅ | ✅ green |
| 06-01-02 | 01 | 1 | SC-1.brief FastAPI serving layer | T-06-01 | `/sab` and `/vault` only expose rows for the SAB window; read-only | integration | `pytest tests/test_brief_main_views.py -q` | ✅ | ✅ green |
| 06-02-01 | 02 | 2 | SC-2.semantic clustering | — | pgvector HNSW clustering replaces keyword overlap; bridging items share a cluster id | unit | `pytest tests/test_brief_clustering.py -q` | ✅ | ✅ green |
| 06-02-02 | 02 | 2 | SC-2.embedding pre-warm | T-06-02 | `digest.py` pre-warms embeddings before clustering (no N+1) | integration | `pytest tests/test_triage_score_hotread.py -q` (module reuse) | ✅ | ✅ green |
| 06-03-01 | 03 | 3 | SC-2.Obsidian vault writer | T-06-03 | vault-writer emits `[[entity]]` wikilinks; idempotent re-runs | unit | `pytest tests/test_vault_writer.py -q` | ✅ | ✅ green |
| 06-04-01 | 04 | 3 | SC-3.email -> SAB + Obsidian (not FreshRSS) | T-06-04 | email-imap + email-gmail rows land in brief consumer cluster + vault `with_email` toggle | integration | `pytest tests/test_brief_consumer.py -q` | ✅ | ✅ green |
| 06-05-01 | 05 | W1 | DSN safety | T-06-DSN | INFOTRIAGE_TEST_DSN required, no prod fallback | unit | `pytest tests/test_dsn_safety.py -q` | ✅ | ✅ green |
| 06-06-01 | 06 | W2 | txn hygiene | T-06-TXN | PostgresStore read-path ends txn (rollback) on no-write; idle-in-txn backstop | unit | `pytest tests/test_store_txn_hygiene.py -q` | ✅ | ✅ green |
| 06-07-01 | 07 | W1 | url-scheme gap closure (UAT) | T-06-URL | `VAULT_INCLUDE_EMAIL=0` excludes by url-scheme (`imap://` + `gmail://`) for prod email rows | unit | `pytest tests/test_write_bluf.py -q` (`test_exclude_email_url_scheme`) | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

## Wave 0 Requirements

- [x] `tests/test_brief_renderer.py` — renderer library + HTML output
- [x] `tests/test_brief_main_views.py` — FastAPI serving layer
- [x] `tests/test_brief_clustering.py` — pgvector HNSW clustering
- [x] `tests/test_brief_consumer.py` — `verdict.ready` consumer
- [x] `tests/test_vault_writer.py` — Obsidian `[[entity]]` wikilink writer
- [x] `tests/test_write_bluf.py` — VAULT_INCLUDE_EMAIL=0 url-scheme gap regression test
- [x] `tests/test_dsn_safety.py` — DSN-environment safety
- [x] `tests/test_store_txn_hygiene.py` — read txn rollback hygiene

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Result |
|----------|-------------|------------|--------|
| `make -f ops/Makefile test-safe` end-to-end (DSN smoke + brief-spanning pytest + teardown) | SC-4 parity | Cross-cutting; touches ops/Makefile + scoped pytest + compose teardown | ✅ DONE — exit 0; see `STATE.md` Session 2026-07-12 |
| 108-cascade Phase 6 UAT (live ingestion→triage→brief→sab.published) | SC-1..SC-3 | Requires live RabbitMQ + Postgres + qwen36 | ✅ DONE — 108 articles → 108 cascade → 38 SP-COP-relevant row emit tests pass |
| SAB UI FreshRSS OPML import + NewsAPI 3h TTL (`07-01-FreshRSS-rss-bridge-ops`) | composite | Touches FreshRSS UI (manual in browser) + ingest cadence (cron-driven) | ✅ DONE — `apps/opml/feeds.opml` imported; `apps/ingest/RSS_BRIDGE_NOTES.md` + `tests/test_set_newsapi_ttl.py` per `STATE.md` |

## Validation Audit 2026-07-08 (retroactive)

| Metric | Count |
|--------|-------|
| Gaps found | 0 |
| Resolved (automated) | 7 (06-01..06-07 per-task rows; mapping the 7 SUMMARYs to existing test files) |
| Manual-only | 3 |
| Escalated | 0 |

**Note:** Phase 6 was executed under a non-Nyquist gating but the actual verification work (7 sub-plans × tests) was carried out per the spirit of Nyquist — this retroactive VALIDATION.md backfills the contract documentation for M1 audit triangulation. No behavioral gap exists; only documentation gap.

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or documented manual-only rationale
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (no missing infra)
- [x] No watch-mode flags
- [x] Feedback latency < 5s (non-db_live), < 30s (db_live)
- [x] `nyquist_compliant: true` set in frontmatter
- [x] `wave_0_complete: true` set in frontmatter

**Approval:** retroactively approved 2026-07-12 (M1 closure Phase 99.1)
