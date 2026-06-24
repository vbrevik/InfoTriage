# Codebase Concerns

**Analysis Date:** 2026-06-24

## Tech Debt

**Monolithic HTML generator (`score/sab_html.py`):**
- Issue: Single 1,206-line file with 17 functions, mixing HTML generation, CSS styling (800+ lines inline), JavaScript, and presentation logic. High cognitive load for changes.
- Files: `score/sab_html.py`
- Impact: Difficult to modify presentation styles or slide logic; risk of subtle bugs in template rendering or event handling when making changes.
- Fix approach: Consider splitting into modules (HTML template builder, CSS constants, JavaScript handler). For now, document the function responsibility order at the top of the file.

**Credential leak risk in exception handlers:**
- Issue: While `score/digest.py:generate_bluf()` (lines 158–163) redacts exception details from output, other scripts like `score/triage_score.py` and `score/fever_triage.py` use bare `urllib.request.urlopen()` without custom exception wrapping. If an exception occurs in the LLM call, the full error (including potentially revealing stack traces) may be written to stderr.
- Files: `score/triage_score.py` (line 51), `score/fever_triage.py` (line 32)
- Impact: API keys, URLs, or sensitive request details could leak into logs if exception handling is not careful.
- Fix approach: Wrap LLM calls in try-catch with explicit redaction of sensitive fields from error messages. Use length-only / shape-only validation (e.g., `len=16, shape_ok=True`) rather than echoing credential values.

**MAJOR-2: CNR carve-out reference in ccir.md**
- Issue: `ccir.md` CNR Routine bullet includes "NB cross-referencing the SIR-2 carve-out" but the actual carve-out mechanics in the scorer prompt (`score/triage_score.py`) only mention SIR-2 context; unclear if the carve-out is actually enforced in scoring logic.
- Files: `ccir.md` (SIR section), `score/triage_score.py` (line ~71)
- Impact: CNR classification may not align with documented rules if the scorer doesn't implement the carve-out.
- Fix approach: Clarify in `triage_score.py` prompt whether SIR-2 items meeting CNR criteria are auto-promoted to CNR-I, or if they stay in SIR-2. Update `ccir.md` to match the actual logic.

**MINOR-1: CCIR_ORDER vs display convention:**
- Issue: Current order in `score/digest.py` (line 31–39) is PIR-1..6, FFIR-1..3, SIR-1, SIR-2. Military intelligence hierarchy convention (NATO/US) is PIR → SIR → FFIR. Reversed order may confuse analysts expecting alphabetical or rank-based ordering.
- Files: `score/digest.py:CCIR_ORDER`
- Impact: Slides render in non-standard order; minor usability friction.
- Fix approach: Reorder to PIR → SIR → FFIR in `score/digest.py:CCIR_ORDER` and verify `sab_html.py:CCIR_ORDER` matches (currently duplicated).

**Duplicated CCIR_ORDER constants:**
- Issue: `CCIR_ORDER` is defined in both `score/digest.py` (lines 32–39) and `score/sab_html.py` (lines 28–35). If one is updated without the other, they drift.
- Files: `score/digest.py`, `score/sab_html.py`
- Impact: Digest and HTML renderers could classify items differently if the constants diverge.
- Fix approach: Move `CCIR_ORDER` to a shared `score/ccir_data.py` module and import in both files.

## Known Bugs

**Gmail bridge authentication rejected:**
- Symptoms: `bridge/gmail_to_atom.py` returns `imaplib.IMAP4.error: b'[AUTHENTICATIONFAILED] Invalid credentials'` when app password is provided.
- Files: `bridge/gmail_to_atom.py` (line 82)
- Trigger: Run the bridge with `GMAIL_APP_PASSWORD` set to a 16-character alphanumeric value.
- Workaround: Most likely causes (per `.continue-here.md` diagnostics): (1) app password belongs to different Gmail account than `GMAIL_USER`, (2) app password was revoked by 2FA rotation. Regenerate app password at `myaccount.google.com/security` → "App passwords" and ensure it matches the account in `GMAIL_USER`.

## Security Considerations

**Plaintext IMAP / Gmail passwords in `.env`:**
- Risk: `.env` files (including `.mailboxes.json`, `.yt_channels.json`) contain plaintext credentials and are intentionally gitignored. A compromise of the machine exposes all credentials.
- Files: `.env`, `.mailboxes.json`, `.yt_channels.json` (runtime config)
- Current mitigation: Files are gitignored; they live on the machine, never in version control. No read-only IMAP flags are enforced at the Python level (only per-script design).
- Recommendations: (1) Document that `.env` must have file mode `600` (user read/write only) — add a `.pre-commit` hook to check this, (2) Consider adding a validation check at script startup: `os.stat(".env").st_mode & 0o077 != 0` would warn if readable by group/other.

**No SSL/TLS certificate validation:**
- Risk: All IMAP connections (`bridge/imap_to_atom.py:82` uses `imaplib.IMAP4_SSL`, `bridge/gmail_to_atom.py:81` same) default to standard validation. However, no explicit certificate pinning or validation is performed in the bridge code; relies on system trust store.
- Files: `bridge/imap_to_atom.py`, `bridge/gmail_to_atom.py`
- Current mitigation: Standard Python `imaplib.IMAP4_SSL` includes certificate validation by default.
- Recommendations: No action required for local use; if the bridges are ever exposed to untrusted networks, add certificate pinning.

**Unvalidated external URLs in feed items:**
- Risk: Item URLs from feeds (`score/digest.py`, `score/fever_triage.py`) are escaped for HTML rendering but not validated. A malicious feed could inject JavaScript or other payloads if URL escaping is incomplete.
- Files: `score/digest.py` (lines 313–314), `score/sab_html.py` (line 107: `escape()` function)
- Current mitigation: HTML escaping via `escape()` function replaces `&`, `<`, `>`. No URL-specific validation.
- Recommendations: (1) Validate URLs to ensure they are HTTP(S) before rendering, (2) Add CSP headers in `sab_html.py` to prevent inline script execution.

## Performance Bottlenecks

**LLM endpoint latency (synchronous blocking):**
- Problem: All scoring (`score/triage_score.py:llm()`, `score/digest.py:generate_bluf()`, `score/fever_triage.py` scoring loop) calls the LLM endpoint synchronously with 120-second timeouts. If the LLM is slow or unavailable, the entire digest generation stalls.
- Files: `score/triage_score.py` (line 39–52), `score/digest.py` (line 134–163), `score/fever_triage.py` (line 68–83)
- Cause: Single-threaded, sequential item scoring against a remote or slow local model.
- Improvement path: (1) Add a `--timeout-item` flag to abort slow items gracefully (fall back to default bucket), (2) Consider async HTTP with `asyncio` and `httpx` for parallel requests if the LLM supports concurrency, (3) Cache LLM responses by title hash to avoid re-scoring duplicates.

**OPML feed health check (`opml/_check.py`) uses sequential probes by default:**
- Problem: `opml/_check.py` defaults to 8 workers (line 59), but network latency per feed (~10 sec timeout, lines 59–60) can add up across 60+ feeds. Sequential fallback would take 10–15 minutes.
- Files: `opml/_check.py`
- Cause: Each feed probe is a blocking HTTP GET; concurrent.futures with 8 workers helps but is still bounded.
- Improvement path: Increase default worker count to 16–32 for faster health checks, or implement a `--fast` flag to reduce timeout from 10s to 5s for quick checks.

**Digest generation scales with item count:**
- Problem: `score/digest.py:fetch_window()` (line 68–100) fetches items in batches of 50 from Fever. Large time windows can yield hundreds of items; each is scored sequentially (~3s per item with qwen36). A 24-hour digest of 400 items = ~20 minutes.
- Files: `score/digest.py`
- Cause: Sequential LLM scoring.
- Improvement path: (1) Add `--workers` flag to enable parallel scoring (requires a thread pool), (2) Implement an in-memory LRU cache for title-based dedup before scoring, (3) Raise the default `--max` cap and document expected runtime.

## Fragile Areas

**CCIR Taxonomy Sync (`score/digest.py` vs `ccir.md`):**
- Files: `score/digest.py:CCIR_ORDER`, `ccir.md`
- Why fragile: `CCIR_ORDER` and `ccir.md` top-level bullets must match exactly. A mismatch causes an `AssertionError` on import (per the drift guard in `digest.py:45–55`). However, the error message (lines 49–55) outputs two unstructured sets, making it hard for the operator to see exactly which IDs differ.
- Safe modification: Always edit `CCIR_ORDER` and `ccir.md` together. When adding a new CCIR tier: (1) Add a `- **CODE**` bullet in `ccir.md`, (2) Add the tuple to `CCIR_ORDER`, (3) Add the tier to the scorer prompt (`score/triage_score.py:score_item()` lines 61–72 and disambiguation guide line 92–97), (4) Run `python3 -m py_compile score/digest.py` to verify the guard passes.
- Test coverage: No automated test verifies the three-way sync (CCIR_ORDER, ccir.md, scorer prompt). A test file `tests/test_ccir_sync.py` exists but may not cover all tiers comprehensively.

**Fever API availability (`score/fever_triage.py`):**
- Files: `score/fever_triage.py`
- Why fragile: The script assumes FreshRSS Fever API is reachable at `FRESHRSS_FEVER_URL` and authenticated (lines 46–48). If the API goes down or credentials are wrong, the script fails late (after printing startup messages). There's a guard at line 47–48, but it doesn't help if FreshRSS is down completely.
- Safe modification: All auth checks happen early; follow the same pattern before making any Fever calls.
- Test coverage: No integration test against a live FreshRSS instance. Manual smoke test required.

**YouTube bridge slug collision (`bridge/yt_to_atom.py`):**
- Files: `bridge/yt_to_atom.py:slug()` (line 43–45)
- Why fragile: The slug is derived from channel name and truncated to the last 32 chars. Two channels with the same last-32-char substring will collide. The workaround (explicit `name` field in `YT_CHANNELS`) exists but is not enforced; a duplicate `name` silently overwrites the earlier one.
- Safe modification: When adding a YouTube channel, check for slug collisions by running `python3 << 'PYEOF'` with the new channel name, comparing against all existing `.yt_channels.json` entries.
- Test coverage: No test for slug collisions or duplication handling.

## Scaling Limits

**Digest generation time scales O(N) with item count:**
- Current capacity: ~400 items max per run (line 322: `--max 400`); at ~3s per item = ~20 minutes.
- Limit: If item ingest grows to 1000+ per day, digest generation becomes unviable as a daily sync.
- Scaling path: (1) Implement worker threads for parallel LLM scoring, (2) Add a `--fast` mode that uses a cheaper, faster model for pre-filtering, (3) Implement feedback loops so the score model learns which items are junk early and stops processing them.

**FreshRSS database / unread count:**
- Current capacity: Tested with 1,642 articles in a single SQLite database (per `.continue-here.md`).
- Limit: SQLite scales to ~100K articles comfortably; beyond that, unread count queries slow down and background refresh cycles can lag.
- Scaling path: Upgrade FreshRSS backend to PostgreSQL before hitting 100K articles.

**Atom file size (`data/feeds/*.xml`):**
- Current capacity: Gmail bridge, YouTube bridge, IMAP bridge each write their own Atom file. No size limit enforced; entries accumulate indefinitely.
- Limit: FreshRSS import/refresh slows if Atom files exceed ~10 MB.
- Scaling path: Add `--max-entries` flag to bridge scripts; older entries are dropped or archived.

## Dependencies at Risk

**`feedgen` (1.0.0):**
- Risk: Declared in `requirements.txt` but not used in production. OPML, digest markdown, and Atom generation are hand-written. If `feedgen` is removed, production does not break, but the codebase retains a dead dependency.
- Impact: None (unused).
- Migration plan: Remove from `requirements.txt` and any corresponding imports. If Atom generation needs improvement later, add `feedgen` back and refactor the bridge scripts to use it.

**yt-dlp (optional, installed by operator):**
- Risk: YouTube bridge (`bridge/yt_to_atom.py`) requires `yt-dlp` on PATH. If not installed, the bridge fails at line 71–73.
- Impact: YouTube ingestion becomes unavailable.
- Migration plan: Document `yt-dlp` as a required install for YouTube channel support. Add a startup check (`which("yt-dlp")`) to provide a clear error message if missing.

**mlx-whisper / openai-whisper (optional):**
- Risk: Transcription is optional; `bridge/yt_to_atom.py` defaults to stub summaries if neither is installed. However, the fallback logic (lines 104–112) is complex and may silently fail.
- Impact: With `transcribe: true` and neither library installed, summaries will be stub text rather than real transcripts.
- Migration plan: Add a pre-flight check (lines 35–36) that detects missing transcription libraries and warns the operator at startup.

## Missing Critical Features

**No feedback loop for scorer tuning:**
- Problem: The scorer prompt is static (`score/triage_score.py`). If the user disagrees with a score, there's no way to provide feedback so the model learns. The only knob is hand-editing `ccir.md`.
- Blocks: Dynamic tuning of the scorer; understanding which CCIR tiers are over/under-scoring.
- Fix approach: (1) Add a `--feedback` mode to `score/fever_triage.py` that logs user corrections (e.g., "user read this but scorer said skip"), (2) Implement a periodic re-tuning pipeline that analyzes feedback and suggests prompt changes.

**No deduplication across sources:**
- Problem: The same story published in 5 outlets appears as 5 separate items. `score/digest.py:cluster()` groups them visually but does not deduplicate in the verdicts store.
- Blocks: Inflated item counts; redundant scoring of near-duplicates.
- Fix approach: (1) Implement fuzzy title matching (e.g., Levenshtein distance > 0.8) at ingest time, (2) Use a bloom filter to quickly rule out exact duplicates, (3) Log all deduped items for transparency.

**No persistent state for digest generation:**
- Problem: Each call to `score/digest.py` re-scores all items in the time window. If the scorer changes, old scores are discarded. If the model endpoint is down, the digest cannot be re-generated from cache.
- Blocks: Resiliency; ability to replay scorings with different models.
- Fix approach: Persist scores in a timestamped JSON file or SQLite table, keyed by item ID + model name. Reuse cached scores if available and model hasn't changed.

## Test Coverage Gaps

**Scorer prompt tier validation:**
- What's not tested: The 12-tier CCIR enum (`PIR-1..6, FFIR-1..3, SIR-1, SIR-2, none`) is defined in the prompt but not validated against the actual JSON schema the model must return.
- Files: `score/triage_score.py`
- Risk: If the model returns an unexpected tier (e.g., `"PIR-7"`), the scorer does not validate it; downstream code silently treats it as "none" or crashes with a KeyError.
- Priority: **High** — add a `tests/test_triage_score.py` that mocks the LLM and verifies each tier parses correctly and produces valid JSON.

**Credential leak in exception handlers:**
- What's not tested: Error messages from LLM calls should not echo credentials or sensitive request details.
- Files: `score/triage_score.py`, `score/fever_triage.py`, `score/digest.py`
- Risk: A test exception (e.g., simulating `LLM_API_KEY="test_key_12345"`) could leak into the digest markdown.
- Priority: **High** — add `tests/test_credential_redaction.py` that simulates exceptions and asserts no credentials appear in output.

**Bridge error handling (Gmail, IMAP, YouTube):**
- What's not tested: What happens if IMAP connection fails, YouTube is unreachable, or transcription times out.
- Files: `bridge/gmail_to_atom.py`, `bridge/imap_to_atom.py`, `bridge/yt_to_atom.py`
- Risk: Silent failures or partial writes if error handling is incomplete.
- Priority: **Medium** — add integration tests that mock IMAP/HTTP responses and verify graceful failure modes.

**OPML parsing edge cases:**
- What's not tested: Malformed OPML, feeds without `xmlUrl`, nested outlines at unexpected depth.
- Files: `opml/_check.py:load_opml()`
- Risk: Silent drops or crashes if OPML structure is unusual.
- Priority: **Medium** — add `tests/test_opml_edge_cases.py` with malformed OPML samples.

**Atomic file writes:**
- What's not tested: What happens if a digest write is interrupted mid-way (e.g., disk full, process killed).
- Files: `score/digest.py:main()` (lines 356–359), `score/sab_html.py:main()` (lines ~1180–1190)
- Risk: Partial or corrupted output files left on disk.
- Priority: **Low** — `score/digest.py` already uses `.tmp` and `os.replace()` for atomicity; `score/sab_html.py` needs the same pattern.

---

*Concerns audit: 2026-06-24*
