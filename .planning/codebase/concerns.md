# CONCERNS — trimail

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

## MAJOR-2 — CNR carve-out in ccir.md is dead documentation

**Where.** `ccir.md` § CNR — the **NB** sentence on the Routine bullet cross-references the SIR-2 carve-out, and § SIR-2 itself declares a CARVE-OUT clause lifting VM 2026 sport hits out of Routine. Both are paper-only.

**Symptom.** A BBC Sport Football hit on a VM 2026 political storyline is tagged by the scorer just like any other Routine item — the carve-out text in `ccir.md` is not consulted as code. The clause influences only what an LLM *might* infer if the scorer prompt explicitly asked it to honor carve-outs (it doesn't).

**Why it's MAJOR.** Documentation that promises code behavior but doesn't deliver is a slow-burn drift source. Operators (including future-you) will trust the carve-out and not double-check.

**Fix shape.** Either:
- **(soften)** Replace "This file IS the triage brain" with a humbler phrasing and stop claiming code behavior that the scorer doesn't have.
- **(wire)** Have the scorer pre/post-process: parse ccir.md lines marked with `**NB**` / `**CARVE-OUT**`, expand the keyword allow-list used by `score_item`, and implement the elevate-to-CAT routing.

**Why it's MAJOR, not drift.** Every scored item on BBC Sport Football et al. is wrong-routed today, and the ccir.md text says it isn't.

## DRIFT-1 — `ccir.md` and `score/digest.py:CCIR_ORDER` are manually synced (**partially mitigated 2026-06-23**)

**Guard enhanced.** The runtime assert at `digest.py` module-import now computes a symmetric diff and surfaces specific IDs in the `AssertionError` message (e.g., `in CCIR_ORDER but not in ccir.md: ['FAKE-99']`). Still a manual sync — not auto-derived — but the failure message is now operator-actionable.

**Residual risk.** The guard only fires at import time; adding a new CCIR to `ccir.md` without updating `CCIR_ORDER` will crash `digest.py` with a clear message, but there is no test or pre-commit hook to catch it earlier.

**Remaining fix shape (deferred):**
- Add `tests/test_ccir_sync.py` that asserts `set(CCIR_ORDER ids) == set(ccir.md regex ids)`.
- Or: derive `CCIR_ORDER` from a parse of `ccir.md` (one regex pass on `^- \*\*([A-Z]{3,4}-\d+)\*\*`).

## MINOR-1 — BLUF token cost is unbounded

**Where.** `score/digest.py:write_bluf` runs once per CCIR in `CCIR_ORDER`. `--bluf-top N` (default 12) caps items-per-topic, but the total tokens across all topics is unbounded.

**Symptom.** A high-traffic day (e.g., a major crisis dropping 200 items in OSINT or Hyb/Cyber) blows the model's context window. The longest-topic topic catches the longest stale-fallback (LLM call fails → markdown placeholder for that topic only).

**Fix shape.** Add `--bluf-cap-total` or a similar aggregate guard. Lower `--bluf-top` default from 12 if 11 sections × 12 × ~150 tokens × 4 sections per item is too aggressive. Monitor fail-rate in `data/triage.log` and tune.

## ~~MINOR-2 — Section order: PIR → FFIR → SIR~~ **CLOSED 2026-06-23**

**Fix landed.** `score/digest.py:CCIR_ORDER` re-ordered to PIR-1..6 → SIR-1,2 → FFIR-1..3 (NATO intel hierarchy: operationally driven first, then friendly force).

## MINOR-3 — ⚠️ flagging is empirical, no auto-detection

**Where.** Some feed titles carry a `⚠️` suffix (`ISW ⚠️`, `Ukrainska Pravda ⚠️`). The convention is "this feed returned 403 to a bot UA once". No script proactively probes the OPML.

**Symptom.** Stale ⚠️ on a feed that fixed its CF configuration; missing ⚠️ on a feed that broke.

**Fix shape.** A Curl-based script that bulk-HEADs the URLs in `opml/feeds.opml` and re-marks ⚠️/✅ accordingly. Out of scope for the spike, fine to defer.

## ~~MINOR-4 — `data/digests/*.md` may carry partial / stale LLM output~~ **CLOSED 2026-06-23**

**Fix landed.** `score/digest.py:main()` now writes each digest file to `<name>.tmp` first, then `os.replace()` atomically. On POSIX this is a single-syscall rename; readers never see a partial file.

## MINOR-5 — Bridges write Atom with hand-built XML, no escaping for raw body text

**Where.** `bridge/gmail_to_atom.py`, `bridge/imap_to_atom.py`, `bridge/yt_to_atom.py` — `body_text` is rendered via `html.escape(snippet)`, but the *title* and *author* are escaped via `html.escape(subj)` / `html.escape(frm)`. The same pattern is repeated in 3 places.

**Symptom.** None today — `html.escape` covers `& < > " '` and the bridges consume IMAP-decoded text. Defense-in-depth is still appropriate.

**Fix shape.** Factor `escape(s)` into a tiny shared helper.

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
