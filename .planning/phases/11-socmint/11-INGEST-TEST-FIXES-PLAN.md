---
phase: 11-socmint
plan: 02
type: bugfix
wave: 7
triggered_by: make-test-safe-2026-08-01
depends_on:
  - 11-PLAN
files_modified:
  - tests/test_ingest_telegram.py
  - tests/test_ingest_youtube.py
autonomous: true
status: ready
created: 2026-08-01
nyquist_compliant_assumption: true  # Test-side debt; does not invalidate 11-VALIDATION.md State B reconstruction
---

# Phase 11 Sub-Task — Ingest Adapter Test-Fixture Fixes

> **Verify-Work bug-fix sub-task.** Documents 3 failures (2 telegram + 1
> youtube) surfaced by today's `make test-safe` exercise. Tests were last
> green on 2026-07-22 (Phase 11 final closeout at `11-01-SUMMARY.md` /
> `11-WAVE4-SUMMARY.md`); became stale due to (a) a time-bomb fixture
> date and (b) a test-side env-var leak. **Production code is unaffected**
> — neither bug requires changes under `apps/`.

## Triggering event

`make test-safe` run on 2026-08-01 produced:

```
3 failed, 674 passed in 66s
Container infotriage-postgres-test Starting/Stopped/Removed  (clean trap teardown)
```

All 3 failures are in test fixtures. Orthogonal to the Phase 8 db_live question that prompted the run; surfaced as bonus debt findings.

## Bug 1 — Telegram `test_ingest_emits_item_with_discipline_and_reliability`

**Failure:** `assert 0 == 1` (adapter emits 0 items despite `fake_message` fixture setting 1 message).

**Root cause:** `fake_message` fixture hardcodes:

```python
date=datetime.datetime(2026, 7, 21, 10, 0, 0, tzinfo=datetime.timezone.utc),
```

Today (2026-08-01) this date is older than `parse_since("7d")` resolves to (~2026-07-25). `fetch_messages()` filters by `message.date >= since_dt` and breaks the loop on the first pre-window message; the hardcoded date fails the filter and produces 0 messages.

**Last-green date:** 2026-07-22 — within the 7d window at that time. Time-bomb fires ~7d after encoding. The hardcoded date is *itself* the bug; it encodes an unforgiving assumption that "now" stays close to the encoding date.

**Fix direction:** replace the hardcoded date with a relative one:

```python
date=datetime.datetime.now(tz=datetime.timezone.utc) - datetime.timedelta(hours=1),
```

The `-1h` keeps the message comfortably above any plausible `since` window without changing the rest of the fixture's identity (id=42, text, etc.).

## Bug 2 — Telegram `test_ingest_dry_run_does_not_persist`

**Failure:** `assert 0 == 1` (dry-run path emits 0 items despite monkeypatched `build_store`/`build_bus` raising).

**Root cause:** Same stale `fake_message` fixture as Bug 1 — the monkeypatched raises don't fire because `ingest()` returns early (0-item `produced` list) before reaching `build_store`/`build_bus`.

**Fix direction:** Inherited from Bug 1 — fixing Bug 1's fixture also resolves Bug 2 automatically. No additional code change needed for Bug 2 itself; it currently doesn't even reach the assertion-targeting call paths because of the upstream 0-items short-circuit.

## Bug 3 — YouTube `test_ingest_r2_dual_output`

**Failure:**

```
AssertionError: blob must contain stub text
assert (b'transcription disabled' in b'(transcription failed \xe2\x80\x94 could not download audio)' or b'stub mode' in ...)
```

**Root cause:** `_transcribe_default()` reads env var `INFOTRIAGE_YOUTUBE_TRANSCRIBE`. If the env var is set to `1` / `true` / `yes` (anywhere outside the test's `monkeypatch.setenv` scope — e.g., a shell `~/.zshrc`, the project's `.env`, or ambient leakage), the channel's `transcribe_wanted` flips to `True` because `c["transcribe"]` is absent from `_test_channels()`. Then `transcribe()` calls the unmocked `_download_audio("vid1")` → subprocess fails (no real yt-dlp video) → stub fallback `(transcription failed — could not download audio)` — which contains neither sentinel.

**Why today:** the `make test-safe` exercise loaded env-vars from the project's `.env` file via `dotenv` or shell; on a fresh developer shell those vars wouldn't be set, so the test would pass. Today's baseline fetched them.

**Fix direction:** At the very top of `test_ingest_r2_dual_output`, before any other monkeypatch, add a defensive `delenv`:

```python
def test_ingest_r2_dual_output(tmp_path: pathlib.Path, monkeypatch) -> None:
    """..."""
    import youtube_ingest

    # Defensive: isolate from any ambient INFOTRIAGE_YOUTUBE_TRANSCRIBE so the
    # _transcribe_default() baseline reads False regardless of caller env.
    monkeypatch.delenv("INFOTRIAGE_YOUTUBE_TRANSCRIBE", raising=False)
    ...
```

The existing `test_transcribe_default_env_var` and `test_ingest_transcribe_env_var_enables_transcription` use `monkeypatch.setenv` correctly (teardown reverts); this test simply misses the *defensive* `delenv` because it doesn't itself need to set the variable.

## Tasks

### Task 1 — Update Telegram `fake_message` fixture

**File:** `tests/test_ingest_telegram.py`
**Lines:** ~24 (the `fake_message` fixture). Replace:

```python
date=datetime.datetime(2026, 7, 21, 10, 0, 0, tzinfo=datetime.timezone.utc),
```

with:

```python
date=datetime.datetime.now(tz=datetime.timezone.utc) - datetime.timedelta(hours=1),
```

Add a 2-line comment above the fixture explaining the time-bomb history so the next developer doesn't re-introduce the hardcoded date.

**Acceptance:**
- `pytest tests/test_ingest_telegram.py::test_ingest_emits_item_with_discipline_and_reliability -q` passes
- `pytest tests/test_ingest_telegram.py::test_ingest_dry_run_does_not_persist -q` passes (inheritance via shared fixture)
- All other tests in `tests/test_ingest_telegram.py` still pass (no regressions)

### Task 2 — Add explicit env-var isolation to YouTube R2 test

**File:** `tests/test_ingest_youtube.py`
**Action:** Add `monkeypatch.delenv("INFOTRIAGE_YOUTUBE_TRANSCRIBE", raising=False)` as the first line inside `test_ingest_r2_dual_output` body (after the `import youtube_ingest` line).

**Acceptance:**
- `pytest tests/test_ingest_youtube.py::test_ingest_r2_dual_output -q` passes regardless of ambient env
- All other tests in `tests/test_ingest_youtube.py` still pass (no regressions; the existing tests that *do* need the env var continue to use `monkeypatch.setenv` correctly)

### Task 3 — Full-suite verification via `make test-safe`

**Command:** `make -f ops/Makefile test-safe`

**Expected outcome:**

```
DSN smoke check passed; running full pytest...
... 677 passed in 66s (or 0 failed with db_live parametric skips)
Container infotriage-postgres-test Stopping/Stopped/Removed (clean teardown)
```

**Acceptance:**
- 0 test failures (was 3)
- 66s baseline holds (no test bloat)
- Throwaway test container (`infotriage-postgres-test`) on port 22062 cleans up; production container (`infotriage-postgres`) on port 22000 untouched

## Verification gate summary

| Pre-fix baseline | Post-fix target |
|---|---|
| 3 failed (2× telegram + 1× youtube) | 0 failed |
| 674 passed | 677 passed |
| 66s | 66s |
| Trap teardown clean | Trap teardown clean |

DSN safety: `tests/test_dsn_safety.py` and `scripts/check_test_dsn.sh` belt-and-suspenders preserved — `INFOTRIAGE_TEST_DSN=postgresql://test:test@localhost:22062/infotriage_test` (distinct non-prod port).

## Cross-references

- **Triggering event:** today's `make test-safe` baseline at 674 passed / 3 failed (66s)
- **Phase 11 validation:** `11-VALIDATION.md` (`status:validated`, `nyquist_compliant:true` per State B reconstruction at `35e4f73`). The validation surface is the SHIPPED CODE in `apps/ingest-telegram/` + `apps/ingest-youtube/`; it does *not* include test fixtures. **Test-fixes do NOT invalidate the nyquist compliance claim** — they address a separate, post-validation debt surface surfaced by today's first full-suite exercise since 2026-07-22.
- **Phase 11 umbrella plan:** `11-PLAN.md` (Tasks 5/6 = telegram, Task 10 = youtube)
- **LEARNINGS.md anchor:** entries cross-referenced in `.planning/LEARNINGS.md` (Pitfall re: time-bomb fixtures; Pattern re: defensive `monkeypatch.delenv`)

## Out of scope

- ACLED license gate (`11-PLAN.md` Task 3) — already verified
- `ingest-barentswatch` test coverage — passing in current baseline
- Wave 6 Phase 11 closeout — already verified 2026-07-22
- Production code in `apps/ingest-telegram/` + `apps/ingest-youtube/` — bug-free per other passing tests; no code changes needed

## Success criteria

1. `make test-safe` exits 0 (or 0 failed with documented db_live parametric skips only)
2. All 3 previously-failing tests now pass
3. 66s baseline holds (no test bloat)
4. No production code changes (working-tree diff is contained to `tests/test_ingest_telegram.py` + `tests/test_ingest_youtube.py`)
5. LEARNINGS.md updated with the hardcoded-date-pitfall entry (under operator direction)

## Operator decision

This sub-task is `status: ready`. Operator decides:

- **Execute now:** dispatch Tasks 1-2 as a single `test(phase-11): fix stale telegram/youtube fixtures` milestone commit + run `make test-safe` for Task 3 verification
- **Defer:** keep this file as parked debt, carry forward to a dedicated Phase 11 verify-work session
- **Reject as out-of-scope:** if operator judges test-fixes don't need tracked planning (the failures are obvious), tear down this file

Per project rule, push remains operator-only. The commit (if executed) lands in the same atomic pattern as `979467d fix(brief): …`.
