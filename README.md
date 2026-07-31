# InfoTriage

*triage + e-mail* — a free, fully-local info-triage hub. Email + RSS + websites in
one searchable app, with a **local LLM on your Mac** deciding what's worth reading.
Nothing leaves the machine. No paid services.

```
 sources                hub (Docker, local)          brain (local, Mac)
 ───────                ───────────────────          ──────────────────
 RSS / YT / Reddit ───▶ FreshRSS  :8088 ──────────▶ qwen36 via oMLX/Ollama
 websites ─ rss-bridge :3000 ─▶ (subscribe in UI)    (score → read/maybe/skip,
 Gmail ─ ingest-gmail (MCP/OAuth2) ─▶ Postgres        mark junk read)
```

## Status of the system (verified, 2026-07-24)

| Piece | State |
|-------|-------|
| FreshRSS + rss-bridge + feeds static server | ✅ reachable (`:8088`, `:3000`, `127.0.0.1:22041`) |
| Postgres 16 + pgvector (`postgres`) | ✅ base storage for all post-Phase-2 data (`:22000`) |
| RabbitMQ 3.13-management (`rabbitmq`) | ✅ event-driven bus; AMQP `:22001`, mgmt UI `:22002` |
| DGX Spark (vLLM, qwen 80B) primary + oMLX fallback via `ops/llm-router.py` | ✅ ADR-004 — local-only; no cloud LLM anywhere |
| Event-driven triage worker (`triage`) | ✅ consumes `item.ingested` → emits `verdict.ready` (`:22030`) |
| Inbound adapters — IMAP · YouTube · Gmail MCP · Obsidian | ✅ containers at `127.0.0.1:22010..22013` |
| Brief app (`brief`) — SAB + cluster + Obsidian vault projection | ✅ consumes `verdict.ready` (`:22040`) |
| Wiki-LLM (`wiki`) — periodic + events modes; optional DGX Spark backend | ✅ writes Obsidian wiki pages (`:22042`) |
| SOCMINT — Telegram public channels (`ingest-telegram`) | ✅ discipline + admiralty reliability (`:22015`); needs `TELEGRAM_API_ID`/`HASH` |
| MASINT/AIS — BarentsWatch (`ingest-barentswatch`) | ✅ needs `BARENTSWATCH_CLIENT_ID`/`SECRET` (`:22016`) |
| OPML-health admin + DLQ consumer | ✅ health-aggregator (`:22032`); DLQ auto-replay |
| ntfy push channel (`ntfy`, pre-baked deny-all ACL) | ✅ image `infotriage-ntfy:prebaked` (`:22070`); Phase 12 sub-wave (a) |
| YouTube local audio transcription (`faster-whisper`) | ✅ opt-in via `INFOTRIAGE_YOUTUBE_TRANSCRIBE=1`; runtime default `INFOTRIAGE_WHISPER_MODEL=tiny` (bump to `large-v3-turbo` for multilingual) |
| Test suite | ✅ last recorded baseline **572 passed / 0 failed** (Phase 12 sub-wave (a) closeout, 2026-07-23) — refresh via `make test-safe` |
| FreshRSS provisioned headless (admin user, 44 feeds, 1642 articles) | ✅ done |

## Live services (operator reference)

The 19 `docker-compose.yml` services run on the `infotriage` Docker network. Published ports follow the `127.0.0.1:2Nxxx:container-port` convention (22010–22070 band, localhost-only per ADR-016). Up + down + status: `make help` from `ops/Makefile`. Live CCIR distribution is mid-flight per the 2026-07-24 dedup-fix re-score (verify before trusting).

| Service | Host port | Purpose | Healthcheck |
|---|---|---|---|
| `freshrss` | `8088:80` | RSS hub + web UI + Fever API | `http://127.0.0.1:8088/` |
| `rssbridge` | `3000:80` | turn non-RSS sites (Forsvarets forum, FFI…) into Atom | `http://127.0.0.1:3000/` |
| `feeds` | `127.0.0.1:22041:80` | static Atom server, mounts `data/feeds/<name>.xml` | `http://127.0.0.1:22041/` |
| `postgres` | `127.0.0.1:22000:5432` | pgvector; `InfoTriage.*` schema | `pg_isready` |
| `rabbitmq` | `127.0.0.1:22001:5672` + `:22002:15672` | AMQP bus + mgmt UI | `:22002` UI |
| `ingest-imap` | `127.0.0.1:22010:8000` | multi-protocol mail (IMAP/POP3, ADR-014) | `/health` |
| `ingest-youtube` | `127.0.0.1:22011:8000` | channels → Atom + opt-in `faster-whisper` | `/health` |
| `ingest-gmail` | `127.0.0.1:22012:8000` | OAuth2/MCP Gmail (ADR-008) | `/health` |
| `ingest-obsidian` | `127.0.0.1:22013:8000` | vault `articles-inbox/` → Atom (READ-ONLY) | `/health` |
| `ingest-telegram` | `127.0.0.1:22015:8000` | SOCMINT — public channels (Telethon) | `/health` |
| `ingest-barentswatch` | `127.0.0.1:22016:8000` | AIS MASINT — Arctic vessels | `/health` |
| `gmail-mcp-server` | `127.0.0.1:22025:3000` | `@shinzolabs/gmail-mcp` Node service (ADR-008) | TCP probe |
| `triage` | `127.0.0.1:22030:22030` | LLM scorer (CCIR-driven, qwen36/qwen80b) | `/health` |
| `opml-health` | `127.0.0.1:22032:22032` | cross-service health dashboard, `/admin/health` | `/health` |
| `brief` | `127.0.0.1:22040:22040` | SAB + markdown digest + Obsidian vault | `/health` |
| `wiki` | `127.0.0.1:22042:22040` | standup Obsidian wiki pages | `/health` |
| `dlq-consumer` | (background) | RabbitMQ `infotriage.dlq`; auto-replay | log watch |
| `ntfy` | `127.0.0.1:22070:80` | CAT-I 🚩 push channel (single-binary local ntfy, ADR-018) | `wget --spider :22070` |
| `scheduler` | `127.0.0.1:22014:8000` | APScheduler cron for ingest adapters | `/health` |

## Run it

```bash
cd ~/projects/InfoTriage
cp .env.example .env          # then edit .env (see below)
docker compose up -d          # FreshRSS http://localhost:8088
```

1. **FreshRSS setup** — open http://localhost:8088, finish the wizard (SQLite is fine),
   create your admin user.
2. **Add sources** — Subscriptions ▸ add RSS feeds directly. For a site with no feed,
   build one at http://localhost:3000 (rss-bridge) and subscribe to its URL.
3. **Email** — Gmail is ingested via the `ingest-gmail` container (OAuth2/MCP path, ADR-008).
   Run `python3 scripts/provision_gmail_oauth.py` once to obtain a refresh token, then
   `docker compose up ingest-gmail gmail-mcp-server`.

## The noise-killer (the point)

```bash
python3 apps/triage/triage_score.py --sample          # demo against your local model
cat items.json | python3 apps/triage/triage_score.py  # score real items
```

Scores each item 0–10 against your interest profile (local LLMs/Mac, Claude Code,
self-hosting, security, Rust, dev tooling) and buckets 🔥read / 🤔maybe / 🗑️skip —
all on qwen36, ~$0. Edit `ccir.md` to tune the dial — it's the triage brain.

### Event-driven triage (the scoring path) — ✅ working

```bash
docker compose up -d triage   # consumes item.ingested, writes infotriage.enrichment, publishes verdict.ready
curl http://localhost:22030/health
```

The `triage` container scores each incoming item against `ccir.md` with qwen36,
dedups via mE5-large embedding similarity, and persists the result to
`infotriage.enrichment` — no manual cron step required. **Tune `ccir.md`** to
retune what gets kept; it covers tech + defense/geopolitics + Norway + world news.
Too narrow a profile = it nukes everything (learned that the hard way).

### This FreshRSS instance (local throwaway)

- Web UI: http://localhost:8088 — login **admin** / **InfoTriageLocal23**
- Fever API password: **feverlocal23** (already in `.env`)
- Provisioned headless via the container CLI (`do-install.php`, `create-user.php`,
  `import-for-user.php`, `actualize-user.php`) — re-runnable if you wipe `data/`.

## Config (.env)

| Var | Default | Note |
|-----|---------|------|
| `LLM_BASE_URL` | `http://127.0.0.1:8000/v1` | oMLX (fallback). Spark: `192.168.10.2:8000/v1` |
| `LLM_API_KEY` | `omlx` | `EMPTY` for Spark (vLLM) |
| `LLM_MODEL` | `qwen36-ud-4bit` | any model your server lists |
| `GMAIL_QUERY` | `newer_than:7d` | Gmail search syntax (used by ingest-gmail MCP adapter) |

## Ingest adapters (containerized)

Each adapter is a containerized service under `apps/ingest-*/`, exposing an HTTP `/health` endpoint and (for adapters that need on-demand retrieval) a `/run` trigger endpoint. Each writes `Item` rows into `InfoTriage.articles` and emits `item.ingested` on RabbitMQ. All adapters are READ-ONLY of their source (no markup, no deletes, no replies — ADR-004 contract).

- **`ingest-imap` (`:22010`)** — multi-protocol mail. Protocol `imap` (Outlook / Fastmail / ProtonMail / custom-domain) or `pop3` (RFC 1939, UIDL-keyed) per mailbox entry. Per-account provider dispatch via standard RFC 3501 SEARCH.
  - Env: `MAILBOXES='[…]'` (JSON array) or `.mailboxes.json` sibling. **Plaintext IMAP creds; gitignored.**
- **`ingest-youtube` (`:22011`)** — YouTube channels → optional audio transcription (Phase 11 W5, opt-in via `INFOTRIAGE_YOUTUBE_TRANSCRIBE=1`, default model `large-v3-turbo`) → Atom feed.
  - Env: `YT_CHANNELS='[…]'` (JSON array) or `.yt_channels.json` sibling.
- **`ingest-gmail` (`:22012`)** — Gmail via OAuth2/MCP. Provision once with `scripts/provision_gmail_oauth.py`; runtime talks to `gmail-mcp-server` (`:22025`); replaces the legacy IMAP bridge (ADR-008).
- **`ingest-obsidian` (`:22013`)** — reads `Vault/articles-inbox/` (READ-ONLY bind per T-04-17) → emits `item.ingested`.
- **`ingest-telegram` (`:22015`)** — SOCMINT. Telethon over **public channels only** (ADR-014; no DM scraping). Needs `TELEGRAM_API_ID`/`HASH`. Tags items with discipline + admiralty reliability per Phase 11 schema.
- **`ingest-barentswatch` (`:22016`)** — MASINT/AIS. Arctic vessel positions from `barentswatch.no` (registered OAuth client). Needs `BARENTSWATCH_CLIENT_ID`/`SECRET`. Optional `BARENTSWATCH_AREA` bounding box.

The legacy `apps/ingest/` host-side bridge scripts (`imap_to_atom.py`, `yt_to_atom.py`) are no longer in the runtime path; superseded by the containerized adapters. Kept under `apps/ingest/` only for the `RSS_BRIDGE_NOTES.md` cross-reference.

For sites without native RSS (Forsvarets forum, FFI, NUPI, UTSYN, High North News), see [`apps/ingest/RSS_BRIDGE_NOTES.md`](apps/ingest/RSS_BRIDGE_NOTES.md) for how to bridge them via rss-bridge at [`http://localhost:3000`](http://localhost:3000).

## Feeds (Norwegian + world + defense/geopolitics)

`apps/opml/feeds.opml` — ~45 feeds, all URL-verified live 2026-06-23, grouped: Norske
aviser · Offentlig Norge · Norsk forsvar & sikkerhet · Forsvar & geopolitikk (intl)
· Verdensnyheter · Datakilder (GDELT) · Medium. Import in FreshRSS ▸ Subscription
management ▸ Import.

- **⚠️-marked feeds** (ISW, Lawfare, Breaking Defense, National Interest) exist but
  return 403 to bots (Cloudflare). FreshRSS may fetch them anyway; if a feed stays
  empty, rebuild it via rss-bridge.
- **No native RSS** (Forsvarets forum, FFI, NUPI, UTSYN, High North News): build a
  feed with **rss-bridge** at http://localhost:3000 (CSS-selector / XPathBridge).

## Polite polling (don't get banned)

Some sources rate-limit. **GDELT = 1 request / 5 seconds**; abuse gets you blocked.
Protections in place / to set:

- FreshRSS refresh runs twice an hour (`CRON_MIN: "23,53"`), feeds fetched one at a
  time — GDELT gets ≤2 hits/hour, far under its limit.
- For GDELT and any heavy feed, set a **long per-feed TTL** in FreshRSS:
  feed ▸ Manage ▸ "Refresh… at most every" → e.g. 6 hours.
- Don't spam the manual "Refresh all" button — that bypasses the schedule.
- If you script your own checks against a source, sleep ≥5 s between hits.

## X / Twitter — the honest status

**X has no free, native RSS** (killed in 2013) and the API is paid. Reliable local
options are limited:

1. **rss-bridge** (already running) has a Twitter/Nitter bridge, but it depends on a
   working **Nitter** instance — most public ones are dead/blocked by X. Self-hosting
   Nitter needs X guest tokens and breaks often. Fragile, but free + local.
2. **Paid relay** (RSS.app, etc.) — works, but not free and not local. Rejected per
   your constraints.

Recommendation: skip X for now, or pick 2–3 must-follow handles and self-host Nitter
as a separate spike — accepting it'll need babysitting. Tell me the handles if you
want me to try wiring rss-bridge to a Nitter instance.

## Teardown

```bash
docker compose down          # keep data/   |   add -v to wipe volumes
```
