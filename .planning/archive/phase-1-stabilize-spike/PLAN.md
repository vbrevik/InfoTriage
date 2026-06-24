# PLAN — Phase 1 · Stabilize the spike

> Phase source: `.planning/ROADMAP.md` Phase 1.
> Goal: Validate every "✅" claim in README, lock the spike so Phase 2 (World Monitor Open-Q1 gate) and Phase 3 (Postgres foundation) can run on trustworthy ground.
> Status: **T1 done** (this commit). T2–T6 ready to execute.

## Done when

- `from score.triage_score import PROFILE` and `from score.fever_triage import fever_key, fever, strip_html` both succeed in a clean import.
- `.env.example` exists at the repo root listing every env var the scripts read (`LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`, `GMAIL_USER`, `GMAIL_APP_PASSWORD`, `GMAIL_QUERY`, `FRESHRSS_FEVER_URL`, `FRESHRSS_FEVER_USER`, `FRESHRSS_FEVER_API_PASSWORD`).
- `bridge/gmail_to_atom.py` produces a valid `data/feeds/gmail.xml` against a real Gmail app password; the file is valid Atom XML and FreshRSS subscribed at `http://feeds/gmail.xml` ingests at least one entry.
- `feedgen` is pinned to a known-good version in `requirements.txt`.
- `tests/test_score_parse.py` runs and asserts the scorer's JSON extraction is robust to: well-formed JSON; JSON inside a code fence (```json … ```); garbage without braces (the fallback `{"ccir": "none", "cnr": "none", "score": 0, "why": "uleselig modell-svar"}` with `bucket="skip"`).
- The README's "✅ wired + tested live" row for the Fever loop is verified at least once end-to-end against a live FreshRSS instance (T7), OR corrected in README to reflect reality.
- Q4 decided (FreshRSS migration: re-provision fresh vs migrate SQLite data).

## Tasks

### T1 · Close the `PROFILE` import gap **[DONE — applied in this commit]**

- **File:** `score/triage_score.py`
- **Change:** Added `PROFILE = CCIR` directly after `CCIR = load_ccir()`, with a comment that names the legacy README references and the trade-off.
- **Why this fix shape:** dropping the dead import in `fever_triage.py` would also require updating README's two PROFILE references and changing the operator's mental model. Adding an alias preserves README consistency with one line and a comment.
- **Verify (run in repo root):**
  ```bash
  python3 -c "import sys; sys.path.insert(0,'score'); from triage_score import PROFILE, CCIR; assert PROFILE == CCIR; print('OK')"
  python3 -c "import sys; sys.path.insert(0,'score'); from fever_triage import fever_key, fever, strip_html, main; print('OK')"
  python3 -m py_compile score/*.py bridge/*.py
  ```
- **Outcome:** all three commands exit 0 in this session.

### T2 · Add `.env.example` **[DONE — 2026-06-23]**

- **File:** `.env.example` at repo root.
- **Content:** all `os.environ` vars across `bridge/` and `score/`: LLM_BASE_URL, LLM_API_KEY, LLM_MODEL, FRESHRSS_FEVER_URL/USER/API_PASSWORD, GMAIL_USER/APP_PASSWORD/QUERY. JSON-array vars (MAILBOXES, YT_CHANNELS) documented as comments with export examples.
- **Verify:** all 9 KEY=VALUE vars present; JSON-array vars documented as comments.

### T3 · Run the Gmail bridge end-to-end

- **File:** `bridge/gmail_to_atom.py` (no code changes; smoke only).
- **Prerequisites:** operator provides `GMAIL_USER` and `GMAIL_APP_PASSWORD` in `.env`. Never commit. Never put real `GMAIL_APP_PASSWORD` anywhere.
- **Steps:**
  ```bash
  # on host (this script can't run inside Docker because of localhost Gmail IMAP)
  python3 bridge/gmail_to_atom.py
  python3 -c "import xml.etree.ElementTree as ET; t = ET.parse('data/feeds/gmail.xml'); ns='{http://www.w3.org/2005/Atom}'; print('entries:', len(t.findall(f'.//{ns}entry')))"
  ```
  Then in FreshRSS: Subscriptions ▸ add `http://feeds/gmail.xml` (assumes `feeds` container is up).
- **Verify:** `len(entries) > 0` AND FreshRSS shows at least one Gmail feed item.
- **Risk:** if a user doesn't have a Gmail account or won't share app password, this task is a "wait" gate. Document the gap in `STATE.md` and continue with T2/T4/T5.

### T4 · Pin `feedgen` in `requirements.txt` **[DONE — 2026-06-23]**

- **File:** `requirements.txt`
- **Change:** `feedgen>=1.0` → `feedgen==1.0.0` (latest stable on PyPI).
- **Verify:** `pip install feedgen==1.0.0` succeeds; `python3 -c "import feedgen"` exits 0.

### T5 · Scorer parse robustness tests **[DONE — 2026-06-23]**

- **File:** `tests/test_score_parse.py`.
- **Approach:** unittest-style (stdlib only, no pytest). Stubs `triage_score.llm` via try/finally swap.
- **5 test cases:**
  - A: well-formed JSON → bucket=read (score >= 7).
  - B: ```json fenced ``` → same parsed dict.
  - C: garbage → fallback dict, bucket=skip.
  - D (bonus): score < 7 + cnr=II → bucket=maybe.
  - E (bonus): cnr=I + low score → bucket=read.
- **Verify:** `python3 tests/test_score_parse.py -v` — all 5 pass.

### T6 · Decide Q4 (FreshRSS migration strategy)

- **Source:** `docs/ARCHITECTURE.md` open question, ROADMAP Phase 1 seam-leads-into-Phase-3.
- **Default recommendation:** **re-provision FreshRSS fresh on Postgres**. Ops rationale:
  - The FreshRSS instance is single-user, single-purpose.
  - SQLite contains FreshRSS-internal state (subscriptions, read/unread, categories) but md/feed entries are re-fetchable from sources.
  - Migrating SQLite → Postgres adds a one-shot risk for marginal historical preservation; subscribing fresh is the lower-risk path.
- **Decision shape:** short note in `STATE.md` and optional ADR-005 in `docs/ARCHITECTURE.md` (no migration code yet — this is just the *decision*).
- **Operator veto:** if operator wants to preserve history, swap to the migrate-SQLite path with a one-liner rationale in the same notes.

### T7 · Runtime smoke against live FreshRSS + oMLX **[DONE — 2026-06-23]**

- **Files:** `score/fever_triage.py` (no changes; smoke only).
- **Command:** `python3 score/fever_triage.py --dry-run --max 5`
- **Result:** Completed with no exceptions. 5 items scored, 2 kept, 3 skipped. Full pipeline verified: Fever API auth → fetch unread → score via local LLM → parse JSON → bucket derivation. README's "✅ wired + tested live" claim re-verified.

### T7.5 · Ingester expansion ⏸ operator pivot, 2026-06-23

> The four tasks below are the operator-pivot re-prioritization. Phases 2–7 are deferred until this expansion has been **used as the actual daily reader** for at least one week. See `.planning/ROADMAP.md` "Ingester-first refactor" note.

### T8 · Multi-mailbox IMAP bridge (operator pivot 2026-06-23)

- **Files:** new `bridge/imap_to_atom.py`.
- **Why:** operator's imminent need = **read Gmail + new sources**. The pre-existing `bridge/gmail_to_atom.py` is Gmail-specific; generalize to multi-mailbox so the same harness serves Outlook / Fastmail / ProtonMail / custom-domain.
- **Provider dispatch:**
  - `provider=gmail` → `X-GM-RAW` (proprietary Gmail search syntax).
  - every other provider → standard IMAP `SEARCH` (RFC 3501).
- **Config:** `MAILBOXES='[…]'` env (JSON), or a sibling `.mailboxes.json`.
- **Verify:** `python3 -m py_compile bridge/imap_to_atom.py` exits 0; runtime smoke needs real IMAP creds (operator-gated).
- **Status:** scaffolded. Runtime-smoke pending.

### T9 · YouTube channel → transcript → Atom bridge (operator pivot 2026-06-23)

- **Files:** new `bridge/yt_to_atom.py`.
- **Why:** operator wants audio/video content in the same SAB loop. Without a transcript, only titles reach the LLM scorer; with one, content scores against CCIR.
- **Pipeline:** per channel `yt-dlp --flat-playlist -I 1:N` → list video ids + titles → audio fetch `yt-dlp -x --audio-format m4a` to tmp → transcription (`mlx_whisper` on Apple Silicon, fall back to `whisper`) → Atom entry with `urn:youtube:{id}` and a transcript excerpt in `<summary>`.
- **Config:** `YT_CHANNELS='[…]'` env JSON, or sibling `.yt_channels.json`.
- **Verify:** `python3 -m py_compile bridge/yt_to_atom.py` exits 0; runtime smoke needs `yt-dlp` + a transcribe backend (operator-gated). With `transcribe: false`, stub entries are written so wiring can be validated without MLX installed.
- **Slug-collision caveat:** per-channel output filename is `data/feeds/youtube-<slug>.xml`. Two channels whose names slug to the same string (e.g., `defense-news` and `defense news`) overwrite each other; disambiguate via the explicit `name` field in `YT_CHANNELS`.
- **Status:** scaffolded. Runtime-smoke pending.

### T10 · Sites via rss-bridge (operator pivot 2026-06-23)

- **Files:** new `bridge/RSS_BRIDGE_NOTES.md` (no code; manual workflow only).
- **Why:** Forsvarets forum, FFI, NUPI, UTSYN, High North News have no native RSS and are exactly the kind of Norwegian defense / policy sources the operator wants. rss-bridge at `:3000` is already running.
- **Approach:** manual via the rss-bridge web UI (XPathBridge / CssSelectorBridge). The OPML already documents which sites need bridges. Optional CLI driver (`bridge/sites_to_feeds.py`) is **deferred** until >5 sites need bridging.
- **Verify:** open `http://localhost:3000` for at least one site (FFI), confirm a `bridge URL` is produced.
- **Status:** notes drafted. Validation on ≥1 site pending operator time.

## Files touched (cumulative)

| File | Change | Status |
|---|---|---|
| `score/triage_score.py` | Add `PROFILE = CCIR` | ✅ done in this commit (T1) |
| `.env.example` | New file | T2 (pending) |
| `requirements.txt` | Pin feedgen; add `mlx-whisper` / `yt-dlp` for T9 when needed | T4 + T9 (pending) |
| `tests/test_score_parse.py` | New file | T5 (pending) |
| `bridge/imap_to_atom.py` | New file (multi-IMAP) | ✅ scaffolded — operator-pivot commit (T8) |
| `bridge/yt_to_atom.py` | New file (YouTube + transcript) | ✅ scaffolded — operator-pivot commit (T9) |
| `bridge/RSS_BRIDGE_NOTES.md` | New file (rss-bridge sites ops notes) | ✅ drafted — operator-pivot commit (T10) |
| `bridge/gmail_to_atom.py` | Keep as-is (single-account Gmail reference path) | T3 keeps proving the path; no migration to T8 needed |
| `.planning/STATE.md` | Reflect T2–T7 + T8–T10 outcomes | incremental |
| `.planning/REQUIREMENTS.md` | Add C-13 multi-IMAP / C-14 sites-via-rssbridge; mark C-9 YouTube as `[SPIKE]` (scaffold landed) | ✅ done in this commit |
| `docs/ARCHITECTURE.md` or `STATE.md` | Short note recording Q4 decision (T6) | T6 (deferred until Phase 3 re-opens) |
| `README.md` | Re-mark "✅ wired + tested live" line if T7 passes | optional post-T7 |

## Files NOT touched

- `ccir.md` (operator-owned)
- `score/triage_score.py` `score_item()` prompt (operator-owned; any change should go through `ccir.md`)
- `bridge/gmail_to_atom.py` (no code change in this phase)
- `docker-compose.yml` (no change in this phase)
- `opml/feeds.opml` (no change in this phase)

## Risks / Notes

- **PROFILE alias is intentional, not a back-fill.** It hides the refactor history. Inline comment explains the alternative (collapse the two and update README); revisit whenever README's PROFILE references are rewritten.
- **T7 is the load-bearing runtime check.** T1 closes the import surface; T7 closes the runtime claim. Don't mark Phase 1 done until T7 passes — or until README is corrected.
- **T3 is operator-gated.** Gmail app passwords live with the user. If the user isn't ready to test, T3 stays open and Phase 1 is "mostly done, T3 deferred."
- **T5 stays stdlib-first.** No pytest install. The project's `requirements.txt` culture is intact.
- **No env values committed.** T2 only enumerates variable names with placeholder values.
- **Q4 is a flag, not a build.** T6 records a decision; the actual migration is Phase 3's work.

## Verification at close

```bash
# T1 (done)
python3 -c "import sys; sys.path.insert(0,'score'); from triage_score import PROFILE; assert PROFILE"

# T2 (after)
diff <(grep -E '^[A-Z_]+=' .env.example | cut -d= -f1 | sort) \
     <(grep -rhE 'os.environ(|\.get)' bridge/ score/ | grep -oE '"[A-Z_]+[A-Z0-9_]*"' | sort -u)

# T4 (after)
python3 -c "import feedgen; print(feedgen.__version__)"

# T5 (after)
python3 tests/test_score_parse.py

# T7 (after, the gate)
python3 score/fever_triage.py --dry-run --max 5
```

## Cross-phase coordination

- **Operator pivot 2026-06-23:** Phases 2–7 are deferred. This plan should be runnable without depending on World Monitor / Postgres / embeddings / RAG / SOCMINT / COP / push work.
- **Phase 1 done ≠ Phase 3 starts.** The ingest loop must prove operator value before any deferred architecture moves.
- **Within Phase 1:** T1 (PROFILE alias), T2 (`.env.example`), T4 (pin `feedgen`), T5 (parse-robustness tests), T7 (runtime smoke) are SEQ-safe; T3 (Gmail end-to-end) and T8/T9/T10 (new bridges) are **all operator-gated** (need real creds or installs) and can land in any order.
- **Independence:** T8 (multi-IMAP) is independent of Gmail T3 — T3 keeps proving the Gmail-specific path works; T8 generalizes. Don't conflate them.
- **Adjacent to Phase 0 already-running rss-bridge usage:** T10's manual workflow is essentially "the rss-bridge path you already have, with sites enumerated."

## Out of scope (deferred)

- Replacing `verdicts.jsonl` with Postgres (Phase 3)
- Embeddings / semantic dedup (Phase 4)
- Embedding model selection (Phase 4 — Q5)
- World Monitor spike (Phase 2, parallel-safe)
- Any change to the CCIR taxonomy itself (operator decision only)
- Cloud LLM (ADR-004 reject)
- X / Twitter (constraints)
- TAK/CloudTAK in early phases (Phase 3+ doctrinal)
- ACLED via local LLM without a paid public-sector license (Q3)
</content>
</invoke>