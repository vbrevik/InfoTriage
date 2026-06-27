---
phase: 01-contracts-monorepo-skeleton
plan: "03"
subsystem: documentation
tags: [docs, requirements, readme, r6, paths, pmesii]
status: complete

dependency_graph:
  requires:
    - plan 01-02 (apps/ tree — source of the path map applied to README.md)
  provides:
    - REQUIREMENTS.md C-9, C-13: "scaffolded" descriptor removed; apps/ingest/ paths
    - REQUIREMENTS.md A-5: [PLANNED] -> [LIVE] with Phase 1.5 PMESII note
    - README.md: all run-commands and prose references point at apps/ tree
  affects:
    - any future plan that reads REQUIREMENTS.md or README.md for reference

tech_stack:
  added: []
  patterns:
    - Doc-only plan pattern: two targeted edits, no code/schema/test changes

key_files:
  created: []
  modified:
    - .planning/REQUIREMENTS.md
    - README.md

key_decisions:
  - "A-5 status set to [LIVE] (not [SPIKE]) — PMESII/TESSOC enrichment fully shipped in Phase 1.5"
  - "C-9 and C-13 status kept as [SPIKE] — transcribe backend and IMAP creds still pending at runtime"
  - "Verification script had planner bug: grep 'opml/feeds.opml' matches apps/opml/feeds.opml substring; spirit of check confirmed satisfied via filtered grep"

requirements-completed: [R6]

coverage:
  - id: D1
    description: "REQUIREMENTS.md C-9 yt_to_atom.py: obsolete scaffolded descriptor removed, path updated to apps/ingest/"
    requirement: R6
    verification:
      - kind: other
        ref: "grep -n 'apps/ingest/yt_to_atom.py' .planning/REQUIREMENTS.md && no scaffolded match -> R6-DOCS OK"
        status: pass
    human_judgment: false
  - id: D2
    description: "REQUIREMENTS.md C-13 imap_to_atom.py: obsolete scaffolded descriptor removed, path updated to apps/ingest/"
    requirement: R6
    verification:
      - kind: other
        ref: "grep -n 'apps/ingest/imap_to_atom.py' .planning/REQUIREMENTS.md && no scaffolded match -> R6-DOCS OK"
        status: pass
    human_judgment: false
  - id: D3
    description: "REQUIREMENTS.md A-5 PMESII tagging: [PLANNED] changed to [LIVE]; source note references Phase 1.5 archive"
    requirement: R6
    verification:
      - kind: other
        ref: "grep 'A-5' .planning/REQUIREMENTS.md | grep -v PLANNED -> R6-DOCS OK"
        status: pass
    human_judgment: false
  - id: D4
    description: "README.md run-commands updated: score/*.py -> apps/triage/*.py, bridge/*.py -> apps/ingest/*.py, cron example updated"
    requirement: R6
    verification:
      - kind: other
        ref: "test -z $(grep -nE 'python3 (score|bridge)/' README.md) -> README-PATHS OK"
        status: pass
    human_judgment: false
  - id: D5
    description: "README.md Bridges section: Three bridge/ scripts -> Three apps/ingest/ scripts; all inline script refs updated"
    requirement: R6
    verification:
      - kind: other
        ref: "grep -nE 'apps/(triage|ingest)/' README.md -> README-PATHS OK"
        status: pass
    human_judgment: false
  - id: D6
    description: "README.md: opml/feeds.opml -> apps/opml/feeds.opml; bridge/RSS_BRIDGE_NOTES.md -> apps/ingest/RSS_BRIDGE_NOTES.md"
    requirement: R6
    verification:
      - kind: other
        ref: "no bare opml/feeds.opml (filtered); apps/opml/feeds.opml present -> README-PATHS OK"
        status: pass
    human_judgment: false

metrics:
  duration: "4m"
  completed: "2026-06-27"
  tasks_completed: 2
  tasks_total: 2
  files_created: 0
  files_modified: 2
---

# Phase 01 Plan 03: Stale Doc Fixes (SPEC R6) Summary

Three stale documentation claims corrected — REQUIREMENTS.md C-9/C-13 "scaffolded" descriptors replaced with "implemented" + apps/ingest/ paths; A-5 PMESII tagging promoted from [PLANNED] to [LIVE]; README.md run-commands and Bridges section repointed to the apps/ tree from plan 01-02.

## Performance

- **Duration:** 4m
- **Started:** 2026-06-27T20:30:24Z
- **Completed:** 2026-06-27T20:33:43Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- REQUIREMENTS.md C-9: `apps/ingest/yt_to_atom.py (implemented — XML-gen + escaping verified)` — "scaffolded 2026-06-23, operator-pivot" removed
- REQUIREMENTS.md C-13: `apps/ingest/imap_to_atom.py (implemented — XML-gen + escaping verified)` — same pattern
- REQUIREMENTS.md A-5: `[PLANNED]` → `[LIVE]` with Phase 1.5 archive reference
- README.md: 12 path/command changes — all `score/` and `bridge/` script references replaced with `apps/triage/` and `apps/ingest/`; `opml/feeds.opml` → `apps/opml/feeds.opml`; `bridge/RSS_BRIDGE_NOTES.md` → `apps/ingest/RSS_BRIDGE_NOTES.md`

## Task Commits

1. **Task 1: Correct REQUIREMENTS.md stale R6 claims** — `b9a1606` (docs)
2. **Task 2: Update README.md run-commands and paths to apps/ tree** — `70e5a25` (docs)

## Files Created/Modified

- `.planning/REQUIREMENTS.md` — C-9, C-13, A-5 rows corrected
- `README.md` — run-commands, Bridges section, Feeds section paths updated

## Decisions Made

- A-5 PMESII status set to `[LIVE]` (not `[SPIKE]`): PROJECT.md confirms "PMESII/TESSOC enrichment done (not planned)" and the Phase 1.5 archive exists at `.planning/archive/phase-1.5-pmesii-enrichment/`.
- C-9 and C-13 status kept as `[SPIKE]`: the runtime blockers (yt-dlp + transcribe backend; IMAP creds) remain. Only the "scaffolded" label was removed — the scripts are implemented but not smoke-tested at runtime.

## Deviations from Plan

### Planner Bug in Verification Script (noted, no fix needed)

The Task 2 verification command `test -z "$(grep -n 'opml/feeds.opml' README.md)"` cannot pass because the pattern `opml/feeds.opml` is a substring of `apps/opml/feeds.opml`. The spirit of the check (no bare `opml/feeds.opml` without the `apps/` prefix) is satisfied — confirmed via `grep -n 'opml/feeds.opml' README.md | grep -v 'apps/opml/feeds.opml'` returning zero results. The R6 requirement is fully met. Noted as a planner-script bug; no code change required.

None of the three deviation rules were invoked — all changes were documentation-only and within plan scope.

## Known Stubs

None — documentation-only plan; no code stubs introduced.

## Threat Flags

None — no new network endpoints, auth paths, file access patterns, or schema changes. Edits are status-wording and path corrections only.

## Self-Check: PASSED
