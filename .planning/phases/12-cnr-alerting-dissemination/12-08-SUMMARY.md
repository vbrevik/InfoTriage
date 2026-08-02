---
phase: 12-cnr-alerting-dissemination
plan: 08
subsystem: ingest
tags: [pydantic, gmail-mcp, imap, poplib, yt-dlp, telethon, obsidian-frontmatter, barentswatch-ais, acled-deferred]

requires:
  - phase: 12-cnr-alerting-dissemination (plan 12-07)
    provides: "Item.body optional field + PostgresStore/InMemoryStore put_item/get_item
      body-aware write path with the single empty/whitespace-to-None coercion choke point"
provides:
  - "6 of 7 ingest adapters (gmail, imap, youtube, telegram, obsidian, barentswatch) set
    Item.body at their Item(...) construction site, riding the existing persist_and_publish
    call site with zero signature changes"
  - "gmail_ingest.py: _extract_text_body/_decode_gmail_base64 walk the Gmail API payload
    (format=full) to find the text/plain part; NULL when none exists"
  - "imap_ingest.py: both construction sites (_fetch_imap, _fetch_pop3) thread the full
    body_text(msg) result through as body, unsliced, alongside the unchanged 500-char summary"
  - "youtube_ingest.py: transcribe() now returns (display_text, is_real_transcript) so
    ingest() can distinguish an actual transcript from every stub/fallback string"
  - "obsidian_ingest.py: _extract_note_body() returns the note content following the
    frontmatter block, mirroring from_frontmatter's own delimiter matching"
  - "barentswatch_ingest.py: _position_to_item sets body from an optional narrative/notes
    field; a routine AIS ping (the common case) leaves it unset"
  - "tests/test_ingest_body_email.py (7 cases), tests/test_ingest_body_media.py (8 cases),
    tests/test_ingest_body_events.py (3 cases, barentswatch only) — 18 new tests total,
    all assert on store.get_item() so the store's NULL coercion is proven, not just the
    constructed Item"
  - "ACLED (7th adapter) intentionally NOT populated — acled_ingest.py has no Item(...)
    construction site to modify (26-line Phase-11 stub, license-gated per C-11). Operator
    decision 2026-08-02: defer and track as debt (ROADMAP.md backlog Phase 999.7) rather
    than build a speculative fetch pipeline against an unresolved license gate, and rather
    than narrow SPEC R7 / this plan's acceptance criteria to a permanent 6-of-7."
affects: [12-09 (alerting-path body-exclusion prohibition test)]

tech-stack:
  added: []
  patterns:
    - "Adapter body extraction mirrors the store's own choke-point philosophy: adapters
      pass through whatever full text they naturally have (including '' when absent) and
      let put_item's single coercion point turn it into SQL NULL — no adapter re-implements
      the None/empty-string rule"

key-files:
  created:
    - tests/test_ingest_body_email.py
    - tests/test_ingest_body_media.py
    - tests/test_ingest_body_events.py
  modified:
    - apps/ingest-gmail/gmail_ingest.py
    - apps/ingest-gmail/mcp_client.py
    - apps/ingest-imap/imap_ingest.py
    - apps/ingest-youtube/youtube_ingest.py
    - apps/ingest-telegram/telegram_ingest.py
    - apps/ingest-obsidian/obsidian_ingest.py
    - apps/ingest-barentswatch/barentswatch_ingest.py
    - tests/test_ingest_imap.py
  not_modified_intentionally:
    - apps/ingest-acled/acled_ingest.py

key-decisions:
  - "gmail_ingest.py's Item(...) construction site was the plan's stated single edit point,
    but the full body text was NOT already available in scope (contrary to the plan's stated
    assumption) — mcp_client.get_message() called Gmail's API with format='metadata', which
    omits payload.body/parts entirely. Switched to format='full' (mcp_client.py, not in this
    plan's files_modified — Rule 3 blocking-issue deviation) plus new
    _extract_text_body/_decode_gmail_base64 helpers in gmail_ingest.py to walk the resulting
    payload for the text/plain part."
  - "youtube_ingest.py's transcribe() signature changed from -> str to -> tuple[str, bool]
    (display_text, is_real_transcript). The plan's stated construction-site-only edit was
    insufficient: transcribe() always returns a non-empty string (real transcript OR one of
    4 stub/fallback messages), so distinguishing 'has a transcript' from 'transcription was
    attempted/disabled/failed' required a signal transcribe() didn't previously expose.
    Verified no other caller of transcribe() exists (repo-wide grep) before widening it."
  - "obsidian_ingest.py's 'full note text' is interpreted as the markdown content following
    the YAML frontmatter block (the article/clip text), not the raw file including the
    frontmatter header — matches the semantic meaning of 'body' as source content distinct
    from metadata, and mirrors from_frontmatter's own delimiter-matching so the two functions
    never disagree about where the frontmatter ends."
  - "BarentsWatch's narrative field is speculative/defensive — the historic AIS combined API
    this adapter actually calls does not carry a documented free-text field today. The
    note/notes/remark/remarks lookup is there so a future API response variant that does
    carry one is picked up automatically, while today's real traffic (routine AIS pings)
    correctly persists NULL, matching SPEC R7's own AIS-ping example."
  - "ACLED deferred as tracked debt, NOT built now and NOT used to narrow scope (operator
    decision, 2026-08-02). acled_ingest.py is a 26-line stub with no HTTP client, no
    field-mapping, and no Item(...) call — adding body= to it would mean building an entire
    new adapter (Rule 4 architectural territory), not a one-field change. The ACLED license
    is [GATED] per REQUIREMENTS.md C-11 (EULA §7 bars training/developing AI on content,
    conflicts with ADR-004) and open question Q3 — this project holds no ACLED license
    today, so a real pipeline would have nothing to fetch and no adapter test could exercise
    a real feed. SPEC R7 and 12-08-PLAN.md's acceptance criteria are left describing all 7
    adapters (not narrowed to 6-of-7 permanently); the gap is tracked forward instead as
    ROADMAP.md backlog Phase 999.7, to be promoted once Q3 (ACLED license) resolves."

requirements-completed: [ADR-003]

coverage:
  - id: D1
    description: "Gmail adapter sets Item.body from the message's decoded text/plain part
      (via Gmail API format=full), NULL when no readable text part exists"
    requirement: "ADR-003"
    verification:
      - kind: unit
        ref: "tests/test_ingest_body_email.py#test_gmail_text_part_persists_full_body_byte_identical"
        status: pass
      - kind: unit
        ref: "tests/test_ingest_body_email.py#test_gmail_no_text_part_persists_null_body"
        status: pass
    human_judgment: false
  - id: D2
    description: "IMAP adapter sets Item.body at both construction sites (_fetch_imap,
      _fetch_pop3) from the full decoded message text, NULL for whitespace-only payloads"
    requirement: "ADR-003"
    verification:
      - kind: unit
        ref: "tests/test_ingest_body_email.py#test_imap_site_persists_full_text_byte_identical"
        status: pass
      - kind: unit
        ref: "tests/test_ingest_body_email.py#test_pop3_site_persists_full_text_byte_identical"
        status: pass
      - kind: unit
        ref: "tests/test_ingest_body_email.py#test_imap_whitespace_only_payload_persists_null_body"
        status: pass
    human_judgment: false
  - id: D3
    description: "YouTube adapter sets Item.body to the real transcript only (never the stub
      placeholder text); a >=1.1M-char transcript round-trips byte-identical with no truncation"
    requirement: "ADR-003"
    verification:
      - kind: unit
        ref: "tests/test_ingest_body_media.py#test_youtube_transcript_persists_full_body"
        status: pass
      - kind: unit
        ref: "tests/test_ingest_body_media.py#test_youtube_no_transcript_persists_null_body"
        status: pass
      - kind: unit
        ref: "tests/test_ingest_body_media.py#test_youtube_oversized_transcript_round_trips_with_no_truncation"
        status: pass
    human_judgment: false
  - id: D4
    description: "Telegram adapter sets Item.body to the message text; a photo-only post
      with no caption persists NULL (SPEC R7's named bodyless case)"
    requirement: "ADR-003"
    verification:
      - kind: unit
        ref: "tests/test_ingest_body_media.py#test_telegram_message_text_persists_full_body"
        status: pass
      - kind: unit
        ref: "tests/test_ingest_body_media.py#test_telegram_photo_only_no_caption_persists_null_body"
        status: pass
    human_judgment: false
  - id: D5
    description: "Obsidian adapter sets Item.body to the note content following its YAML
      frontmatter; an empty/whitespace-only note persists NULL"
    requirement: "ADR-003"
    verification:
      - kind: unit
        ref: "tests/test_ingest_body_media.py#test_obsidian_note_persists_full_text"
        status: pass
      - kind: unit
        ref: "tests/test_ingest_body_media.py#test_obsidian_empty_note_persists_null_body"
        status: pass
    human_judgment: false
  - id: D6
    description: "BarentsWatch adapter sets Item.body from an optional narrative/notes field;
      a routine AIS position ping persists NULL"
    requirement: "ADR-003"
    verification:
      - kind: unit
        ref: "tests/test_ingest_body_events.py#test_barentswatch_ais_ping_persists_null_body"
        status: pass
      - kind: unit
        ref: "tests/test_ingest_body_events.py#test_barentswatch_narrative_field_persists_full_body"
        status: pass
    human_judgment: false
  - id: D7
    description: "ACLED adapter sets Item.body — DEFERRED, not implemented. acled_ingest.py
      has no Item(...) construction site (Phase-11 stub, C-11 license gate). Operator
      decision 2026-08-02: track as debt (ROADMAP.md backlog Phase 999.7), do not build a
      speculative pipeline against an unlicensed feed, do not narrow SPEC R7's scope."
    requirement: "ADR-003"
    verification: []
    human_judgment: true
    rationale: "No automated verification is possible against a source this project has no
      license to fetch from. Deferred to backlog Phase 999.7, to be promoted once
      REQUIREMENTS.md Q3 (ACLED license) resolves."

duration: ~40min (incl. checkpoint resolution session)
completed: 2026-08-02
status: complete
---

# Phase 12 Plan 08: Ingest adapters set Item.body (6 of 7 shipped — ACLED deferred as tracked debt) Summary

**6 of 7 ingest adapters (gmail, imap, youtube, telegram, obsidian, barentswatch) now UPSERT `articles.body` at ingest via `Item.body`. ACLED is intentionally deferred — not a failure of this plan, but an operator-confirmed decision to track it as backlog debt (Phase 999.7) rather than build a speculative fetch pipeline against a license this project does not hold (REQUIREMENTS.md C-11 `[GATED]`).**

## Performance

- **Duration:** ~40 min total (Tasks 1-3 partial ~35min + checkpoint resolution ~5min)
- **Completed:** 2026-08-02 (final close-out, superseding the earlier checkpoint summary)
- **Tasks:** 3/3 tasks closed — Task 3 closed at its operator-decided scope (barentswatch shipped, ACLED explicitly deferred rather than built)
- **Files modified:** 8 (3 new test files, 1 test file widened, 7 production adapter/client files); `apps/ingest-acled/acled_ingest.py` intentionally untouched

## Accomplishments

- Gmail and IMAP (both construction sites) now populate `Item.body` from the full
  decoded message text, leaving the existing summary derivation untouched.
- YouTube, Telegram, and Obsidian now populate `Item.body` from their respective
  full-text source (transcript, message text, note content), with NULL for every
  documented bodyless case (transcript-less video, photo-only post, empty note).
- BarentsWatch now populates `Item.body` from an optional narrative field, NULL
  for the routine AIS position ping (the common case, and SPEC R7's canonical example).
- 18 new tests across 3 new files, all reading the persisted value back through
  `store.get_item()` so the store's NULL coercion (plan 12-07) is proven per adapter,
  not just the constructed `Item`.
- No adapter applies a size cap, truncation, or HTML sanitization anywhere in the
  body path (grep-confirmed per adapter, plus a >=1.1M-char youtube transcript
  round-trip proving the producer-end half of SPEC R7's no-size-cap backstop).
- Full `pytest tests/ -q` (default, no db_live): **719 passed, 74 skipped, 0 failed**
  at checkpoint — no regressions from any of this plan's edits.
- **ACLED gap resolved by operator decision, not code:** rather than building a
  speculative new adapter (Rule 4 territory) or permanently narrowing SPEC R7's
  acceptance criteria to 6-of-7, the operator chose to close this plan at 6/7 and
  track ACLED forward as `ROADMAP.md` backlog Phase 999.7, gated on
  `REQUIREMENTS.md` Q3 (ACLED license resolution). `12-SPEC.md` R7 and
  `12-08-PLAN.md`'s acceptance criteria remain unmodified — they still describe all
  7 adapters as the eventual target.

## Task Commits

Each task was committed atomically:

1. **Task 1: Email adapters — gmail and imap** - `2a5ddc5` (feat)
2. **Task 2: Media and note adapters — youtube, telegram, obsidian** - `da84889` (feat)
3. **Task 3: Event-feed adapters — barentswatch and acled** - `9e0c692` (feat) — barentswatch shipped; ACLED explicitly not implemented (see Deviations)

**Plan metadata:** this SUMMARY + STATE.md/ROADMAP.md updates committed as `docs(12-08): complete adapter body-wiring plan — 6/7 shipped, ACLED deferred (C-11 gated)`.

## Files Created/Modified

- `apps/ingest-gmail/gmail_ingest.py` - `_extract_text_body`/`_decode_gmail_base64` helpers; `body=` at the construction site
- `apps/ingest-gmail/mcp_client.py` - `get_message` switched from `format="metadata"` to `format="full"` (Rule 3 deviation, see below)
- `apps/ingest-imap/imap_ingest.py` - both construction sites (`_fetch_imap`, `_fetch_pop3`) gain `body=full_text`
- `apps/ingest-youtube/youtube_ingest.py` - `transcribe()` returns `(text, is_real_transcript)`; `body=text if is_real_transcript else None`
- `apps/ingest-telegram/telegram_ingest.py` - `body=text` at the construction site
- `apps/ingest-obsidian/obsidian_ingest.py` - new `_extract_note_body()` helper; `body=note_body` at the construction site
- `apps/ingest-barentswatch/barentswatch_ingest.py` - `body=narrative` (optional note/notes/remark/remarks field) at the construction site
- `apps/ingest-acled/acled_ingest.py` - **not modified, by decision** (see Deviations; tracked forward as backlog Phase 999.7)
- `tests/test_ingest_body_email.py` - new, 7 cases (gmail x3, imap x4 across both sites)
- `tests/test_ingest_body_media.py` - new, 8 cases (youtube x4, telegram x2, obsidian x2)
- `tests/test_ingest_body_events.py` - new, 3 cases (barentswatch x2, 6-of-7 coverage assertion x1)
- `tests/test_ingest_imap.py` - `FIXTURE_ENTRIES` widened from 4-tuples to 5-tuples (matches `fetch_entries`'s new return shape — a Rule 1 regression fix, not a body-feature test)

## Decisions Made

- **gmail full text was not already in scope** — contrary to the plan's `PATTERNS.md`/`RESEARCH.md` example, which showed gmail's construction site as if the full body were already decoded and merely unused. In the actual code, `mcp_client.get_message()` calls Gmail's API with `format="metadata"`, which Gmail's API contract omits `payload.body`/`payload.parts` from entirely — there was no full text to extract without changing the MCP call itself. Fixed by switching to `format="full"` (the minimal correct change) plus new payload-walking helpers.
- **YouTube's `transcribe()` signature widened** to `tuple[str, bool]` rather than trying to distinguish "real transcript" from "stub message" via string-matching on the 4 different stub sentinel strings (fragile, and one is user-visible prose that could plausibly change). Verified via repo-wide grep that `transcribe()` has exactly one caller (`ingest()` itself), so the signature change is fully contained to `youtube_ingest.py`.
- **Obsidian body = note content after frontmatter**, not the whole raw file. This is the natural reading of "full note text" as distinct from the YAML metadata block, and it reuses `from_frontmatter`'s own delimiter-matching logic so the two functions can never disagree about where the frontmatter ends.
- **BarentsWatch's narrative field is speculative/defensive** — the historic AIS combined API this adapter actually calls does not carry a documented free-text field today. The `note`/`notes`/`remark`/`remarks` lookup is there so a future API response variant that does carry one is picked up automatically, while today's real traffic (routine AIS pings) correctly persists NULL, matching SPEC R7's own AIS-ping example.
- **ACLED: defer, track as debt** (operator decision, 2026-08-02, resolving the Task 3 checkpoint). Of the 3 options the checkpoint surfaced (defer / build now / permanently narrow scope), the operator chose defer: close this plan now at 6/7, do not spend this plan's scope building a full ACLED fetch/parse/`Item` pipeline against an unlicensed source, and do not amend `12-SPEC.md` R7 or `12-08-PLAN.md`'s acceptance criteria to permanently shrink the requirement to 6-of-7. The requirement continues to read as covering all 7 adapters; the gap is explicit, tracked, and revisitable — not silently narrowed.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `mcp_client.py`'s `get_message` switched from `format="metadata"` to `format="full"`**
- **Found during:** Task 1 (gmail construction site)
- **Issue:** The plan's `PATTERNS.md`/`RESEARCH.md` analog showed gmail's construction site as though the full message body were already decoded and merely unused (echoing imap's actual state). In reality, `get_message` requests `format="metadata"`, and Gmail API's contract for that format omits `payload.body`/`payload.parts` — there is no full text anywhere in scope to extract. Without this change, Task 1's acceptance criteria (body populated from actual message content) would be unsatisfiable for gmail.
- **Fix:** Changed the MCP tool call's `format` argument to `"full"` (only call site, only caller of `get_message`). Added `_extract_text_body`/`_decode_gmail_base64` in `gmail_ingest.py` to walk the resulting payload (handles both simple and multipart/nested messages) and base64url-decode the text/plain part.
- **Files modified:** `apps/ingest-gmail/mcp_client.py`, `apps/ingest-gmail/gmail_ingest.py`
- **Verification:** `tests/test_ingest_body_email.py` (7 cases) + existing `tests/test_ingest_gmail.py` (4 cases) both pass; `tests/test_ingest_gmail.py`'s mock intercepts at the `mcp_call` level regardless of the `format` param, so no fixture changes were needed there.
- **Committed in:** `2a5ddc5` (Task 1 commit)

**2. [Rule 1 - Bug fix, regression] `tests/test_ingest_imap.py`'s `FIXTURE_ENTRIES` widened to 5-tuples**
- **Found during:** Task 1 (imap construction sites)
- **Issue:** `imap_ingest.fetch_entries()`'s return tuple shape gained a `full_text` element (4-tuple → 5-tuple) to carry the un-truncated body alongside the existing 500-char snippet. `tests/test_ingest_imap.py` monkeypatches `fetch_entries` directly with a hardcoded fixture list, so the old 4-tuple fixture no longer matched the real function's unpacking in `_fetch_imap`, breaking the existing test suite.
- **Fix:** Widened `FIXTURE_ENTRIES` to 5-tuples with a `full_text` value matching each entry's existing snippet text.
- **Files modified:** `tests/test_ingest_imap.py`
- **Verification:** `tests/test_ingest_imap.py` (3 cases) pass unchanged in behavior.
- **Committed in:** `2a5ddc5` (Task 1 commit)

---

**Total auto-fixed:** 2 (1 blocking, 1 regression fix)
**Impact on plan:** Both necessary for Task 1's stated acceptance criteria and test-suite integrity. No scope creep beyond what body-population required.

### DEFERRED (Rule 4 finding, resolved by operator decision — NOT built, NOT scope-narrowed)

**3. [Rule 4 → operator decision: defer] `apps/ingest-acled/acled_ingest.py` has no Item(...) construction site**

- **Found during:** Task 3, `<read_first>` step ("locate its Item construction site by
  grepping for the constructor")
- **What was found:** `acled_ingest.py` is a 26-line Phase-11 stub. Its entire body is:
  ```python
  async def ingest() -> None:
      require_acled_license()
      log.info("ACLED license verified. Ingestion stub complete.")
  ```
  There is no HTTP client, no event-fetching logic, no field-mapping/normalization code,
  and no `Item(...)` call anywhere in the file or directory. `require_acled_license()`
  raises `AcledLicenseMissing` unless `ACLED_LICENSE_KEY` is set (ADR-014's paid-license
  gate; `REQUIREMENTS.md` marks C-11 `[GATED]`; `HANDOFF.json`'s Phase-11 summary confirms
  "ACLED gate keeps unlicensed data out" as intentional). This project has no ACLED license
  today.
- **Why this blocked the plan as originally written:** The plan (and its supporting
  `PATTERNS.md`/`RESEARCH.md`, both written before the executing session's ground-truth
  read) assumed all 7 adapters share the uniform shape gmail's construction site
  exemplifies — an existing `Item(...)` call needing one new keyword argument. That
  assumption does not hold for ACLED. Making Task 3's stated acceptance criteria pass (a
  non-zero `body=` grep count in `apps/ingest-acled`, plus a genuine 7-of-7 coverage
  assertion) would have required writing an entire new ACLED HTTP client, event-fetching
  logic, and field mapping — a new-adapter-scale feature addition comparable in scope to
  BarentsWatch or Telegram's existing adapters, not a one-field change. Squarely deviation
  Rule 4 ("new service layer") territory, correctly routed to a checkpoint rather than
  auto-fixed.
- **What was NOT done:** No fetch logic, HTTP client, or `Item` construction was added to
  `acled_ingest.py`. No fabricated/no-op `Item(...)` call was added purely to make a grep
  pass — that would misrepresent working functionality that does not exist.
  `tests/test_ingest_body_events.py`'s coverage assertion proves 6-of-7 coverage explicitly
  and names the ACLED gap, rather than silently asserting a false 7-of-7.
- **Operator decision (2026-08-02, resolving the checkpoint):** of the 3 options the
  checkpoint proposed (1: defer entirely; 2: build a full pipeline now; 3: permanently
  narrow SPEC/plan acceptance criteria to 6-of-7), the operator picked a variant of option
  1 — defer and track as debt — while explicitly declining option 3's "narrow the
  requirement" framing. `12-SPEC.md` R7 and `12-08-PLAN.md`'s acceptance criteria are left
  unmodified; the gap is recorded as `ROADMAP.md` backlog **Phase 999.7** (ACLED ingest
  adapter — body-population + real fetch pipeline), gated on `REQUIREMENTS.md` Q3 (ACLED
  license resolution) and cross-referenced to C-11.
- **Impact:** `articles.body` is populated for 6 of 7 adapters in production. ACLED rows
  (there are none today, since the license gate blocks all ACLED ingestion) continue to
  have `body IS NULL`, since no ACLED data is ingested at all — the deferral changes
  nothing about production data completeness today.
- **Committed:** the barentswatch half of Task 3 is committed at `9e0c692`;
  `acled_ingest.py` remains untouched at `HEAD`, which is the deliberate outcome, not an
  incomplete state.

## Issues Encountered

None beyond the two auto-fixed deviations and the one operator-resolved deferral, all
documented above.

## User Setup Required

None - no external service configuration required. No new env vars introduced.

## Next Phase Readiness

- **This plan is CLOSED at 6/7 adapters**, by explicit operator decision. ACLED is tracked
  forward as `ROADMAP.md` backlog Phase 999.7 (gated on `REQUIREMENTS.md` Q3 — ACLED
  license resolution), not as an open item on this phase's critical path.
- **Plan 12-09** (alerting-path body-exclusion prohibition test) is NOT blocked by this
  gap — it tests that the alerting path never reads `articles.body`, which holds regardless
  of how many adapters populate it.
- **`STATE.md`/`ROADMAP.md` updated this session** to reflect 12-08 complete (6/7) and the
  new backlog entry. `REQUIREMENTS.md` was NOT touched — `ADR-003` continues to be a
  design-doc reference cited across ~10 requirement rows rather than its own checkbox ID,
  matching every prior 12-0x session's identical finding (`requirements.mark-complete
  ADR-003` returns `not_found`; this is expected, not an error).

## Self-Check: PASSED

- FOUND: tests/test_ingest_body_email.py
- FOUND: tests/test_ingest_body_media.py
- FOUND: tests/test_ingest_body_events.py
- FOUND: 2a5ddc5 (Task 1 commit)
- FOUND: da84889 (Task 2 commit)
- FOUND: 9e0c692 (Task 3 commit — barentswatch shipped, ACLED deferred by decision)

---
*Phase: 12-cnr-alerting-dissemination*
*Completed: 2026-08-02 (final close-out — 6/7 adapters shipped, ACLED deferred as tracked debt per backlog Phase 999.7)*
