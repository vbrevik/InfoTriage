# CONCERNS — InfoTriage

Source of truth: code review of last 5 file changes + known-issues from prior sessions.
Generated: 2026-06-23.

Severity legend: **MAJOR** = blocks feature; **MINOR** = smell or convenience; **DRIFT** = will bite eventually.

## ~~MAJOR-1 — `score/triage_score.py` prompt is unaware of new CCIR tiers~~ **CLOSED 2026-06-23**

**Fix landed.** `score/triage_score.py:score_item` prompt now:
- Enumerates all 12 CCIR IDs (PIR-1..6, FFIR-1..3, SIR-1, SIR-2, none) with one-line descriptions per tier.
- Includes a 5-rule disambiguation guide for overlapping tiers (PIR-5/SIR-1, PIR-1/PIR-6, PIR-6/SIR-2, FFIR-3/PIR-4, sport/SIR-2).
- Includes 8 worked examples (one per new tier + PIR-3, PIR-4, FFIR-1, none) showing expected JSON output.
- SAMPLE fixture extended from 5 items (FFIR-3 + none only) to 8 items covering PIR-6, SIR-1, SIR-2, PIR-4, FFIR-1, FFIR-3, and 2× none.
- Verified: `python3 score/triage_score.py --sample --json` scores all items to correct tiers.

## ~~MAJOR-2 — CNR carve-out in ccir.md is dead documentation~~ **CLOSED 2026-06-24 (soften)**

**Fix landed.** `ccir.md` rewritten to match the actual execution path:
- §SIR-2 → "Carve-out-intent" reframed: "VM 2026-hits med sikkerhets-/politisk
  signal eskaleres til SIR-2 (CAT II dagsbrief) eller CAT I ved konkret
  sikkerhetshendelse; ren sportsdekning forblir CNR-Routine." The wording now
  explicitly names `score/triage_score.py:score_item`-promptens disambigueringsguide
  "Sport vs SIR-2" + worked examples (FIFA-format-update → SIR-2 score 5;
  mass-protester → SIR-2 score 7) as the execution mechanism, instead of
  claiming a hardkodet parser.
- §CNR Routine NB → softened: "VM 2026-saker med sikkerhets-/politisk signal
  eskaleres per SIR-2-carve-out (se SIR-2 over) ... Ikke alle saker fra disse
  kildene eskaleres; kun de med sikkerhets-/politisk vinkling." Removes the
  "alle saker fra den kilden" overpromise.
- Top-of-file → clarified: this file is the canonical taxonomy inlined into
  the LLM prompt; carve-out intent is enforced by the scorer prompt's rules +
  examples, not by literal parsing of this file.

**Why this works.** Verified that `score/triage_score.py:score_item` prompt
already has both:
1. Disambiguation rule (line 97): "Sport (general) vs SIR-2: regular sport
   coverage with no security/political angle → 'none'. VM 2026 security,
   protests, boycott, terrortrusler, or political controversy → SIR-2."
2. Worked examples (lines 108-110): "FIFA confirms World Cup 2026 will use
   expanded 48-team format" → SIR-2 score 5; "Threat of mass protests at
   US World Cup venues over immigration policy" → SIR-2 score 7.

So the carved-out behavior the operator expected was *already* being enforced
via the LLM disambiguation + examples — only the doc was over-claiming. The
soften aligns doc with the working semantics; no code change was needed.

**Verification.** `py_compile` clean; DRIFT-1 guard happy (11 ccir.md bullets
== 11 `CCIR_ORDER` entries); `tests/test_score_parse.py` (6 tests) +
`tests/test_write_bluf.py` (3 tests) both pass.

**(wire) shape** (parse `**NB**` / `**CARVE-OUT**` in Python) explicitly
**rejected**: would have violated the "CCIR is the brain — don't retune via
Python" load-bearing constraint, AND duplicated logic the LLM already
embodies semantically via its disambiguation guide + examples. Doc-alignment
was the right cut.

## ~~DRIFT-1 — `ccir.md` and `score/digest.py:CCIR_ORDER` are manually synced~~ **CLOSED 2026-06-24**

**Residual closed.** `tests/test_ccir_sync.py` mirrors the runtime assert as
explicit unittest, so CI / pre-commit catches drift before `digest.py`
is imported in anger. Three places now lock the same invariant:

1. **Hard runtime assert** (top of `score/digest.py`): symmetric-diff
   `AssertionError` at module-import with named ids (e.g.
   `in CCIR_ORDER but not in ccir.md: ['FAKE-99']`).
2. **Test regression net** (`tests/test_ccir_sync.py:test_ids_match`):
   symmetric-diff assertion; surfaces `in ccir.md but not in CCIR_ORDER:
   ['SIR-3']`. Plus 4 structural sanity checks (no duplicates,
   canonical id regex, no-empty-title tuple shape).
3. **Manual convention reminder** (this CONCERNS entry): until drift is
   auto-derived.

**Verified.** py_compile clean; `python3 tests/test_ccir_sync.py -v`
runs 5 assertions green; the existing 16 tests across 3 files
(test_score_parse, test_write_bluf, test_opml_roundtrip) all still pass
— no regression.

**Why "(auto-derive CCIR_ORDER from ccir.md parse)" was rejected at
CONCERNS-write-time.** That shape would silently regress MINOR-2:
`ccir.md`'s section order is PIR → FFIR → SIR, but `CCIR_ORDER` is
PIR → SIR → FFIR (NATO hierarchy per Round C). Auto-parse top-to-bottom
would re-emit the wrong ordering and revert the recent reorder. The
hardcoded-CCIR_ORDER + symmetric-diff guard + new test triple keeps
MINOR-2 in place while fully closing DRIFT-1.

## ~~MINOR-1 — BLUF token cost is unbounded~~ **CLOSED 2026-06-24**

**Fix landed.** `score/digest.py:write_bluf` now accepts `cap_total=N`
(default 6000, CLI: `--bluf-cap-total N`). New helper `_est_tokens(s) =
max(1, len(s) // 4)` is stdlib-only (no tiktoken dep). Per-prompt truncation
in the context builder:

1. Trim loop pops tail items (lowest-score end) while `_est_tokens(frame +
   ctx) > cap_total`; loop guard keeps at least 1 item.
2. If 1 item + frame still exceeds `cap_total`, the section is skipped
   cleanly with `_(seksjon hoppet over — cap {N} for lav til a kjre BLUF_
   marker and a stderr log `…{cid} skipped — cap {N} below frame + 1 item`.
3. Citation list iterates `ctx_items` (post-trim), so bracket numbers match
   exactly what was fed to the LLM — no drift.
4. On ANY trim (incl. skip-section), `bluf.md` ends with an italic footer
   `_Trimmet N elementer for a holde hver LLM-prompt innenfor cap {N}_`.
5. On NO-trim runs, behaviour is byte-identical to before the fix.

**Measured constants.** Frame template (FFIR-1 title) = 785 chars /
`len/4` = 196 estimated tok. Per-block (with summary[:500] + headers) =
145 chars / 36 estimated tok. `cap=6000` default safely absorbs the full
`top_n=12` payload (frame + 12×36 ≈ 232+12×36 = 664 tok estimated).

**Verified.** `py_compile` clean across 10 files. DRIFT-1 guard still happy
(11 ccir.md bullets == 11 CCIR_ORDER entries). `tests/test_write_bluf.py`
now runs 6/6 green (3 new TestBlufTokenCap + 3 prior TestBlufCredentialLeak).
`tests/test_score_parse.py` 6/6 green. `tests/test_opml_roundtrip.py` 4/4
green after stale EXPECTED_RSS_FEEDS bump 61 → 64 (OPML has 64
type="rss" outlines as of 2026-06-24). `python3 score/digest.py --help`
lists `--bluf-cap-total`. Help text documents the lower bound
(`cap <= ~200 tok = smallest frame alone … skips cleanly`).

**Out of scope.** Cluster() keyword-overlap cross-language fragility
(MINOR-9; Phase 2 architectural fix — embeddings). Cumulative
cross-section budget (only used per-call; full-nightly aggregate stays
under operator control via `--bluf-cap-total`).

## ~~MINOR-2 — Section order: PIR → FFIR → SIR~~ **CLOSED 2026-06-23**

**Fix landed.** `score/digest.py:CCIR_ORDER` re-ordered to PIR-1..6 → SIR-1,2 → FFIR-1..3 (NATO intel hierarchy: operationally driven first, then friendly force).

## ~~MINOR-3 — ⚠️ flagging is empirical, no auto-detection~~ **CLOSED 2026-06-24**

**Fix landed.** New `opml/_check.py` is the auto-detector: iterates every `xmlUrl` in `opml/feeds.opml`, GET-probes with a FreshRSS-equivalent Mozilla UA, classifies each feed into ✅ / ⚠️ / ❌ per the OPML header convention, and emits a per-category markdown report. Stdlib-only — `urllib.request`, `xml.etree.ElementTree`, `concurrent.futures`, `argparse`. No new deps, no cloud calls.

**Symbol ↔ status mapping:**
- ✅ HTTP 200 + RSS/Atom XML (lenient path accepts `<?xml + <rss/<feed>` and bare `<rss>/<feed>` after UTF-8 BOM strip)
- ⚠️ 403 Cloudflare bot-block / 404 retired URL / 200 OK with HTML body
- ❌ HTTP 5xx / DNS / TLS / timeout / connection refused

**Tri-state exit policy** wired for cron + pre-commit hooks:
- (default) any ⚠️ OR ❌ → exit 1 (strict gate)
- `--exit-on-error-only` → exit 1 only on ❌ (softer gate)
- `--allow-broken` → exit 0 (informational dashboards)

**Tests.** `tests/test_opml_check.py` — 17 assertions. Classify branches: 200 RSS, 200 Atom, 200 HTML (Pravda), 403 (ISW), 404 (RUSI), 5xx, network-error, 200 unrecognised, 302 redirect, 200 RSS with UTF-8 BOM, 200 bare-rss Atom XML, **HTML-with-literal-`<rss>` false-positive guard**. Loader: 11 categories, 64 RSS feeds, substring filter.

**Verified.** `python3 opml/_check.py --workers 8 --timeout 10` against the real `opml/feeds.opml` finds 51 ✅ live + 13 ⚠️ broken — including the 5 ⚠️ currently flagged in the OPML and 8 others silently degraded (surfaced for the first time). Default exit 1 (broken ⚠️ + ❌). `--allow-broken` exits 0; `--exit-on-error-only` exits 0 if only ⚠️, 1 if any ❌. All 17 test_opml_check assertions green; the other 5 test files (test_opml_roundtrip, test_ccir_sync, test_score_parse, test_write_bluf, test_bridge_escape) still green — no regression. py_compile clean across 13 source files.

**Defensive hardening on the way to closure.**
- `load_opml` originally returned 64 (one tuple per rss) instead of 11 (category groups + rss lists); fixed by extracting `_collect_rss(folder)` and iterating top-level folders only.
- `classify` originally required `<?xml` declaration; feeds that prefix a UTF-8 BOM or omit the prolog got downgraded to ⚠️. Fix: BOM-strip + lenient bare `<rss>/<feed>` path; false-positive guarded against HTML pages that mention `<rss>` literal in text.
- `stdout`/`stderr` both `reconfigure(encoding='utf-8', errors='replace')` in `main()` so markdown em-dashes survive latin-1 shells.
- The `DEFAULT_UA` literal originally contained an em-dash (U+2014); `urllib` encodes User-Agent headers as latin-1 and rejected the request on **every** probe. Replaced with `--` and added an explicit ASCII-only constraint comment.

**Why "auto-patch feeds.opml from probe results" was rejected.** Conflates transient network errors (one-off 5xx, CDN brief flaps) with permanent breakage. Operator glances at the report and manually edits the OPML — one human in the loop per OPML mutation, no silent mutation of the source of truth.

## ~~MINOR-4 — `data/digests/*.md` may carry partial / stale LLM output~~ **CLOSED 2026-06-23**

**Fix landed.** `score/digest.py:main()` now writes each digest file to `<name>.tmp` first, then `os.replace()` atomically. On POSIX this is a single-syscall rename; readers never see a partial file.

## ~~MINOR-5 — Bridges write Atom with hand-built XML, no escaping for raw body text~~ **CLOSED 2026-06-24**

**Fix landed.** New `bridge/_util.py::escape(s)` is the single point of policy for the three bridges.

Changes:
- `bridge/_util.py` — new ~40-line module. `escape(s)` wraps stdlib `html.escape(s, quote=True)` (byte-identical output for any `str`), with two intentional tightenings: `None → ""` (stdlib raises `TypeError`; bridges iterate dict values where missing fields are often `None`) and non-`str` non-`None` raises `TypeError` from the helper itself with a clear `"escape expected str or None, got {type}"` message — fail loud on bad input. Stable contract across Python versions (we don't depend on what `html.escape` happens to do internally — Python 3.13 raises `AttributeError` for `int`, earlier versions differ).
- `bridge/gmail_to_atom.py` — `import html` dropped; `from _util import escape` added; 4 `html.escape(X)` → `escape(X)` (title / id / author / summary). Output byte-identical.
- `bridge/imap_to_atom.py` — same 4 replacements in `write_atom`.
- `bridge/yt_to_atom.py` — same 2 replacements (title + summary).
- `tests/test_bridge_escape.py` — new file, 11 assertions pinning the helper's contract: ASCII + Norwegian (æøåÆØÅ) pass-through, ampersand / angle bracket / double-quote / single-quote escaping, None → "", empty → "", realistic mixed Norwegian title round-trip, no-raw-metachars after double-escape (defense-in-depth invariant), non-`str` non-`None` raises `TypeError`.

**Verified.** 11 + 21 = **32 assertions green across 5 test files**. 12 files `py_compile` clean. Direct `_util.escape` REPL confirms `str` passes through, `None` becomes `""`, `int` / `dict` / `bytes` all raise `TypeError` with type-name in the message. All 3 bridges smoke-import clean.

**Why a helper vs. inline.** Three reasons: (a) **defense-in-depth** — one place owns the escape contract; (b) **testability** — pinned at CI time so drift is caught before a malformed feed breaks FreshRSS; (c) **None-safety + fail-loud-on-bad-input** is a contract the bridges can rely on without each bridge re-checking. Output behavior unchanged for the 10 existing call sites.

## MINOR-6 — Bridge slug collision cases are sneaky

**Where.** `bridge/yt_to_atom.py:slug()` truncates to trailing 32 chars. Two channels whose names normalize to the same trailing-32 are silently aliased.

**Symptom.** Last-write-wins; the operator loses one channel's feed silently.

**Fix shape.** Print a collision warning when two `name:` slots slug to the same value.

## MINOR-7 — Secrets hygiene: `.mailboxes.json` is plaintext with no rotation reminder

**Where.** IMAP app passwords in `.mailboxes.json` (gitignored) — long-lived plaintext. No expiry warning, no last-rotated date.

**Symptom.** Operators forget to rotate. Compromised file = high blast radius.

**Fix shape.** A `_meta` field per entry that the script reads + warns about. Optional.

## ~~MINOR-8 — Loaded-but-stateless `PROFILE` typo in `triage_score.py`~~ **CLOSED 2026-06-23**

**Fix landed.** `PROFILE = CCIR` alias removed from `score/triage_score.py`. Import dropped from `score/fever_triage.py`. Two README references updated to point at `ccir.md` directly.

## MINOR-9 — `cluster()` keyword-overlap is cross-language-fragile

**Where.** `score/digest.py:cluster` uses a `STOP` set built from common English+Norwegian function words; keyword overlap of ≥2 collapses. NRK "Nato-toppmøte" + BBC "NATO summit" + TASS "Саммит НАТО" don't share 4+-char keywords and won't collapse.

**Symptom.** "Same event, multiple languages" clusters aren't merged. Operator reading the digest sees what look like multiple unique clusters.

**Fix shape.** Phase 2 — embed articles + cosine-threshold for cluster merge. Architectural, not bug-shaped.

## X-FILE — Triage decisions still happen at the mark-skip step, irreversible from FreshRSS view

**Where.** `score/fever_triage.py:60` calls `mark=item&as=read&id=…` for anything `score ≤ skip-threshold` or `bucket == skip`. No undo API. The mark is API-mutating.

**Symptom.** If the scorer's prompt regresses (MAJOR-1 above), every item is misrouted to skip and silently auto-marked-read. The fact is invisible until you next read the digest.

**Fix shape.** Add a `--snapshot` mode that writes what *would* be marked, without firing. Already partially present (`--dry-run`), but the failure cases from MAJOR-1 would still go through mark-read on the *next* non-dry-run.
