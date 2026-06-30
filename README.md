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

## Status of this spike (what's verified)

| Piece | State |
|-------|-------|
| FreshRSS + rss-bridge + feeds server in Docker | ✅ up, reachable (`:8088`, `:3000`) |
| qwen36 triage scorer vs your oMLX endpoint | ✅ tested live — correct buckets, ~3s/item |
| Gmail via OAuth2 MCP (`ingest-gmail`) | ✅ MCP path proven; replaces legacy IMAP bridge (ADR-008) |
| Scorer → FreshRSS auto-mark-read (Fever API) | ✅ wired + tested live (verified 2026-06-23) — marks junk read, unread count drops |
| FreshRSS provisioned headless (admin user, 44 feeds, 1642 articles) | ✅ done (see creds below) |

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

**Retired:** `apps/triage/fever_triage.py` was the production scoring path
(FreshRSS Fever-API polling + host crontab) before the event-driven triage
container existed. It is **no longer invoked** as a scoring path — the crontab
entry that ran it has been removed (R6, shadow-run parity confirmed via
`scripts/shadow_run.py`). The file itself is preserved because
`apps/triage/digest.py` still imports `fever_key`/`fever`/`strip_html` from it;
do not delete it.

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

## Bridges (ingest paths)

Three `apps/ingest/` scripts write Atom feeds into `data/feeds/<name>.xml`, which the `feeds` container serves to FreshRSS at `http://feeds/<name>.xml`. All are read-only of their source.

- **`apps/ingest-gmail/`** — Gmail via OAuth2 MCP (`ingest-gmail` container + `gmail-mcp-server`). Provision once with `scripts/provision_gmail_oauth.py`, then start containers (ADR-008).
- **`apps/ingest/imap_to_atom.py`** — multi-IMAP mailboxes (Outlook / Fastmail / ProtonMail / custom-domain). One runner, per-account provider dispatch via standard RFC 3501 SEARCH.

      Env / config:
      - `MAILBOXES='[…]'` — JSON array, set as a shell env var.
      - `.mailboxes.json` — sibling file fallback. **Plaintext IMAP creds; gitignored.**
- **`apps/ingest/yt_to_atom.py`** — YouTube channels → optional audio transcription → Atom feed. Default runner: `mlx_whisper` (Apple Silicon); cross-platform fallback: `whisper`. With `transcribe: false`, the script emits stub summaries so the wiring is end-to-end testable without any MLX install.

      Env / config:
      - `YT_CHANNELS='[…]'` — JSON array, set as a shell env var.
      - `.yt_channels.json` — sibling file fallback (gitignored).
      - Channel name slug is the output-filename stem (`youtube-<slug>.xml`); provide an explicit `name` if two channel URLs slug to the same string.

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
