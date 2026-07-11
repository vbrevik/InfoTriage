---
phase: 06-brief-app
verified: 2026-07-11T22:30:00Z
status: passed
score: 15/15 must-haves verified
behavior_unverified: 0
overrides_applied: 0
gaps: []
re_verification:
  previous_status: passed
  previous_score: 14/14 must-haves verified
  gaps_closed:
    - "VAULT_INCLUDE_EMAIL=0 now excludes production email rows — write_vault_digest() in apps/brief/vault_writer.py matches the row's url scheme (imap:// / gmail://) instead of the source field, which never carried a mail URI on real adapter output (source='gmail' or source=<mailbox name>). Fixed in 8ef54ee, locked by 4 new regression tests in d7dba4a (tests/test_vault_writer.py, 14/14 pass)."
  gaps_remaining: []
  regressions: []
---

# Phase 6: Brief app Verification Report

**Phase Goal:** SAB/digest become an event-driven product plus an Obsidian projection.
**Verified:** 2026-07-11
**Status:** passed
**Re-verification:** Yes — re-verification #3, focused on gap-closure plan 06-07 (UAT round 2, Test 6: `VAULT_INCLUDE_EMAIL=0` did not exclude production email rows). Confirms the fix and re-checks for regressions against the full must-have set carried forward from the 2026-07-11 "passed 14/14" report.

## Goal Achievement

### Observable Truths — 06-07 gap-closure (new this round)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 15a | With `VAULT_INCLUDE_EMAIL=0`, a production gmail row (`source='gmail'`, `url='gmail://message/…'`) is excluded from vault output | ✓ VERIFIED | `apps/brief/vault_writer.py:20` defines `_EMAIL_URL_SCHEMES = ("imap://", "gmail://")`; line 261 filters `kept = [r for r in kept if not (r.get("url") or "").startswith(_EMAIL_URL_SCHEMES)]`. `tests/test_vault_writer.py::test_gmail_row_excluded_when_email_disabled` uses the exact production shape (`source="gmail"`, `url="gmail://message/abc123"`) and asserts no per-item `.md` and absence from `obsidian-sab.md`. Ran directly: **PASS** |
| 15b | With `VAULT_INCLUDE_EMAIL=0`, a production imap row (`source=<mailbox name>`, `url='imap://<host>/<id>'`) is excluded | ✓ VERIFIED | `test_imap_row_excluded_when_email_disabled` uses `source="Telegraph Ukraine"` (a mailbox name, not a URI) + `url="imap://mail.example.com/msg-1"` — the exact shape UAT proved leaked previously. Ran directly: **PASS** |
| 15c | With `VAULT_INCLUDE_EMAIL=1` (default, unset), email rows are included | ✓ VERIFIED | `test_gmail_row_included_by_default` (new) + pre-existing `test_write_vault_digest_includes_email_by_default` (imap shape) both assert inclusion. Ran directly: **PASS** |
| 15d | Non-email rows (RSS/YouTube/Obsidian web-clips) are never dropped by the toggle | ✓ VERIFIED | `test_non_email_row_not_excluded_when_email_disabled` — `source="NRK"`, `url="https://nrk.no/article-1"` — asserts the file exists under `VAULT_INCLUDE_EMAIL=0`. Ran directly: **PASS** |

**Root-cause match:** The 06-07-PLAN diagnosis (production gmail rows carry `url=gmail://…`, imap rows carry `url=imap://…` while `source` holds the adapter/mailbox name, never a URI) is exactly what the code now checks — confirmed by reading `apps/brief/vault_writer.py` directly, not by trusting the SUMMARY narrative.

**Score (this round):** 4/4 new must-haves verified.

### Observable Truths (ROADMAP.md Success Criteria — the contract, re-checked for regression)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `brief` subscribes `verdict.ready`, clusters via pgvector, renders SAB at :22040, publishes `sab.published` | ✓ VERIFIED (no change) | Unchanged from prior "passed 14/14" report — `apps/brief/consumer.py`/`main.py` still join `infotriage.embeddings`; 06-07 touched only `vault_writer.py` and its test file (confirmed via `git show 8ef54ee --stat` / `d7dba4a --stat`, no other files modified) |
| 2 | A vault-writer emits high-value items + the SAB as Obsidian `.md` (front-matter, body summary, `[[entity]]` wikilinks) | ✓ VERIFIED (no change) | `write_item_obsidian`, `write_sab_obsidian`, `write_vault_digest` still present and wired; 06-07 only changed the exclusion predicate inside `write_vault_digest()` |
| 3 | Email surfaces here (SAB + Obsidian), not in FreshRSS — **both directions now correct** | ✓ VERIFIED (strengthened) | SAB half: unchanged, still no source-type filter on the enrichment query. Obsidian half: inclusion (default) AND exclusion (`VAULT_INCLUDE_EMAIL=0`) both now proven against production-shaped rows — the exclusion half was the gap closed this round |

**Score:** 3/3 roadmap success criteria fully verified, no regressions.

### PLAN-level must-haves (06-01 through 06-06 — re-checked for regression, unchanged from prior report)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 4 | `SabPublished` event schema on ContractEvent | ✓ VERIFIED | Unchanged |
| 5 | `render_brief()` — CNR first, CCIR order, cluster metadata | ✓ VERIFIED | `tests/test_brief_renderer.py` re-run this session: passes as part of the 58-test `test_brief_*`/`test_vault_writer.py` group and the full 296-pass suite run |
| 6 | `render_list()` — score >= 8, sorted desc | ✓ VERIFIED | Unchanged, tests pass |
| 7 | `render_bluf()` — [N] citations, LLM-local, placeholder on failure | ✓ VERIFIED | Unchanged |
| 8 | Clustering is per-CCIR — never merges across sections | ✓ VERIFIED | Unit tests pass; not touched by 06-07 |
| 9 | `CLUSTER_THRESHOLD` env var configurable, wired end-to-end | ✓ VERIFIED | Unchanged; not touched by 06-07 |
| 10 | All SQL uses `%s` bind params | ✓ VERIFIED | Unchanged; 06-07 made no SQL changes (explicitly out of scope per plan diagnosis — fix stays inside `vault_writer.py`) |
| 11 | Atomic file writes (`.tmp` + `os.replace`) | ✓ VERIFIED | Unchanged in `vault_writer.py`; the 06-07 diff only touches the filter predicate, not the write path |
| 12 | Concurrent SAB writes don't produce partial reads (BACKSTOP) | ✓ VERIFIED (via prior human UAT) | Unchanged, satisfied by 06-UAT.md round 1/round 2 tests 1 and 7 |
| 13 | No FreshRSS/Fever reads in apps/brief/ | ✓ VERIFIED | `grep -rn "fever(\|fever_key("  apps/brief/` → empty (re-run) |
| 14 | No copied `HTML_TEMPLATE` inline HTML | ✓ VERIFIED | Unchanged |

**Score:** 11/11 must-haves re-verified, no regressions.

**Total this round:** 15/15 (11 regression-checked + 4 new gap-closure truths; roadmap SC1-3 folded into the 11+4 above as compound checks, consistent with the prior report's counting convention).

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `apps/brief/vault_writer.py` | Email-exclusion predicate matches production row shapes | ✓ VERIFIED (was STUB-EQUIVALENT bug) | `_EMAIL_URL_SCHEMES = ("imap://", "gmail://")` at line 20; `write_vault_digest()` line 261 filters on `r.get("url")`, not `r.get("source")`. Read directly — matches the diagnosed fix exactly |
| `tests/test_vault_writer.py` | Regression tests for both email adapters + non-email guard + default-include | ✓ VERIFIED | 4 new tests read in full (lines 227-304): each uses production-shaped field values (not the synthetic `source="imap://…"` shape that coincidentally passed in UAT round 1), asserts both file-absence and SAB-content-absence. Not just present — substantive: distinct assertions per adapter, explicit non-email guard test |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `write_vault_digest()` row filter | production enrichment rows (gmail/imap adapters) | `r.get("url").startswith(_EMAIL_URL_SCHEMES)` | ✓ WIRED | Traced adapter output fields against the filter: `apps/ingest-gmail/gmail_ingest.py` emits `url=gmail://message/<id>` (per 06-07-PLAN diagnosis, re-confirmed by grep of the constant and predicate in the fixed file); `apps/ingest-imap/imap_ingest.py` emits `url=imap://<host>/<id>`. Both schemes are named literals in `_EMAIL_URL_SCHEMES`, and the predicate reads `url`, not `source` — closing the exact mismatch UAT found |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| New 06-07 regression tests pass | `pytest tests/test_vault_writer.py -q` | 14 passed | ✓ PASS |
| No regression in related brief test files | `pytest tests/test_brief_consumer.py tests/test_brief_main_views.py tests/test_brief_renderer.py tests/test_brief_clustering.py -q` | 58 passed | ✓ PASS |
| Full workspace suite (single run) | `pytest -q` | 296 passed, 1 failed, 32 skipped | ⚠️ 1 pre-existing failure — `tests/test_bus_consume.py::test_consume_delivers_message` (RabbitMQ live-consumer contention flake), documented in `deferred-items.md` under "From 06-07 execution" and outside `apps/brief/` scope; count increased from 292→296 passed (the 4 new tests), no new failures |
| Fix diff is scoped exactly as claimed | `git show 8ef54ee --stat` / `git show d7dba4a --stat` | Only `apps/brief/vault_writer.py` (fix commit) and `tests/test_vault_writer.py` (test commit) touched | ✓ PASS |
| Root-cause predicate present and correct | Read `apps/brief/vault_writer.py` lines 18-22, 247-262 directly | `_EMAIL_URL_SCHEMES` tuple + url-scheme filter present exactly as diagnosed | ✓ PASS |

### Requirements Coverage

Phase 6's `requirements:` field convention (established and accepted in the prior two verification rounds) uses SPEC-local/ROADMAP-local references (`R1`-`R6`, `SC1b`, `SC3`, ADR IDs) rather than `.planning/REQUIREMENTS.md` registry IDs. Re-checked: no `.planning/REQUIREMENTS.md` entries reference "Phase 6", "brief-app", or "SC3" (`grep` empty) — confirms no orphaned requirements this round, consistent with prior findings.

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|--------------|--------|----------|
| SC3 | 06-07-PLAN (gap-closure) | Email surfaces here (SAB + Obsidian), not FreshRSS — exclusion half | ✓ SATISFIED (was FAILED per 06-UAT.md round 2, Test 6) | `apps/brief/vault_writer.py` url-scheme predicate; 4 regression tests pass |
| R1-R6, SC1b, ADR-004/006/007 | 06-01 through 06-06 PLANs | Unchanged | ✓ SATISFIED | Re-affirmed, not touched by 06-07 |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `tests/test_bus_consume.py` | 69 | `test_consume_delivers_message` fails against live RabbitMQ (contention) | ℹ️ Info | Pre-existing/known-flaky (documented in `deferred-items.md` "From 06-05 execution" and "From 06-07 execution"); outside `apps/brief/` scope, not introduced or touched by 06-07 |

No 🛑 Blocker or ⚠️ Warning-level anti-patterns found in `apps/brief/vault_writer.py` or `tests/test_vault_writer.py`. No `TBD`/`FIXME`/`XXX` markers introduced by 06-07 (`grep -n -E "TBD|FIXME|XXX" apps/brief/vault_writer.py` → empty).

### Human Verification Required

None. The gap closed this round (VAULT_INCLUDE_EMAIL exclusion) is fully covered by automated regression tests using production-shaped field values — the specific defect class that a prior synthetic-shape test missed. No new behavior in this round depends on live-service state or visual/UX judgment.

### Gaps Summary

The single gap from UAT round 2 (06-UAT.md Test 6: `VAULT_INCLUDE_EMAIL=0` did not exclude production email rows because the exclusion predicate matched `source.startswith("imap://")`, but production rows carry `source="gmail"` or `source=<mailbox name>` — never an `imap://`-prefixed source) is closed:

- `apps/brief/vault_writer.py` now filters on `r["url"]` against `_EMAIL_URL_SCHEMES = ("imap://", "gmail://")`, covering both production email adapters (gmail and imap).
- `tests/test_vault_writer.py` adds 4 regression tests using exact production-shaped rows (not the synthetic shape that previously passed by coincidence): gmail-excluded, imap-excluded, non-email-not-excluded, gmail-included-by-default.
- All 14 tests in `tests/test_vault_writer.py` pass; the 58-test `test_brief_*` group passes; the full 296-test workspace suite run shows no new failures beyond the pre-existing, documented, out-of-scope RabbitMQ flake.
- Diff scope verified via `git show --stat` on both 06-07 commits: only `apps/brief/vault_writer.py` and `tests/test_vault_writer.py` were touched, matching the plan's stated boundary and preventing any risk of regression to the SQL/consumer/clustering/threshold work verified in the prior two rounds.

Phase 6's stated goal — "SAB/digest become an event-driven product plus an Obsidian projection" — remains achieved, now with the Obsidian email-privacy opt-out (SC3) fully closed on both directions (inclusion and exclusion), corroborated by human UAT round 2 (7/8 pass pre-fix, with the one flagged issue now resolved and locked by regression tests) and this codebase re-verification.

---

_Verified: 2026-07-11_
_Verifier: Claude (gsd-verifier)_
