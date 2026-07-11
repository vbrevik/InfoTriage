---
phase: 06-brief-app
fixed_at: 2026-07-11T21:05:00Z
review_path: .planning/phases/06-brief-app/06-REVIEW.md
iteration: 1
findings_in_scope: 5
fixed: 5
skipped: 0
status: all_fixed
---

# Phase 06: Code Review Fix Report

**Fixed at:** 2026-07-11T21:05:00Z
**Source review:** .planning/phases/06-brief-app/06-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 5 (fix_scope: critical_warning — 5 Info findings excluded)
- Fixed: 5
- Skipped: 0

**Verification:** `python -m pytest tests/test_vault_writer.py tests/test_brief_consumer.py -q` → 17 passed, 0 failed (run after all fixes applied).

## Fixed Issues

### CR-01: NULL `score` crashes `write_vault_digest` and aborts all vault writes

**Files modified:** `apps/brief/vault_writer.py`
**Commit:** 87fad9f
**Applied fix:** Replaced `r.get("score", 0)` with `(r.get("score") or 0)` in the keep-filter, `-(x.get("score") or 0)` in the SAB sort key, and `item.get('score') or 0` in the SAB body render — NULL scores now coerce to 0 instead of raising `TypeError`.

### WR-01: `render_wikilinked` corrupts output for overlapping entities; dead regex escape

**Files modified:** `apps/brief/vault_writer.py`
**Commit:** c0a2af0
**Applied fix:** Rewrote replacement loop to iterate entities longest-first and use `re.sub` with `(?<!\[)\b{escaped}\b(?!\])` — word boundaries prevent prefix corruption ("Ukraine" inside "Ukrainian"), lookarounds skip already-wikilinked text, and the previously-dead `re.escape` is now actually used.

### WR-02: `_SYSTEM_TOPICS` leading-space entries and junk topic

**Files modified:** `apps/brief/vault_writer.py`
**Commit:** 10b2a03
**Applied fix:** Stripped leading spaces from the ten affected entries, removed the `"clearly"` junk topic and the duplicate `"norway"`, and added defensive `topic.strip().title()` in the match loop.

### WR-03: `VAULT_INCLUDE_EMAIL` parsing treats any value other than `"1"` as disabled

**Files modified:** `apps/brief/vault_writer.py`
**Commit:** 342bd63
**Applied fix:** Parsing is now `os.environ.get("VAULT_INCLUDE_EMAIL", "1").strip().lower() not in ("0", "false", "no")` — common truthy strings (`true`, `yes`, `" 1"`) no longer silently invert the toggle.

### WR-04: Tautological assertion in `test_extract_entities_with_known_topics`

**Files modified:** `tests/test_vault_writer.py`
**Commit:** ca7ea0a
**Applied fix:** Replaced the always-true disjunction with the concrete expectation: `assert "Norge" not in entities` (the test text contains no "norge"; "norge" is not a substring of "norwegian").

## Skipped Issues

None — all in-scope findings were fixed. Info findings IN-01 through IN-05 were out of scope (fix_scope: critical_warning).

---

_Fixed: 2026-07-11T21:05:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
