# CONVENTIONS — trimail

Source of truth: code-level patterns + ccir.md headings + opml/feeds.opml.
Generated: 2026-06-23.

## Naming

- **CCIR tier prefixes.** PIR-* (external threats), FFIR-* (home/own forces), SIR-* (time-bounded specific). Numbers 1..N per tier.
- **CNR levels.** CAT I 🚩 (varsle straks), CAT II 📋 (dagsbrief), Routine (utelat).
- **Bucket labels.** `read` / `maybe` / `skip` — internal to the scorer. Visualised in digests as 🔥 / 🤔 / 🗑️.
- **Writer modes.** `cluster` / `brief` / `list` / `bluf` — passed via `--mode` to `score/digest.py`. `cluster` is the default; digests ship to `data/digests/`.
- **Atom output names.** `data/feeds/<name>.xml` (IMAP) or `data/feeds/youtube-<slug>.xml` (YouTube). The single-account Gmail bridge writes **`gmail.xml`** (collision risk documented in `bridge/imap_to_atom.py:54-58`).
- **Channel slug.** lowercased / non-alnum → `-`, trailing 32 chars. Disambiguate via explicit `name:` in the channel config when collision risk exists.

## OPML style (`opml/feeds.opml`)

- 4-space indent for top-level `<outline text="…" title="…">`.
- 6-space indent for child `<outline type="rss" …/>`.
- Every `<outline type="rss">` carries both `xmlUrl` and `htmlUrl`. `text` and `title` are kept in sync.
- Em-dash `—` and middle-dot `·` are UTF-8 — OK.
- `&` in URLs/titles escaped as `&amp;` to keep XML well-formedness.
- `⚠️` suffix on a title means "feeds 403 to bot UAs". Empirical, not speculative.
- Bottom-of-file `<!-- ===== NO native RSS (404) — build with rss-bridge (CSS-selector scrape) ===== -->` lists the sites that have no native RSS — pipeline reminder, not data.

## Python code style

- `#!/usr/bin/env python3` shebang on every script.
- Module docstring with **usage** in the first block.
- Stdlib-maximum; resist new deps unless feedgen's job is genuinely outside stdlib's reach.
- Functions named after their role: `score_item`, `fever`, `strip_html`, `gmail_search`, `write_bluf`, `fetch_window`.
- Module-level constants `UPPER_SNAKE` (`CCIR_ORDER`, `STOP`, `STORE`, `OUT`, `OSLO`).
- `load_dotenv(path)` helper duplicated across modules for self-containment — keeps each script runnable standalone.

## Bilingual policy

- **Code identifiers** — English.
- **User-facing prose** — Norwegian. Headings are bilingual (`## PIR — Priority Intelligence Requirements`).
- **Prompts to the LLM** — bilingual segment: instructions in English; example outputs in Norwegian.
- **OPML "text=" labels** — Norwegian (matches the user-facing UI in FreshRSS, which a Norwegian operator will see).
- **ccir.md entries** — bilingual heading + Norwegian bulleted description.

## Secrets hygiene

- **Plaintext in `.env`** (gitignored). Used for LLM API key (oMLX/Ollama; not a real secret in the operator's threat model), Gmail app password, Fever creds.
- **App password shape:** 16 chars, lowercase letters + digits only, no spaces. Validation done length-and-shape-only — never printed.
- **`.mailboxes.json`** (gitignored). Plaintext IMAP credentials for non-Gmail accounts. Operator-side, file-based.
- **`.yt_channels.json`** (gitignored). Channel URLs only — **do not** add a YouTube account.
- **Never echo credential characters in error text.** Probes redact via regex (`[a-z]{16}` → `[REDACTED]`) and length-only diagnostics (`len=16`, `isalnum+islower=True/False`).
- **Reuse the same `load_dotenv()` helper across all modules** so secret-handling behavior is consistent.

## Output paths

- `data/feeds/<name>.xml` — bridge-produced Atom feeds.
- `data/digests/<mode>.md` — digest writer output. One md file per mode.
- `data/verdicts.jsonl` — append-only scorer history (legacy; future: Postgres).
- Atom output is always hand-written by the bridges (XML strings assembled in `parts = [...]`). `feedgen` is available but not yet used in production.

## Failure handling

- **Stderr = diagnostic. Stdout = clean output.** Cron'd scripts should be parseable.
- **Never echo exception text into user-facing markdown.** urllib error text can carry URLs with auth headers / env-var components. Pattern: `print(..., file=sys.stderr, flush=True)` for full detail; emit a stinging Norwegian placeholder to markdown.
- **Length-only credential diagnostics.** `print("len=", len(value), "shape_ok=", bool(value.isalnum() and value.islower()))` — never `print(value)`.
- **`--dry-run` first.** Where a side-effect could change persistent state (e.g., marking items read in FreshRSS), default to read-only.

## CCIR routing responsibility

- `ccir.md` is the **document of record**. Read-only to the runtime; the runtime consults it via the scorer's prompt context.
- `score/digest.py:CCIR_ORDER` is the **render-engine** contract — section order in `brief.md` / `cluster.md` / `bluf.md`. **Manually synced** with ccir.md.
- The scorer's prompt ties them together — see CONCERNS.md for the specific drift points.

## Versioning

- Single-version-in-a-day spike. No semver. The project's "version" is its date-stamped status (header comment in `opml/feeds.opml` reads `verified 2026-06-23`).
- That's the only datestamp in the codebase — no `__version__` constants anywhere.

## Style for digests

- One markdown file per writer mode.
- Top heading carries the writer name + the period (cutoff → now Oslo).
- Each `## SECTION` heading is `CCIR_ID · Norwegian title`.
- Items use `- **[{score}] {title}**  · {source} · {ccir}` line shape, then a `- {why} — [les]({url})` continuation.
- Emojis are *intentional* — they're part of CNR/CNR-elevated visibility, not decoration.
