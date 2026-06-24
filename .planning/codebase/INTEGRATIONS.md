# External Integrations

**Analysis Date:** 2026-06-24

## APIs & External Services

**Email (IMAP):**
- Gmail IMAP (`imap.gmail.com:993`) - Read-only newsletter/message ingestion
  - SDK/Client: Python `imaplib` (stdlib)
  - Auth: Google app password (not full Gmail API)
  - Used by: `bridge/gmail_to_atom.py`, `bridge/imap_to_atom.py`
  - Query language: Gmail X-GM-RAW (native Gmail search syntax)
  - Output: Atom feed written to `data/feeds/gmail.xml` or `data/feeds/gmail-multi.xml`

- Multi-Account IMAP (`imap_to_atom.py`)
  - Providers: Gmail, Outlook, Fastmail, ProtonMail, custom-domain IMAP
  - Auth: Plaintext IMAP credentials in `.mailboxes.json` (gitignored)
  - Config: `MAILBOXES` env var (JSON array) or `.mailboxes.json` file
  - Output: `data/feeds/gmail-multi.xml` (one runner, per-account dispatch)

**LLM / AI Scoring:**
- OpenAI-compatible API endpoint (local)
  - Default: oMLX on `http://127.0.0.1:8000/v1`
  - Alternative: Ollama on `http://127.0.0.1:11434/v1`
  - Auth: Bearer token in header (`Authorization: Bearer {LLM_API_KEY}`)
  - Endpoint: `/chat/completions` (POST)
  - Model: Configurable (default: `qwen36-ud-4bit` on oMLX)
  - Payload: JSON with `model`, `messages`, `temperature`, `max_tokens`
  - Used by: `score/triage_score.py`, `score/fever_triage.py`, `score/digest.py`, `score/sab_html.py`
  - Purpose: Scoring items against CCIR (interest profile) and generating digests
  - Implementation: `score/triage_score.py::llm()` - wraps urllib for compatibility

**YouTube (Video Transcription):**
- YouTube video metadata and audio
  - SDK/Client: `youtube-transcript-api` (optional, implicit in yt_to_atom.py architecture)
  - Transcription: `mlx_whisper` (Apple Silicon) or OpenAI `whisper` (fallback)
  - Config: `YT_CHANNELS` env var (JSON array) or `.yt_channels.json` file
  - Output: Atom feed `data/feeds/youtube-<slug>.xml`
  - Used by: `bridge/yt_to_atom.py`
  - Mode: Optional transcription (can emit stub summaries without transcription for testing)

## Data Storage

**Databases:**
- FreshRSS (in-container)
  - Type: SQLite (embedded in `freshrss/freshrss:latest` Docker image)
  - Path (container): `/var/www/FreshRSS/data`
  - Path (host): `./data/freshrss/` (Docker volume mount)
  - Connection: Automatic via FreshRSS ORM
  - Stores: User accounts, feed subscriptions, articles, read/unread state

- rss-bridge
  - Type: File-based cache (in-container)
  - Path (container): `/config`
  - Path (host): `./data/rssbridge/` (Docker volume mount)
  - Stores: Bridge configurations, cache of generated feeds

**File Storage (Local):**
- `./data/feeds/` - Generated feed files served by static server
  - `gmail.xml` - Gmail-to-Atom output (from `bridge/gmail_to_atom.py`)
  - `gmail-multi.xml` - Multi-IMAP output (from `bridge/imap_to_atom.py`)
  - `youtube-<slug>.xml` - YouTube transcript feeds (from `bridge/yt_to_atom.py`)
  - Server: `halverneus/static-file-server` on port 80 (internal Docker network)

- `./data/triage.log` - Cron log output from `score/fever_triage.py`

- `./data/digests/` - Generated digest files (if created by `score/digest.py`)

**Caching:**
- FreshRSS internal feed cache (TTL configurable per-feed in UI)
- rss-bridge local cache in `./data/rssbridge/`
- No external caching service

## Authentication & Identity

**Email (IMAP):**
- Google app password (not full Gmail API key) — can be revoked independently
  - Env var: `GMAIL_APP_PASSWORD`
  - Scope: Read-only IMAP access to specific account

- Per-account IMAP credentials in `.mailboxes.json`
  - Format: JSON array with `host`, `port`, `user`, `password` per entry
  - Example: `[{"host": "imap.gmail.com", "user": "...@gmail.com", "password": "...", ...}]`

**FreshRSS (Fever API):**
- Fever API username and password (stored in FreshRSS database)
  - Env vars: `FRESHRSS_FEVER_USER`, `FRESHRSS_FEVER_API_PASSWORD`
  - Auth method: MD5 hash of `username:password` sent as `api_key` in POST body
  - Used by: `score/fever_triage.py` to mark items read/unread
  - Web UI credentials: Admin / InfoTriageLocal23 (default, for local throw-away instance)

**LLM API:**
- Bearer token authentication (header-based)
  - Env var: `LLM_API_KEY` (default: `omlx` for oMLX, `ollama` for Ollama)
  - No external identity provider — API key is local/trusted

## Monitoring & Observability

**Error Tracking:**
- None (local, no external service)

**Logs:**
- Stdout/stderr to console and cron logs
- Triage log: `./data/triage.log` (from cron-scheduled `fever_triage.py`)
- Docker logs: `docker compose logs <service>`

**Alerting:**
- None (local system, no external monitoring)

## CI/CD & Deployment

**Hosting:**
- Local macOS machine (no cloud deployment)
- All services containerized via Docker Compose

**CI Pipeline:**
- None (local development only)
- Manual testing: `python3 script.py --sample` or piping JSON to stdin
- Test suite: `tests/` directory with pytest/unittest (runner not explicitly configured)

## Environment Configuration

**Required env vars (from `.env.example`):**
- `LLM_BASE_URL` — LLM API endpoint
- `LLM_API_KEY` — Bearer token for LLM
- `LLM_MODEL` — Model name to use
- `GMAIL_APP_PASSWORD` — Google app password (if using gmail_to_atom.py)
- `FRESHRSS_FEVER_URL` — FreshRSS Fever API endpoint (e.g., `http://localhost:8088/api/fever.php`)
- `FRESHRSS_FEVER_USER` — Fever API username
- `FRESHRSS_FEVER_API_PASSWORD` — Fever API password

**Optional env vars:**
- `GMAIL_QUERY` — Gmail search filter (default: `newsletters, 7d`)
- `MAILBOXES` — JSON array of IMAP accounts (or use `.mailboxes.json`)
- `YT_CHANNELS` — JSON array of YouTube channels (or use `.yt_channels.json`)

**Secrets location:**
- `.env` file (top-level, gitignored)
- `.mailboxes.json` (gitignored, plaintext IMAP creds)
- `.yt_channels.json` (gitignored, YouTube channel metadata)

## Webhooks & Callbacks

**Incoming:**
- None (no webhooks subscribed)

**Outgoing:**
- Fever API calls from `score/fever_triage.py` to mark items read/unread in FreshRSS
  - Endpoint: FreshRSS Fever API (`FRESHRSS_FEVER_URL?api&...`)
  - Payload: Form-encoded with `api_key`, `unread_item_ids`, `read_item_ids`
  - Used by: `fever()` function in `score/fever_triage.py`

## Content Sources (Feed Inputs)

**Subscribed Feeds:**
- 44+ RSS/Atom feeds in `opml/feeds.opml` (Norwegian + world + defense/geopolitics)
  - News outlets: NRK, VG, DN, Klassekampen, etc.
  - Government: Regjeringen.no, Stortinget, etc.
  - Defense/Security: ISW (Institute for the Study of War), Lawfare, Breaking Defense, etc.
  - International: Major news (BBC, Reuters, etc.), defense analysts
  - Data sources: GDELT (geopolitical events, 1 req / 5 sec rate limit)

- Sites without native RSS:
  - Forsvarets forum, FFI, NUPI, UTSYN, High North News
  - Workaround: Built via rss-bridge at `http://localhost:3000` (CSS-selector / XPathBridge)

**Rate Limiting Compliance:**
- GDELT: 1 request per 5 seconds (FreshRSS fetches at :23/:53 twice per hour, plus per-feed 6-hour TTL minimum)
- CloudFlare-protected feeds: May return 403; handled per-feed in FreshRSS UI or via rss-bridge

## Data Flow Summary

```
External Sources
├─ Gmail (IMAP)          ──▶ bridge/gmail_to_atom.py      ──▶ data/feeds/gmail.xml
├─ IMAP mailboxes        ──▶ bridge/imap_to_atom.py       ──▶ data/feeds/gmail-multi.xml
├─ YouTube channels      ──▶ bridge/yt_to_atom.py         ──▶ data/feeds/youtube-*.xml
└─ RSS/Atom feeds        ──▶ (native)
        │
        ▼
  Static File Server (feeds:/ on infotriage network)
        │
        ▼
  FreshRSS (freshrss:8088) ──▶ stores articles in SQLite
        │
        ▼
  score/fever_triage.py   ──▶ queries unread items (Fever API)
        │
        ├─▶ scores items via LLM (OpenAI-compatible endpoint)
        │
        ├─▶ marks skipped items read (Fever API)
        │
        └─▶ generates digest / outputs keepers

  score/digest.py         ──▶ generates CCIR-bucketed digests (cluster / brief / list modes)
  score/triage_score.py   ──▶ one-off scoring (stdin/JSON)
  score/sab_html.py       ──▶ HTML digest output
```

---

*Integration audit: 2026-06-24*
