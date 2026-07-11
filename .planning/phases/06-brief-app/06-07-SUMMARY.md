---
phase: 06-brief-app
plan: 07
subsystem: brief
tags: [obsidian-vault, email-privacy, python, pytest]

requires:
  - phase: 06-brief-app
    provides: apps/brief/vault_writer.py (Obsidian vault projection, VAULT_INCLUDE_EMAIL toggle)
provides:
  - Corrected VAULT_INCLUDE_EMAIL=0 exclusion predicate that actually matches production gmail/imap rows
  - Regression tests locking both directions (excluded under =0, included under default) for both email adapters
affects: [phase-06-verification, phase-07-ops-cutover]

tech-stack:
  added: []
  patterns:
    - "Email-surface detection by url scheme (imap://, gmail://), not source field — source holds adapter/mailbox name, url holds the transport URI"

key-files:
  created: []
  modified:
    - apps/brief/vault_writer.py
    - tests/test_vault_writer.py

key-decisions:
  - "Excluded email by matching r['url'] against _EMAIL_URL_SCHEMES = (\"imap://\", \"gmail://\") instead of r['source'] — source_type isn't available to vault_writer.py's row shape (consumer.py's SELECT omits it), so url-scheme is the only reliable, in-file-scope signal."

patterns-established:
  - "Trust-boundary exclusion toggles (privacy opt-outs) must be tested against production-shaped field values, not synthetic shapes that happen to match the buggy predicate — the UAT gap here was a synthetic control test coincidentally passing."

requirements-completed: [SC3]

coverage:
  - id: D1
    description: "VAULT_INCLUDE_EMAIL=0 excludes production gmail rows (source='gmail', url='gmail://...') from the vault"
    requirement: "SC3"
    verification:
      - kind: unit
        ref: "tests/test_vault_writer.py#test_gmail_row_excluded_when_email_disabled"
        status: pass
    human_judgment: false
  - id: D2
    description: "VAULT_INCLUDE_EMAIL=0 excludes production imap rows (source=<mailbox name>, url='imap://...') from the vault"
    requirement: "SC3"
    verification:
      - kind: unit
        ref: "tests/test_vault_writer.py#test_imap_row_excluded_when_email_disabled"
        status: pass
    human_judgment: false
  - id: D3
    description: "Non-email rows (RSS/http(s) urls) are never dropped by the VAULT_INCLUDE_EMAIL toggle"
    requirement: "SC3"
    verification:
      - kind: unit
        ref: "tests/test_vault_writer.py#test_non_email_row_not_excluded_when_email_disabled"
        status: pass
    human_judgment: false
  - id: D4
    description: "Gmail rows are included by default (VAULT_INCLUDE_EMAIL unset)"
    requirement: "SC3"
    verification:
      - kind: unit
        ref: "tests/test_vault_writer.py#test_gmail_row_included_by_default"
        status: pass
    human_judgment: false

duration: 3min
completed: 2026-07-11
status: complete
---

# Phase 6 Plan 07: Vault email-exclusion url-scheme fix Summary

**Fixed VAULT_INCLUDE_EMAIL=0 to actually exclude production email rows by matching the `url` scheme (`imap://`/`gmail://`) instead of the `source` field, which never carried a mail URI on real gmail/imap adapter output.**

## Performance

- **Duration:** 3 min
- **Started:** 2026-07-11T20:19:42Z
- **Completed:** 2026-07-11T20:22:07Z
- **Tasks:** 2 completed
- **Files modified:** 2

## Accomplishments
- Root-caused and fixed the UAT round-2 Test 6 gap: `write_vault_digest()`'s email-exclusion predicate tested `source.startswith("imap://")`, but production gmail rows carry `source="gmail"` and production imap rows carry `source=<mailbox name>` — neither shape was ever caught, so email content leaked into the Obsidian vault even with the opt-out set.
- Added `_EMAIL_URL_SCHEMES = ("imap://", "gmail://")` and rekeyed the exclusion on `r["url"]`, which reliably carries the mail transport URI for both adapters (`gmail://message/...`, `imap://<host>/<id>`).
- Added 4 regression tests covering both directions (excluded under `VAULT_INCLUDE_EMAIL=0`, included by default) for both email adapters, plus a non-email guard proving RSS/http(s) rows are never dropped by the toggle.
- Followed TDD: RED confirmed (both `*_row_excluded_when_email_disabled` tests failed against the pre-fix predicate) before the one-line/one-constant fix landed, then GREEN confirmed (all 14 tests in the file pass).

## Task Commits

Each task was committed atomically:

1. **Task 1: Add production-shaped email-exclusion regression tests (RED)** - `d7dba4a` (test)
2. **Task 2: Fix the email-exclusion predicate by URL scheme (GREEN)** - `8ef54ee` (fix)

**Plan metadata:** (pending — final metadata commit follows this SUMMARY)

## Files Created/Modified
- `apps/brief/vault_writer.py` - Added `_EMAIL_URL_SCHEMES` constant and rekeyed the `VAULT_INCLUDE_EMAIL=0` exclusion predicate in `write_vault_digest()` from `source` to `url` scheme matching.
- `tests/test_vault_writer.py` - Added `test_gmail_row_excluded_when_email_disabled`, `test_imap_row_excluded_when_email_disabled`, `test_non_email_row_not_excluded_when_email_disabled`, `test_gmail_row_included_by_default`.

## Decisions Made
- Kept the fix entirely inside `vault_writer.py` (no consumer/SQL change) by using `url` scheme rather than the canonical `source_type` column, because `apps/brief/consumer.py`'s enrichment SELECT (line ~61-68) does not select `source_type` — it never reaches `write_vault_digest()`'s row dicts. This matches the plan's explicit rationale and keeps the change surgical.

## Deviations from Plan

None - plan executed exactly as written (both tasks, RED then GREEN, single predicate + one constant change).

## Issues Encountered

None specific to this plan. A full-suite `pytest tests/ -q` run afterward showed one unrelated pre-existing failure, `tests/test_bus_consume.py::test_consume_delivers_message` (RabbitMQ live-consumer contention — q.triage/q.brief consumers eating test messages), out of this plan's scope (`files_modified` is limited to `apps/brief/vault_writer.py` and `tests/test_vault_writer.py`). Logged to `.planning/phases/06-brief-app/deferred-items.md` under a new "From 06-07 execution" entry; not fixed.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- The VAULT_INCLUDE_EMAIL=0 privacy opt-out now works correctly against real gmail/imap adapter output; ROADMAP SC3's exclusion half is closed. Phase 6 UAT round-2 Test 6 gap resolved.
- No blockers for Phase 07 (ops-cutover). The unrelated RabbitMQ live-consumer test contention (`test_consume_delivers_message`) remains a known, tracked, pre-existing issue — not a blocker for this plan or phase.

---
*Phase: 06-brief-app*
*Completed: 2026-07-11*

## Self-Check: PASSED

- FOUND: apps/brief/vault_writer.py
- FOUND: tests/test_vault_writer.py
- FOUND: commit d7dba4a
- FOUND: commit 8ef54ee
- FOUND: `_EMAIL_URL_SCHEMES` constant present in apps/brief/vault_writer.py
