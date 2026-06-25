<!-- refreshed: 2026-06-24 -->
# Architecture

**Analysis Date:** 2026-06-24

## System Overview

InfoTriage is a **local OSINT intelligence hub** — a free, fully-local info-triage system that ingests multiple content sources (RSS, email, YouTube), applies LLM-driven CCIR-based scoring, and generates structured intelligence briefs. All processing runs on a local Mac (qwen3.6 LLM via oMLX); no cloud LLM calls in the runtime.

```text
┌────────────────────────────────────────────────────────────────────┐
│                    INGEST LAYER (Content Sources)                   │
├──────────────────┬────────────────────┬────────────────────────────┤
│  Gmail Bridge    │  IMAP Bridge       │  YouTube Bridge            │
│ `bridge/gmail_   │ `bridge/imap_      │ `bridge/yt_to_atom.py`    │
│  to_atom.py`     │  to_atom.py`       │ (stub: no transcription)   │
└──────────┬───────┴────────┬───────────┴──────────────┬─────────────┘
           │                │                          │
           ▼                ▼                          ▼
┌────────────────────────────────────────────────────────────────────┐
│            FEED LAYER (Atom File Generation)                        │
│  `data/feeds/gmail.xml` | `data/feeds/imap*.xml` | `youtube-*.xml` │
└────────────┬─────────────────────────────────────────────────────┬─┘
             │                                                       │
             ▼                                                       ▼
┌─────────────────────────────────────────────────────────┐  (Docker)
│          FreshRSS Hub (`data/freshrss/`, :8088)         │
│    RSS Reader + Ingestion + Fever API + SQLite Store    │
│  `http://feeds/` mounts Atom files as local feed URLs   │
└──────────────┬──────────────────────────────────────────┘
               │ Fever API (unread item IDs + content)
               │
               ▼
┌─────────────────────────────────────────────────────────┐  (Local Mac)
│              SCORING LAYER (LLM Triage)                 │
│  `score/triage_score.py` → qwen3.6 via oMLX :8000/v1   │
│   (CCIR-driven, multi-field enrichment: PIR/FFIR/SIR,  │
│    CNR bucket, PMESII, TESSOC, score 0–10, why)        │
└──────────────┬──────────────────────────────────────────┘
               │ Scored verdicts (JSON)
               │
               ▼
┌──────────────────────────────────────────┬──────────────┐
│  STORAGE LAYER (Verdict Persistence)     │ Fever API    │
│  `data/verdicts.jsonl` (append-only)     │ (mark read)  │
└──────────────┬─────────────────────────┬─┘              │
               │                         │                │
               ▼                         ▼                ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    DIGEST / REPORTING LAYER                           │
│  `score/digest.py`: cluster | brief | list | bluf modes              │
│  (Keyword dedup, CCIR sectioning, LLM synthesis, HTML markup)        │
└──────────────────────┬─────────────────────────────────────────────┬─┘
                       │                                             │
       Output: digest modes (cluster.md, brief.md, list.md, bluf.md)  │
                                                                      │
                  FreshRSS Web UI (:8088) ◀── mark items read/unread
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| **Gmail Bridge** | Connect to Gmail IMAP (read-only), fetch messages matching `GMAIL_QUERY`, convert to Atom feed | `bridge/gmail_to_atom.py` |
| **IMAP Bridge** | Multi-IMAP ingestion (Gmail, Outlook, Fastmail, etc.), per-account dispatch | `bridge/imap_to_atom.py` |
| **YouTube Bridge** | YouTube channel subscriptions → Atom; optional audio transcription (stub mode: no-op) | `bridge/yt_to_atom.py` |
| **Feeds Server** | Serve Atom XML files from `data/feeds/` to FreshRSS via Docker network alias `http://feeds/` | Docker `feeds` container |
| **FreshRSS Hub** | Ingest RSS/Atom feeds, maintain reader UI, store articles in SQLite, expose Fever API for programmatic access | Docker `freshrss` container |
| **Scorer** | Fetch unread items from FreshRSS Fever API, score each against CCIR taxonomy using local LLM, enrich with PMESII/TESSOC, bucket into read/maybe/skip | `score/triage_score.py` |
| **Fever Triage Loop** | Invoke scorer on unread, mark low-score items read, print keeper digest to stdout | `score/fever_triage.py` |
| **Digest Generator** | Read verdicts from `verdicts.jsonl` + live FreshRSS Fever state, cluster/section/synthesize, write four digest modes | `score/digest.py` |
| **Taxonomy (CCIR)** | Canonical intelligence requirements; edited to tune triage behavior; inlined into scorer prompt | `ccir.md` |

## Pattern Overview

**Overall:** Event-driven pipeline with **behavioral configuration** (taxonomy-driven).

**Key Characteristics:**
- **No cloud LLM**: All scoring uses local qwen3.6 (oMLX/Ollama).
- **Taxonomy-first design**: Editing `ccir.md` changes triage without code changes (because the full file is inlined into the scorer prompt).
- **Loosely coupled layers**: Bridges → Atom files → FreshRSS → Fever API → Scorer → Verdicts → Digest.
- **Persistent state in verdicts.jsonl**: All scored items written (append-only); digest generators filter/view from here.
- **Sync guards**: `score/digest.py` validates `CCIR_ORDER` matches `ccir.md` at import time (survives `python3 -O`).

## Layers

**Ingest Layer:**
- Purpose: Convert heterogeneous sources (email, YouTube, RSS) into a uniform Atom format.
- Location: `bridge/` (three converters: `gmail_to_atom.py`, `imap_to_atom.py`, `yt_to_atom.py`).
- Contains: Entry points for external data pull; IMAP/Gmail auth; YouTube metadata; Atom XML generation.
- Depends on: IMAP libraries (stdlib), `feedgen` (for cleaner Atom XML generation), external IMAP/YouTube servers.
- Used by: Feeds server (reads Atom files from disk); FreshRSS (subscribes to `http://feeds/<name>.xml`).

**Feed Server + FreshRSS:**
- Purpose: Central hub for RSS ingestion, article storage, and reader UI.
- Location: `data/freshrss/` (state) + Docker container (runtime).
- Contains: FreshRSS installation, SQLite database, Fever API plugin, web UI.
- Depends on: Docker, `data/feeds/` mounted at `http://feeds/`.
- Used by: Scorer (fetches unread via Fever API); end user (web UI at :8088).

**Scoring Layer:**
- Purpose: Apply LLM-driven triage against CCIR requirements; enrich each item with tactical metadata.
- Location: `score/triage_score.py` (scorer entry point), plus `score/digest.py` (report generator).
- Contains: Prompt templates (CCIR inlined from ccir.md), LLM integration (oMLX/Ollama), JSON parsing, bucket assignment.
- Depends on: `ccir.md` (taxonomy), local LLM endpoint (Spark vLLM `192.168.10.2:8000/v1` (primary) or oMLX `:8000/v1` (fallback)).
- Used by: `score/fever_triage.py` (mark-read loop), `score/digest.py` (batch scoring for reports).

**Verdict Store:**
- Purpose: Persist all scored items in append-only format; immutable record for replay/audit.
- Location: `data/verdicts.jsonl` (one JSON object per line).
- Contains: All verdicts ever written: original item + LLM enrichment (CCIR, CNR, PMESII, TESSOC, score, bucket, why).
- Depends on: Scorer output.
- Used by: Digest generators (read, filter, cluster, synthesize); external audit/replay tools.

**Digest / Reporting Layer:**
- Purpose: Generate four distinct narrative/tabular views of the verdict stream.
- Location: `score/digest.py`, output to `data/digests/`.
- Contains: Four render functions (`write_cluster`, `write_brief`, `write_bluf`, `write_list`), window selection, keyword clustering, LLM synthesis.
- Depends on: Verdict store, live FreshRSS Fever state (fetch unread window), local LLM for BLUF synthesis.
- Used by: Human reader (reads .md files); potentially external systems (webhook relay).

## Data Flow

### Primary Request Path (FreshRSS Unread → Digest)

1. **Fetch unread window** — `score/digest.py:fetch_window()` calls Fever API; get unread IDs (newest-first), batch-fetch by ID (50 per request), filter by time cutoff (default: yesterday 16:00 Oslo). (`score/digest.py:68–110`)
2. **Score each item** — Call `score_item()` for each fetched article; LLM inlines CCIR prompt + item (title/source/summary). Scorer returns JSON: `{ccir, cnr, pmesii, tessoc, score, bucket, why}`. (`score/digest.py:102–109`)
3. **Persist to verdicts.jsonl** — Write each verdict (original item + enrichment) to store for audit. (`score/digest.py:112–116`)
4. **Choose output mode** — CLI `--mode cluster|brief|bluf|list` selects which render function to use. (`score/digest.py:346–347`)
5. **Cluster (dedup) or synthesize** — Either keyword-overlap cluster (cluster/brief modes), select strict high-score items (list mode), or feed top-N per CCIR to LLM for BLUF synthesis. (`score/digest.py:121–305`)
6. **Write .md output** — Write to `data/digests/{cluster,brief,bluf,list}.md` via atomic temp → rename. (`score/digest.py:354–360`)

### Mark-as-Read Loop (Fever Triage)

1. **Get unread IDs** — `score/fever_triage.py` calls Fever API `unread_item_ids`. (`score/fever_triage.py:53–57`)
2. **Batch-fetch by ID** — Fever capped at 50 per request; fetch item bodies. (`score/fever_triage.py:60–64`)
3. **Score each item** — Call `score_item(title, source, summary[:500])`. Return bucket (skip/maybe/read). (`score/fever_triage.py:69–83`)
4. **Mark skip items read** — If `score ≤ skip_threshold` (default 3) or `bucket == "skip"`, call Fever API `mark=item as read`. (`score/fever_triage.py:75–78`)
5. **Print keeper digest** — Display kept items (score > threshold) to stdout; summary of marked items. (`score/fever_triage.py:85–92`)

### Email Bridge → FreshRSS Subscription

1. **Run scheduler task** — `python3 bridge/gmail_to_atom.py` (e.g., via cron).
2. **Authenticate IMAP** — Connect to `imap.gmail.com` with `GMAIL_USER` + `GMAIL_APP_PASSWORD`.
3. **Search by Gmail X-GM-RAW query** — E.g., `newer_than:7d` or `label:newsletters`. (`bridge/gmail_to_atom.py:36–38`)
4. **Fetch + decode headers** — Extract subject, from, snippet (body first 500 chars). (`bridge/gmail_to_atom.py:40–77`)
5. **Generate Atom feed** — Use `feedgen` library to write well-formed `data/feeds/gmail.xml`. (`bridge/gmail_to_atom.py:80+` — incomplete in snippet)
6. **FreshRSS subscribes** — Web UI → Subscriptions ▸ add feed URL `http://feeds/gmail.xml`.
7. **Fever API fetches** — `score/digest.py` and `score/fever_triage.py` see Gmail items via Fever unread query.

**State Management:**
- **FreshRSS SQLite**: Articles + feeds + read/unread state. Modified by FreshRSS UI and Fever API calls from scorer.
- **verdicts.jsonl**: Append-only log of all scored verdicts; used to replay/audit; survives FreshRSS wipes.
- **digest .md files**: Human-readable reports; ephemeral (regenerated each run; not stored in git).
- **.env**: Environment config for LLM endpoint, Gmail, IMAP creds, FreshRSS Fever auth.

## Key Abstractions

**CCIR (Commander's Critical Information Requirements):**
- Purpose: Defines "what matters" — the schema that drives triage decisions. Edited by the operator to tune behavior.
- Examples: `PIR-1` (Russia/Ukraine war), `PIR-2` (Arctic/Nordområdene), `FFIR-3` (personal tech stack), `SIR-2` (World Cup 2026 security angle).
- Pattern: Flat taxonomy list in `ccir.md`; inlined into `score_item()` prompt as a reference table + disambiguation guide. No code hardcoding; taxonomy is data.

**Verdict (enriched item):**
- Purpose: Original item (title, source, summary, URL) + LLM-assigned metadata (CCIR, CNR, PMESII, TESSOC, score, bucket, why).
- Examples: `{"title": "...", "source": "NRK", "summary": "...", "ccir": "PIR-1", "cnr": "II", "pmesii": "Military", "tessoc": "Equipment", "score": 8, "bucket": "read", "why": "Frontlinjer-update"}`
- Pattern: JSON object; persisted line-by-line in `verdicts.jsonl`; passed between scoring and digest layers.

**Bucket (triage disposition):**
- Purpose: Classify an item into one of three actionable states.
- Values: `read` (CCIR match + CNR-I or score ≥ 7 → keep unread for SAB), `maybe` (CCIR match but CNR-II and score < 7), `skip` (no CCIR match → mark read, hide from human).
- Examples: Derived from `(ccir == "none") → skip; (ccir != "none" && cnr == "I") → read; else → maybe` (`score/triage_score.py:141–144`).

**Digest Mode (output narrative):**
- Purpose: Select which view of the verdict stream is most useful for consumption.
- **cluster**: Keyword-overlap deduped view; same story across outlets collapsed to one entry + source count.
- **brief**: Section-per-CCIR SAB (Situation Assessment Brief) format; quick-read, ~10 min.
- **list**: Strict high-score only (score ≥ 8); minimal, action-oriented.
- **bluf**: LLM-synthesized Bottom Line Up Front per CCIR; 2–3 sentence summaries with numbered citations + contradiction handling.

## Entry Points

**Ingest:**
- Location: `bridge/gmail_to_atom.py`, `bridge/imap_to_atom.py`, `bridge/yt_to_atom.py`
- Triggers: Scheduled task (cron/launchd) or manual invocation.
- Responsibilities: Read external source, convert to Atom, write `data/feeds/<name>.xml`.

**Interactive Scorer:**
- Location: `score/triage_score.py`
- Triggers: Manual invocation with `--sample` or stdin pipe or `--file`.
- Responsibilities: Load items from JSON, score each via LLM, output JSON or markdown.

**Fever Triage Loop:**
- Location: `score/fever_triage.py`
- Triggers: Scheduled task (cron, typically :35 every hour) or manual with `--dry-run`.
- Responsibilities: Fetch unread from FreshRSS, score, mark skip items read, print keeper digest.

**Digest Generator:**
- Location: `score/digest.py`
- Triggers: Scheduled task or manual with `--mode {cluster|brief|bluf|list}`.
- Responsibilities: Fetch unread window from FreshRSS, score, cluster/synthesize, write .md files to `data/digests/`.

## Architectural Constraints

- **Threading:** Single-threaded event loop. All calls to oMLX/FreshRSS are synchronous (urllib). Batch operations iterate sequentially.
- **Global state:** CCIR taxonomy loaded once at module import (ccir.md via `load_ccir()` in `score/triage_score.py:21–27`); immutable thereafter. Prompt is expensive to regenerate; cached. Verdict store is append-only (safe for concurrent reads, writes via separate processes OK if atomicity is guaranteed by filesystem).
- **Circular imports:** None known; bridges are standalone, scorer is a library (`score_item()` reused by digest), digest calls scorer as a function.
- **LLM endpoint**: Hardcoded to oMLX `:8000/v1` (default) or Ollama `:11434/v1` (env override). Single endpoint; no failover. Timeout = 120 seconds.
- **FreshRSS Fever API**: Assumes Fever plugin is enabled, auth valid. No retry logic on `AUTHENTICATIONFAILED`.
- **File I/O**: Atomic rename used for digest output (temp → final); verdicts.jsonl is append-only (no truncation).

## Anti-Patterns

### Prompt Drift (CCIR ↔ Scorer)

**What happens:** `ccir.md` and `score/triage_score.py:score_item()` prompt diverge. A new CCIR is added to `ccir.md`, but the scorer prompt's tier quick-reference and JSON enum are not updated. Scorer emits old enum values for the new CCIR, triggering JSON parse errors or silent fallback to `ccir: "none"`.

**Why it's wrong:** Silent bucket misassignment. Items matching the new CCIR are marked skip (skipped by the mark-as-read loop) instead of kept. User sees a broken triage.

**Do this instead:** Edit both `ccir.md` AND `score/triage_score.py:score_item()` in the same commit. The prompt must enumerate all tier codes and include a worked example for each new tier. (`score/triage_score.py:54–128` is the canonical prompt template.)

### CCIR_ORDER ↔ ccir.md Drift

**What happens:** `score/digest.py:CCIR_ORDER` list does not match the count / order of CCIR bullets in `ccir.md`. Digest silently drops new tiers or renders them in the wrong order.

**Why it's wrong:** Incomplete section coverage in digest output. A new CCIR tier exists but the digest's per-CCIR sections silently skip it (no error, just an empty section).

**Do this instead:** Sync guard at module import enforces the invariant. Edit both together. The guard is in `score/digest.py:45–55` and raises `AssertionError` if counts/IDs diverge.

### Fever API Auth Silent Failure

**What happens:** FRESHRSS_FEVER_USER, _API_PASSWORD, or Fever plugin is misconfigured. Fever calls return `{"auth": 0}` (auth failed). Code checks `if fever(…)["auth"] != 1:` and raises `SystemExit` with a helpful message, but the message may not match the actual problem (e.g., plugin disabled).

**Why it's wrong:** User runs `fever_triage.py` and gets an exit code 1 with a message about auth, but the real issue is FreshRSS was just restarted and needs a few seconds to initialize. No retry, no delay, hard stop.

**Do this instead:** Fetch unread twice with a 5-second delay if auth fails; then raise if still failing. Or, offer a `--retry` flag for cron operations.

### IMAP Credentials in `.mailboxes.json`

**What happens:** Developer stores plaintext IMAP passwords in `.mailboxes.json` (gitignored, but still a file on disk). If the machine is compromised or the file is backed up, credentials leak.

**Why it's wrong:** Credentials at rest on disk; no encryption.

**Do this instead:** Use OAuth2 + refresh tokens (Gmail), or fetch passwords from a secure store (macOS Keychain, `security find-internet-password`, etc.). For manual entry, prompt `getpass()` instead of storing.

## Error Handling

**Strategy:** Fail fast with clear messages; never silently drop data.

**Patterns:**
- **IMAP connection**: `imaplib.IMAP4_SSL()` raises `socket.error` if host unreachable; caught and re-raised as `SystemExit`.
- **LLM prompt**: `urllib.error.URLError` if oMLX is down; caught, error logged to stderr, exception re-raised.
- **JSON parse**: If LLM returns unparseable JSON, `json.JSONDecodeError` caught; fallback to `{"ccir": "none", …, "why": "uleselig modell-svar"}` (scored as skip).
- **Fever API**: If auth fails, raise `SystemExit`. If item fetch fails, skip the item and continue (log to stderr).
- **Digest LLM call** (BLUF synthesis): If LLM fails, log exception to stderr (never echo auth headers into .md), write placeholder `_(Kunne ikke generere BLUF — sjekk logg)_` to digest, continue to next section.

## Cross-Cutting Concerns

**Logging:** All scripts use `print(..., file=sys.stderr, flush=True)` for progress and debug; stdout reserved for the primary output (digest markdown, JSON, keeper list). No centralized logging framework; timestamps are human-readable (`datetime.strftime`).

**Validation:** Env vars loaded via `load_dotenv()` (non-strict; missing vars return `None` or use defaults). CCIR tier enums validated by LLM prompt (scorer rejects invalid JSON); digest validates CCIR_ORDER sync at import.

**Authentication:** 
- FreshRSS Fever API: MD5 hash of `FRESHRSS_FEVER_USER:FRESHRSS_FEVER_API_PASSWORD` sent per request.
- Gmail/IMAP: App-password (Google) or plaintext password (others); stored in `.env` (plaintext, unencrypted).
- oMLX/Ollama: Bearer token in `Authorization` header (key from env).

---

*Architecture analysis: 2026-06-24*
