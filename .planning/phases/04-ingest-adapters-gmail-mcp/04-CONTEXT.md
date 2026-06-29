# Phase 4: Ingest adapters + Gmail MCP - Context

**Gathered:** 2026-06-29
**Status:** Ready for planning

<domain>
## Phase Boundary

Containerize four working host-run ingest scripts (imap, youtube, gmail-MCP, obsidian), wire each to Postgres (`libs/store`) + RabbitMQ bus (`libs/contracts` BusClient), and retire the legacy IMAP-based Gmail bridge. Each adapter exposes an HTTP trigger endpoint (POST /run). A separate scheduler container (Python + APScheduler) fires each adapter on a configurable cron schedule.

</domain>

<spec_lock>
## Requirements (locked via SPEC.md)

**7 requirements are locked.** See `04-SPEC.md` for full requirements, boundaries, and acceptance criteria.

Downstream agents MUST read `04-SPEC.md` before planning or implementing. Requirements are not duplicated here.

**In scope (from SPEC.md):**
- `ingest-imap` Docker container + Dockerfile
- `ingest-youtube` Docker container + Dockerfile (stub transcription only)
- `ingest-gmail` MCP client Docker container + Dockerfile
- Gmail MCP server Docker container on `127.0.0.1:22025`
- One-time OAuth2 provision script for Gmail (writes refresh token to `.env`)
- `ingest-obsidian` Docker container + Dockerfile
- Scheduler container (cron-based, per-adapter config, single-instance lock)
- `docker-compose.yml` entries for all 6 new containers (4 adapters + scheduler + Gmail MCP)
- Atom XML output for YouTube only (`data/feeds/youtube-*.xml`)
- Upsert idempotency via `libs/store` interface
- Deletion of `gmail_to_atom.py`

**Out of scope (from SPEC.md):**
- `ingest-web` (direct HTTP scraper) — deferred to Phase 5+
- Real mlx-whisper transcription in Docker — mlx requires macOS Metal; deferred
- Atom XML for IMAP or Gmail — email is triage-only, not projected to FreshRSS
- FreshRSS Atom for `ingest-obsidian` — Obsidian clips go to SAB/Obsidian output (Phase 6)
- LLM scoring, PMESII/TESSOC enrichment — Phase 5
- Container healthchecks, structured logging, DLQ ops — Phase 7

</spec_lock>

<decisions>
## Implementation Decisions

### Adapter invocation model

- **D-01:** Each adapter exposes an **HTTP trigger endpoint** — `POST /run` returns `200 OK` or `409 Conflict` (if a run is already in progress). This is the single-instance lock mechanism: the adapter itself rejects concurrent invocations.
- **D-02:** Use **FastAPI** for the trigger endpoint in each adapter. Async-native; pairs cleanly with asyncio-based aio-pika BusClient. One route per adapter.
- **D-03:** Adapter trigger ports follow the **22010–22014 band**:
  - `ingest-imap` → `127.0.0.1:22010`
  - `ingest-youtube` → `127.0.0.1:22011`
  - `ingest-gmail` → `127.0.0.1:22012`
  - `ingest-obsidian` → `127.0.0.1:22013`
  - `scheduler` → `127.0.0.1:22014` (health/status endpoint)
- **D-04:** The **scheduler container** runs **Python + APScheduler**. Per-adapter cron expressions come from env vars. On each tick, the scheduler calls `httpx.post(f"http://{adapter_host}:{port}/run")` and logs the response code (200 = started, 409 = skipped — already running).

### Gmail MCP client transport

- **D-05:** The Python `ingest-gmail` adapter communicates with the Node.js MCP server at `:22025` via **raw httpx JSON-RPC calls** — no `mcp` Python SDK. The adapter calls the server's JSON-RPC tool endpoints directly using httpx.
- **D-06:** Gmail OAuth2 scopes: **`gmail.readonly` + `gmail.metadata`**. The provision script requests both. Satisfies NF-4 (read-only constraint); metadata scope enables label/thread filtering.
- **D-07:** The OAuth2 provision script completes the browser flow and **writes `GMAIL_OAUTH2_REFRESH_TOKEN` to `.env`**. The Gmail MCP server container mounts `.env` via `env_file` in docker-compose — same pattern as `POSTGRES_PASSWORD`, `RABBITMQ_DEFAULT_PASS`. Token never appears in a git-tracked file or Docker image layer (NF-6).

### Obsidian clip → Item field mapping

- **D-08:** Obsidian clips are created by the **official Obsidian Web Clipper** browser extension. Default frontmatter keys: `title`, `url`, `date`, `tags`, `author`, `site`, `description`.
- **D-09:** Field mapping (uses `libs/contracts._codec.from_frontmatter()` for YAML parsing):
  - `title` → `Item.title`
  - `url` → `Item.url`
  - `date` → `Item.ts` (parsed as tz-aware datetime; assume UTC if no offset)
  - `site` → `Item.source` (human-readable source name)
  - `description` → `Item.summary`
  - `lang` → inferred from title text (detect æ/ø/å or common NO patterns → `"no"`, else `"en"`; fallback `"und"` if indeterminate)
  - `source_type` always `"obsidian"`
  - Missing required fields (`title`, `url`, `date`) fall back to safe defaults: empty string / `utcnow()`. Adapter logs a warning but does not reject the clip.

### Docker packaging — local libs

- **D-10:** All adapter Dockerfiles use **`COPY + pip install`** pattern:
  ```dockerfile
  COPY libs/contracts /build/contracts
  COPY libs/store /build/store
  RUN pip install --no-deps /build/contracts /build/store
  ```
  No shared base image. A libs change rebuilds that layer in the affected adapter. Consistent across all 4 adapter Dockerfiles.
- **D-11:** Base image for all adapter containers: **`python:3.12-slim`**. `psycopg[binary]` bundles libpq (no apt-get for Postgres client). All required wheels (pydantic, aio-pika, pgvector, numpy) have pre-built slim-compatible packages.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & boundaries
- `.planning/phases/04-ingest-adapters-gmail-mcp/04-SPEC.md` — Locked requirements, boundaries, acceptance criteria, prohibitions. MUST read before planning.

### Architecture decisions
- `docs/ARCHITECTURE.md` — ADR-001 (libs/store interface), ADR-003 (read-only), ADR-004 (no cloud LLM), ADR-007 (RabbitMQ topology), ADR-008 (Gmail MCP/OAuth2 path)
- `.planning/ROADMAP.md` §Phase 4 — Goal, depends-on, success criteria

### Phase dependencies (read interfaces, not full docs)
- `.planning/phases/02-storage-postgres-blobs/02-CONTEXT.md` — libs/store interface decisions (upsert pattern, blob storage)
- `.planning/phases/03-bus-rabbitmq/03-CONTEXT.md` — aio-pika BusClient, connect_robust(), publisher confirms, DLX topology

### Existing ingest code (to containerize, not rewrite)
- `apps/ingest/imap_to_atom.py` — Multi-mailbox IMAP logic; containerize + replace Atom output with Item/bus
- `apps/ingest/yt_to_atom.py` — YouTube fetch logic; containerize + add Item/bus alongside existing Atom output
- `apps/ingest/gmail_to_atom.py` — To be **deleted** (not adapted); replaced entirely by MCP path

### Contracts & codec
- `libs/contracts/src/contracts/_item.py` — Item schema, SHA-256 id (dedup key), required fields
- `libs/contracts/src/contracts/_codec.py` — `from_frontmatter()` for Obsidian YAML parsing
- `libs/contracts/src/contracts/_bus.py` — BusClient Protocol (adapters call `publish()`)
- `libs/contracts/src/contracts/_bus_rabbitmq.py` — RabbitMQBus implementation (aio-pika, connect_robust)

### Infrastructure reference
- `docker-compose.yml` — Existing services, port assignments (8088/3000/22000/22001/22002), network name `infotriage`

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `libs/contracts._item.Item` — Pydantic model; adapters construct `Item(...)` then call `store.upsert(item)`. SHA-256 `id` is the idempotency key used by `libs/store` ON CONFLICT.
- `libs/contracts._codec.from_frontmatter()` — YAML frontmatter parser for Obsidian clips; already handles tz-aware datetime, Norwegian unicode, None→null.
- `libs/contracts._bus_rabbitmq.RabbitMQBus` — aio-pika BusClient implementation; adapters call `await bus.publish("item.ingested", item)`. `connect_robust()` for auto-reconnect.
- `libs/store._postgres.PostgresStore` — `upsert(item)` does ON CONFLICT on `articles.url`; returns `(row, is_new_insert)`. Adapters publish bus event only when `is_new_insert=True`.
- `apps/ingest/imap_to_atom.py` — IMAP fetch logic (multi-mailbox, X-GM-RAW query support) reusable; replace Atom output section with `Item` construction.
- `apps/ingest/yt_to_atom.py` — YouTube fetch + stub transcription logic reusable; add `Item` + bus path alongside existing `youtube-*.xml` output.

### Established Patterns
- Port band 22000+: postgres=22000, rabbitmq=22001/22002, gmail-mcp=22025; Phase 4 adds 22010–22014 for adapter trigger endpoints. All bound to `127.0.0.1` (not `0.0.0.0`).
- Credentials in `.env` via `env_file` in docker-compose (never in image layers, never in git).
- Docker network: `infotriage` — all containers join this network; inter-container calls use service name (e.g., `http://ingest-imap:8000/run`).
- `restart: unless-stopped` on long-running containers; adapters are long-running (FastAPI server stays up, trigger starts work).

### Integration Points
- `docker-compose.yml` — Add 6 new services: `ingest-imap`, `ingest-youtube`, `ingest-gmail`, `ingest-obsidian`, `scheduler`, `gmail-mcp-server`
- `libs/store` interface — all adapters call `await store.upsert(item)` and check `is_new_insert`
- RabbitMQ bus (`libs/contracts`) — all adapters call `await bus.publish("item.ingested", item)` on new inserts only

</code_context>

<specifics>
## Specific Ideas

- **Single-instance lock**: FastAPI adapter sets a `threading.Event` (or `asyncio.Event`) at `POST /run` start and clears it on completion. Returns `409` immediately if event is already set. No shared volume, no external lock service needed.
- **Scheduler → adapter communication**: `httpx.AsyncClient().post(f"http://{adapter_host}/run")` — scheduler treats `409` as "skipped (already running)" and logs accordingly; `200` as "started". No error on `409`.
- **OAuth2 provision script**: Separate `scripts/provision_gmail_oauth.py` — runs `google-auth-oauthlib` browser flow, writes `GMAIL_OAUTH2_REFRESH_TOKEN=...` to `.env`. Ships with Phase 4 but runs once on operator machine before `docker compose up`.
- **YouTube Atom output preserved**: `ingest-youtube` writes `data/feeds/youtube-*.xml` (same as `yt_to_atom.py`) AND publishes Item to bus. Dual output. FreshRSS subscribes to the Atom feed at `http://feeds/youtube-*.xml` as before.
- **No mlx-whisper in container**: `transcribe=false` forced. The `yt_to_atom.py` stub transcription path is retained as the only mode in the container.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 04-ingest-adapters-gmail-mcp*
*Context gathered: 2026-06-29*
