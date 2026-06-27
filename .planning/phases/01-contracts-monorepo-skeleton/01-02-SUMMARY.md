---
phase: 01-contracts-monorepo-skeleton
plan: "02"
subsystem: monorepo-restructure
tags: [restructure, pytest, apps, contracts, path-depth]
status: complete

dependency_graph:
  requires:
    - plan 01-01 (contracts editable install — digest.py imports Item from it)
  provides:
    - apps/ingest/ (bridge scripts re-homed)
    - apps/triage/ (score scripts re-homed, wired to contracts)
    - apps/opml/ (OPML scripts re-homed)
    - root pyproject.toml pytest config (pythonpath replaces all sys.path.insert)
    - 6 pytest-native test files (no unittest, no sys.path hacks)
  affects:
    - plan 01-03 (next plan in phase can build on the restructured layout)
    - all Phase 2+ apps (import from apps/ subdirs)

tech_stack:
  added:
    - pyproject.toml [tool.pytest.ini_options] pythonpath (replaces per-test sys.path.insert)
  patterns:
    - apps/{ingest,triage,opml} subdir layout (SPEC R5)
    - exhaustive 7-expression path-depth fix table (RESEARCH Pitfall 1)
    - module-level __contract__ = Item marker for D-08 wiring
    - pytest tmp_path fixture replacing setUp/tearDown tmpdir
    - monkeypatch fixture replacing manual try/finally LLM stubs

key_files:
  created:
    - pyproject.toml
    - apps/ingest/gmail_to_atom.py
    - apps/ingest/imap_to_atom.py
    - apps/ingest/yt_to_atom.py
    - apps/ingest/_util.py
    - apps/ingest/RSS_BRIDGE_NOTES.md
    - apps/triage/triage_score.py
    - apps/triage/digest.py
    - apps/triage/fever_triage.py
    - apps/triage/sab_html.py
    - apps/opml/_check.py
    - apps/opml/feeds.opml
    - apps/opml/working.opml
  modified:
    - tests/test_bridge_escape.py
    - tests/test_ccir_sync.py
    - tests/test_opml_check.py
    - tests/test_opml_roundtrip.py
    - tests/test_score_parse.py
    - tests/test_write_bluf.py
  removed:
    - bridge/ (all 5 files moved to apps/ingest/)
    - score/ (all 4 files moved to apps/triage/)
    - opml/ (all 3 files moved to apps/opml/)

decisions:
  - "pyproject.toml [tool.pytest.ini_options] chosen over pytest.ini and conftest.py (Q3 resolved)"
  - "sab_html.py lands in apps/triage/ not apps/brief/ — sibling import of triage_score forces co-location (Q1 resolved)"
  - "working.opml moved (git-tracked confirmed via git ls-files — Q2 resolved: tracked -> move)"
  - "RSS_BRIDGE_NOTES.md moved from bridge/ not opml/ (RESEARCH Pitfall 7 correction applied)"
  - "7 path-depth fixes applied exhaustively — RESEARCH/PATTERNS were missing 3 expressions (sab_html.py ROOT, gmail_to_atom.py OUT, gmail_to_atom.py .env load)"

metrics:
  duration: "8m"
  completed: "2026-06-27"
  tasks_completed: 3
  tasks_total: 3
  files_created: 14
  files_modified: 6
  files_removed: 12
  test_count: 83
---

# Phase 01 Plan 02: Monorepo Restructure Summary

Re-home bridge/score/opml into apps/{ingest,triage,opml}, apply all 7 exhaustive path-depth fixes, wire digest.py to import Item from contracts (D-08), add root pyproject.toml pytest config, and migrate 6 unittest files to pytest functions — ending with 83 tests green.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add root pyproject.toml pytest config | c22d10c | pyproject.toml |
| 2 | Re-home all scripts into apps/ + path-depth fixes + D-08 wiring | 9035fe5 | 12 moved files (5 ingest, 4 triage, 3 opml) |
| 3 | Migrate 6 test files to pytest + fix OPML paths + green suite | 8d9ca9d | 6 test files |

## What Was Built

### Root pytest config (`pyproject.toml`)

`[tool.pytest.ini_options]` with `testpaths = ["tests"]` and `pythonpath = ["apps/triage", "apps/opml", "apps/ingest"]`. Single config seam that replaces every `sys.path.insert` removed in Task 3.

### Monorepo layout (`apps/`)

- `apps/ingest/` ← `bridge/`: `gmail_to_atom.py` (2 path fixes: OUT + .env), `imap_to_atom.py` (identity), `yt_to_atom.py` (identity), `_util.py` (identity), `RSS_BRIDGE_NOTES.md` (was in bridge/, NOT opml/ per RESEARCH Pitfall 7 correction)
- `apps/triage/` ← `score/`: `triage_score.py` (2 path fixes: CCIR_PATH + .env load at line 180), `digest.py` (ROOT fix + D-08 wiring), `fever_triage.py` (ENV fix), `sab_html.py` (ROOT fix — missed by RESEARCH/PATTERNS as identity move; Q1 resolution: co-located with triage_score.py for sibling import)
- `apps/opml/` ← `opml/`: `_check.py` (identity), `feeds.opml` (identity), `working.opml` (git-tracked, moved per Q2 resolution)

### Exhaustive 7-expression path-depth fix table

All 7 expressions updated (2 missed by RESEARCH/PATTERNS added: sab_html.py ROOT, gmail_to_atom.py OUT + .env):

| File | Expression | Fix |
|------|-----------|-----|
| apps/triage/triage_score.py:19 | CCIR_PATH | `".."` → `"..", ".."` before `ccir.md` |
| apps/triage/triage_score.py:180 | .env load | `".."` → `"..", ".."` before `.env` |
| apps/triage/digest.py:26 | ROOT | `".."` → `"..", ".."` (cascades to OUT, STORE, ccir drift guard, load_dotenv) |
| apps/triage/fever_triage.py:20 | ENV | `".."` → `"..", ".."` before `.env` |
| apps/triage/sab_html.py:23 | ROOT | `".."` → `"..", ".."` (cascades to STORE, OUT, load_dotenv at line 1176) |
| apps/ingest/gmail_to_atom.py:18 | OUT | `".."` → `"..", ".."` before `data` |
| apps/ingest/gmail_to_atom.py:57 | .env load | `".."` → `"..", ".."` before `.env` |

### D-08 contract wiring (`apps/triage/digest.py`)

Added `from contracts import Item` at top of import block and `__contract__ = Item` module-level marker after constants. Type/marker reference only — zero runtime behavior change. Proves the editable install (`pip install -e libs/contracts`) resolves.

### Test migration (6 files)

All 6 test files converted from `unittest.TestCase` classes to pytest module-level functions:
- `sys.path.insert` calls dropped (D-05) — resolved via pyproject.toml pythonpath
- `if __name__ == "__main__": unittest.main()` removed (D-05/D-07)
- `setUp/tearDown` tmpdir → `tmp_path` built-in fixture (`test_opml_check.py`)
- Manual `try/finally` LLM stubs → `monkeypatch.setattr` (`test_write_bluf.py`)
- OPML paths: `opml/feeds.opml` → `apps/opml/feeds.opml` (test_opml_check + test_opml_roundtrip)
- `ccir.md` path unchanged in `test_ccir_sync.py` (file did not move, lives at repo root)
- Credential-leak guard preserved in `test_write_bluf.py`

## Verification Results

```
TASK1 OK  — pyproject.toml parses, testpaths + pythonpath verified via tomllib
STRUCT OK — apps/{ingest,triage,opml} exist; bridge/score/opml are gone
PATHS+BOUNDARY OK — all 7 fixes present; no cross-app-subdir imports
D-08 contract OK — python3 -c "sys.path.insert(0,'apps/triage'); import digest; digest.Item.__name__=='Item'"
pytest tests/ -q -> 83 passed in 0.18s (27 contracts + 56 pre-existing migrated)
```

## Deviations from Plan

### Auto-corrected (RESEARCH/PATTERNS gaps — no deviation rules invoked, corrections were in plan)

**1. sab_html.py ROOT — missed by RESEARCH/PATTERNS**
- RESEARCH/PATTERNS labelled `score/sab_html.py` as an identity move. The plan explicitly noted this was incorrect and that ROOT at line 23 needed the depth fix (same pattern as digest.py). Applied the fix: `ROOT = os.path.join(os.path.dirname(__file__), "..", "..")` — cascades to STORE (line 24), OUT (line 25), and `load_dotenv(os.path.join(ROOT,".env"))` (line 1176).

**2. gmail_to_atom.py OUT + .env — missed by RESEARCH/PATTERNS**
- RESEARCH/PATTERNS missed these two expressions. Plan explicitly listed them as part of the exhaustive 7-fix table. Both corrected as specified.

**3. RSS_BRIDGE_NOTES.md lives in bridge/, NOT opml/**
- RESEARCH/PATTERNS incorrectly placed it in opml/. Plan stated bridge/ — moved from bridge/RSS_BRIDGE_NOTES.md to apps/ingest/RSS_BRIDGE_NOTES.md.

None of these required deviation rule invocation — all corrections were pre-specified in the plan's context section.

## Known Stubs

None — all moved scripts are complete implementations. The `__contract__ = Item` marker in digest.py is a type/reference annotation, not a stub; it proves the contract seam resolves.

## Threat Flags

None — no new network endpoints, auth paths, or schema changes at trust boundaries. All `.env` loads continue to read the gitignored repo-root `.env`. Credential-leak test preserved in `test_write_bluf.py`.

## Self-Check: PASSED
