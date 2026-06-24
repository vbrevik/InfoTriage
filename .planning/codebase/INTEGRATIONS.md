# INTEGRATIONS — InfoTriage

Source of truth: code-level env reads + bridge entry points.
Generated: 2026-06-23.

## LLM (local)

**Endpoint.** OpenAI-compatible `chat/completions` on the local qwen3.6 server.
- Primary: `http://127.0.0.1:8000/v1` (oMLX on Mac).
- Fallback: `http://127.0.0.1:11434/v1` (Ollama).
- Both reply `/v1/models` for inventory and `/v1/chat/completions` for inference.

**Auth.** Bearer token from env.
- `LLM_BASE_URL` (default `http://127.0.0.1:8000/v1`).
- `LLM_API_KEY` (default `omlx`).
- `LLM_MODEL` (default `qwen36-ud-4bit`).

**Code anchor.** `score/triage_score.py:50` — `llm(messages, max_tokens=400)`. Used by `score_item` for triage and by `write_bluf` (in `score/digest.py`) for per-CCIR synthesis.

**Failure handling.** All call sites wrap with try/except; never echo exception text into user-facing markdown (urllib errors can carry URLs with env vars — like `GMAIL_APP_PASSWORD` if it ever leaks into a URL). Stderr gets full detail; markdown gets a stingy Norwegian placeholder. Examples:
- `triage_score.py` — JSON parse exception → fallback verdict `{ccir:none, cnr:none, score:0}`.
- `digest.py:write_bluf` — any exception → `_(Kunne ikke generere BLUF — sjekk logg for detaljer)_`.

## Gmail (single-account bridge)

**Service.** Google Mail IMAP `imap.gmail.com:993` (SSL).
**Auth.** Google **app password** (16 chars, lowercase-alnum only). Stored as `GMAIL_APP_PASSWORD` in `.env`. App-password requires 2-Step Verification to be ON on the account.
**Query.** `GMAIL_QUERY` env var (default `newer_than:7d`). Sent as Gmail's proprietary `X-GM-RAW` IMAP extension key.
**Code anchor.** `bridge/gmail_to_atom.py:1–91`. Single account, INBOX only.
**Output.** `data/feeds/gmail.xml` (ATOM 1.0). Served at `http://feeds/gmail.xml` to FreshRSS via the `feeds` compose container.
**Posture.** Read-only — `imap.select("INBOX", readonly=True)`. No STORE / EXPUNGE calls anywhere.

**Collision warning.** If `name="gmail"` is also given to `imap_to_atom.py`, both scripts will write the same file. Use `name="gmail-multi"` for IMAP Gmail or run only one bridge per Gmail account.

## Multi-IMAP bridge

**Service.** Any IMAP mailbox, including Gmail (with `X-GM-RAW`), Outlook, Fastmail, ProtonMail, custom-domain.
**Auth.** Per-account password — app password where applicable.
**Config.** `MAILBOXES` JSON array as a shell env, **OR** `.mailboxes.json` sibling file (gitignored, plaintext). The `.env` loader skips `MAILBOXES=` because the JSON starts with `[` and is not a `KEY=VALUE` line.
**Per-entry shape.**
```json
{"name":"...","host":"...","user":"...","password":"...","query":"...","provider":"gmail|imap"}
```
**Provider dispatch.** `bridge/imap_to_atom.py:71-77` — `gmail.com` / `googlemail.com` → `X-GM-RAW`; everything else → standard `IMAP SEARCH` (RFC 3501).
**Output.** One Atom file per mailbox: `data/feeds/<name>.xml`.
**Posture.** Read-only. Single-port IMAP4_SSL + `readonly=True`. If all accounts fail → exit 1; if some fail → exit 0 with stderr summary.

## YouTube → Atom with transcripts

**Service.** YouTube public-channel pages via `yt-dlp`. **No YouTube credentials.** Treated as anonymous public feed pull.
**Per-channel pipeline.**
1. `yt-dlp --flat-playlist --print "%(id)s|||%(title)s"` (no download) → list of (video_id, title).
2. Per video: `yt-dlp -x --audio-format m4a` → `tmp/<id>.m4a`.
3. Transcribe with first available runner: `mlx_whisper` (Apple Silicon primary) → `whisper` (fallback).
4. Emit Atom entry `(id, title, transcript[:1000])`.

**Transcription off.** Set `"transcribe": false` per channel — wires the pipeline with stub summary so MLX/whisper need not be installed for an end-to-end smoke.
**Config.** `YT_CHANNELS` JSON env or `.yt_channels.json` (gitignored). Loader same shape as `MAILBOXES`.
**Slug.** `data/feeds/youtube-<slug>.xml` where slug = lowercase / non-alnum → `-`, last 32 chars. Two names that slug-collide need explicit `name:` field.
**Dependencies (operator-side).** `yt-dlp`; `mlx_whisper` *or* `whisper`. **Do not add a YouTube account.**

## FreshRSS

**Service.** `freshrss/freshrss:latest`. Single-user self-hosted reader + aggregator.
**Endpoint (container).** `http://localhost:8088`.
**Fever API.** Used by the scorer to pull unread + mark items read.
- `FRESHRSS_FEVER_URL` (e.g. `http://localhost:8088/api/fever.php`).
- `FRESHRSS_FEVER_USER`.
- `FRESHRSS_FEVER_API_PASSWORD`. The client computes `md5(user:password)` as the api_key.
**Code anchors.**
- `score/fever_triage.py:13` — `fever_key()`.
- `score/fever_triage.py:18` — `fever(api_key, query, **params)`.
- `score/digest.py:38` — `fetch_window(cutoff_epoch, hardcap)` (paginates items by `max_id`).
**Cron cadence.** `23,53` minutes past the hour (in compose env) — gentler on rate-limited sources. `score/fever_triage.py` runs at `:35` per README's example cron (after the two refresh stamps).
**Composer rest.** `:35` per InfoTriage cron, after FreshRSS `:23 / :53` refresh windows.

## rss-bridge

**Service.** `rssbridge/rss-bridge:latest`.
**Endpoint (container).** `http://localhost:3000`.
**Used for.** Sites without native RSS — Forsvarets forum, FFI, NUPI, UTSYN, High North News (per README). Bridge protocol: CSS-selector or XPathBridge configured in the rss-bridge UI. The OPML file lists these sites as comments at the end (`<!-- ===== NO native RSS (404) — build with rss-bridge (CSS-selector scrape) ===== -->`) since InfoTriage cannot auto-bridge them.

## OPML ingest

**File.** `opml/feeds.opml` — 61 feeds across 10 top-level outlines (as of post-2026-06-23): Norske aviser, Offentlig Norge, Norsk forsvar & sikkerhet, Forsvar & geopolitikk (intl), OSINT & investigations (intl), Verdensnyheter, Datakilder, Medium, **Midtøsten & US-Iran (SIR-1)**, **Sport — VM 2026 (SIR-2)**. Verified URL-bulk-OK 2026-06-23.
**Flagging convention.** Feeds known to 403 to bot UAs (Cloudflare) carry a `⚠️` suffix on the title — ISW, Lawfare, Breaking Defense, National Interest, Ukrainska Pravda (HTML-only at the canonical URL — placeholder).
**Import.** FreshRSS ▸ Subscription management ▸ Import ▸ upload.

## GDELT (a single query-feed in OPML)

**Service.** `https://api.gdeltproject.org/api/v2/doc/doc?query=...&mode=ArtList&format=rss`.
**Rate limit.** 1 req / 5 s — strictly enforced. The compose cron `23,53` brings global cadence to ≤2 hits/hour, well under the limit.
**Per-feed TTL.** The OPML comment in `opml/feeds.opml` (Datakilder outline) tells the operator to set a long per-feed TTL in FreshRSS.

## World Monitor (planned, Phase 1)

**Service.** `koala73/worldmonitor`, AGPL-3.0, Docker/Tauri self-host.
**Why we don't ship it yet.** The Open-Q1 gate (RESEARCH-REPORT.md) — does Ollama path cover CCIR scoring + SAB briefing, or only classification? Must spike and verify before adopting. Cost-free architecture but operationally not free.
