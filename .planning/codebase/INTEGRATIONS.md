# External Integrations

**Analysis Date:** 2026-06-24

## APIs & External Services

**Email — Gmail via MCP:**

- Containerized adapter (`apps/ingest-gmail/`) talks to a Node-side MCP server (`gmail-mcp-server`, `@shinzolabs/gmail-mcp`) over HTTP on the `infotriage` Docker network.
  - SDK/Client: Python `urllib` (via `make_trigger_app` from `libs/ingest_common`) → MCP server (Node) → Gmail API
  - Auth: OAuth2 — `python scripts/provision_gmail_oauth.py` writes `GMAIL_OAUTH2_REFRESH_TOKEN` to `.env` once
  - Used by: `apps/ingest-gmail/gmail_ingest.py` (publishes `item.ingested` on RabbitMQ)
  - Query language: Gmail search syntax (`GMAIL_QUERY=newer_than:7d`)
  - Replaces the retired host-side `bridge/gmail_to_atom.py` (ADR-008).

**Email — multi-protocol mail (`apps/ingest-imap/`):**

- IMAP via stdlib `imaplib` for non-Gmail (Outlook, Fastmail, ProtonMail, custom-domain); POP3 via stdlib `poplib` for servers that don't offer IMAP. Both READ-ONLY.
  - Auth: `MAILBOXES` env var (JSON array) or `.mailboxes.json` sibling file (gitignored). Plaintext on disk — see Security Considerations.
  - Output: `Item` rows in `InfoTriage.articles` + `item.ingested` events on RabbitMQ (not Atom files anymore — those go through the triage path now).
  - ADR-014.

**LLM — local-only (ADR-004):**

- **Intent (per PROJECT.md / ADR-004):** DGX Spark vLLM `qwen 80B` at `http://192.168.10.2:8000/v1` is the primary target when the Spark is on the LAN.
- **Runtime default (`ops/llm-router.py` + `.env.example`):** oMLX `qwen36-ud-4bit` at `http://127.0.0.1:8000/v1` — works standalone without Spark. To flip to DGX, uncomment the Spark `LLM_BASE_URL` line in `.env.example` and `docker compose up -d --build triage brief wiki` to pick up the new env.
- **Router:** `ops/llm-router.py` proxies both backends into a single local endpoint at `http://127.0.0.1:8600/v1`. Inside Docker, services reach the host router as `http://host.docker.internal:8600/v1` (compose hardcodes this to avoid `LLM_BASE_URL=127.0.0.1` from `.env` pointing at the container itself).
  - Auth: Bearer token in `Authorization` header (`LLM_API_KEY`); `EMPTY` for Spark (vLLM), `omlx` for oMLX.
  - Endpoint: `/chat/completions` (POST); reasoning is suppressed (`chat_template_kwargs: {enable_thinking: false}`) to keep sub-10s responses.
  - Used by: `apps/triage/worker.py`, `apps/brief/consumer.py`, `apps/wiki/wiki_worker.py`, `apps/triage/recall.py`.
  - ADR-004 forbids cloud LLMs anywhere in the runtime. Cloud models are only used by this assistant during design.

**Embedder — local-only:**

- **Primary (Mac oMLX):** `intfloat/multilingual-e5-large` (1024-dim, multilingual).
- **Spark transfer:** `Alibaba-NLP/gte-Qwen2-7B-instruct` (transferred from Mac since Spark has no internet to fetch weights).
- `EMBED_BASE_URL` + `EMBED_MODEL` select; default `intfloat/multilingual-e5-large`.

**YouTube — containerized (Phase 11 W5 transcription):**

- Containerized adapter (`apps/ingest-youtube/`) pulls channel data + optional local audio transcription.
  - SDK/Client: `yt-dlp` for metadata + audio extraction; `faster-whisper` (cross-platform, CPU `int8`) for transcription.
  - Transcription is opt-in: `INFOTRIAGE_YOUTUBE_TRANSCRIBE=1` + `INFOTRIAGE_WHISPER_MODEL=tiny` (runtime default per `.env.example` and compose). Bump to `large-v3-turbo` for multilingual ~8× turbo speed vs `large-v3`. Either choice survives a container rebuild.
  - Dockerfile installs `ffmpeg` + `libgomp1` per `apps/ingest-youtube/Dockerfile`.
  - Replaces the retired host-side `bridge/yt_to_atom.py`.

## Data Storage

**Stores:**

- **Postgres 16 + pgvector** (`postgres` service, image `pgvector/pgvector:pg16`) — canonical InfoTriage store.
  - Host port: `127.0.0.1:22000:5432` (localhost-only per ADR-016).
  - DSN: `INFOTRIAGE_PG_DSN=postgresql://infotriage:infotriage_dev@postgres:5432/infotriage` (from `.env`).
  - Schema: `InfoTriage.*` — articles, enrichment, embeddings, ccir, ccir_vectors, entities, entity_links, audit, plus strata tables.
  - One Postgres instance; FreshRSS owns its own schema; `InfoTriage.*` owns ours (no fan-out; ADR-004 contract).

- **FreshRSS** (legacy SQLite inside `freshrss/freshrss:latest`) — RSS aggregator + reader UI only.
  - Path (host): `./data/freshrss/` (volume-mounted).
  - Schema: `freshrss.*` — user accounts, feed subs, articles, read/unread.
  - Note: scoring no longer reads the Fever endpoint (fever_triage retired 2026-07-11, Phase 7). FreshRSS's `/api/fever.php` still works for external clients.

- **rss-bridge** cache (`./data/rssbridge/`) — bridge configurations + cache of generated feeds.

- **ntfy cache** (`./data/ntfy-cache/`) — runtime message cache only; credentials live in the pre-baked image layer (ADR-018), not on disk.

**File Storage (Local):**
- `./data/feeds/` - Generated feed files served by static server
  - `gmail.xml` - Gmail-to-Atom output (from `bridge/gmail_to_atom.py`)
  - `gmail-multi.xml` - Multi-IMAP output (from `bridge/imap_to_atom.py`)
  - `youtube-<slug>.xml` - YouTube transcript feeds (from `bridge/yt_to_atom.py`)
  - Server: `halverneus/static-file-server` on port 80 (internal Docker network)

- `./data/triage.log` - Cron log output from `score/fever_triage.py`

- `./data/digests/` - Generated digest files (if created by `score/digest.py`)

**Caching:**
- FreshRSS internal feed cache (TTL configurable per-feed in UI).
- rss-bridge local cache in `./data/rssbridge/`.
- ntfy runtime cache in `./data/ntfy-cache/` (writable bind).
- mE5-large embedding cache (in-process LRU) inside `apps/triage/worker.py`.
- `faster-whisper` model load cache (process-level, thread-safe) inside `apps/ingest-youtube/youtube_ingest.py`.
- No external caching service.

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

**Health aggregator:**
- `opml-health` service (`:22032`) polls every service's `/health` endpoint on a tick; surfaces aggregate status at `/admin/health`. Backs the `make status` Makefile target.

**Logs:**
- `setup_logging()` from `libs/contracts` emits JSON to stdout and a daily-rotating file under `/data/logs/<service>.log` (with `LOG_LEVEL` env var). Wired into every Compose service. Triage guide: `docs/ops/logging.md`.

**Alerts / DLQ pipeline:**
- `apps/dlq_consumer/` consumes `infotriage.dlq`; live RabbitMQ-mgmt queue-depth probe (configurable `DLQ_DEPTH_*`); emits `feed.unhealthy` after a consecutive-message threshold; supports `--replay` back to the original routing key.

**CAT-I push channel:**
- Local `ntfy` (`:22070`) for 🚩 / CNR-I per ADR-015 + ADR-018 (pre-baked Docker image, deny-all ACL default, BuildKit-secrets injection).

**External monitoring:**
- None (local-only system; the design principles in ADR-004 forbid cloud dependencies in the runtime, and the operator-facing surfaces above are the project's complete observability footprint).

## CI/CD & Deployment

**Hosting:**
- Local macOS machine (no cloud deployment)
- All services containerized via Docker Compose

**CI / Quality Gates:**

- None external (no GitHub Actions, no GitLab CI). Local pipeline baked into `ops/Makefile`:
  - `make test-safe` — `scripts/check_test_dsn.sh` first (refuses a DSN pointing at the prod port), then `make test-full`.
  - `make test-full` — full pytest suite against a throwaway `infotriage-test` Postgres container on `:22062`.
  - `make test-integration` — adds RabbitMQ to the test stack so `db_live` / `rabbitmq` / `integration` markers don't skip.
  - `make test-uvicorn-log`, `make test-dlq-depth`, `make test-dsn-smoke` — per-bug/per-feature regression gates.
  - `make ccir-sync`, `make ntfy-build`, `make ntfy-up`, `make ntfy-publish-test` — substrate sync / ntfy gating.

- Pre-commit (`.pre-commit-config.yaml`): black + mypy on staged Python files.

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

- **RabbitMQ bus** (`rabbitmq` 3.13-management) — event-driven fabric.
  - AMQP: `INFOTRIAGE_AMQP_DSN=amqp://infotriage:infotriage_rmq@rabbitmq:5672`; host `127.0.0.1:22001:5672`; mgmt UI `127.0.0.1:22002:15672`.
  - Routing keys (current): `item.ingested`, `verdict.ready`, `sab.published`, plus per-Phase-12 `cnn.cat-i`, `outbox.publish`, `outbox.dlx` (sub-wave b).
  - **Fan-out:** `verdict.ready` fans to BOTH `q.brief` AND `q.wiki` via `ROUTING_KEY_TO_QUEUE` list (commit `ec52292`).
  - DLX/DLQ: `infotriage.dlq` is consumed by `apps/dlq_consumer/`. Live RabbitMQ-mgmt queue-depth probe + auto-replay; tunable per `DLQ_DEPTH_*` envs.

- **FreshRSS Fever API** — still available for external clients (e.g. legacy scripts / external readers); no longer in the InfoTriage runtime path (fever_triage retired 2026-07-11, Phase 7).

## Content Sources (Feed Inputs)

**Subscribed Feeds:**

- 44+ curated RSS/Atom feeds in `apps/opml/feeds.opml` (CCIR-grouped, regenerated by `make ccir-sync` from the registry in `libs/contracts/src/contracts/ccir.py`).
  - News outlets: NRK, VG, DN, Klassekampen, BBC, Reuters, etc.
  - Government: Regjeringen.no, Stortinget, etc.
  - Defense/Security: ISW (Institute for the Study of War), Lawfare, Breaking Defense, etc.
  - Data sources: GDELT (geopolitical events, 1 req / 5 s rate limit).
- Sites without native RSS (Forsvarets forum, FFI, NUPI, UTSYN, High North News) → built via **rss-bridge** at `http://127.0.0.1:3000` (CSS-selector / XPathBridge).

**SOCMINT sources (Phase 11):**

- Telegram public channels (Telethon) — published channels only (`ingest-telegram`). ADR-014 explicitly gates DM scraping out. Tags items with `discipline=SOCMINT` + `admiralty_reliability=A-F/1-6` provenance.

**MASINT/AIS sources (Phase 11):**

- BarentsWatch AIS — Arctic vessel positions (`ingest-barentswatch`). Tagged `discipline=MASINT/AIS`.

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
