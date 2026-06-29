# Phase 04: Ingest adapters + Gmail MCP — Research

**Researched:** 2026-06-29
**Domain:** Python containerization, FastAPI trigger endpoints, APScheduler, MCP/OAuth2, Docker multi-service
**Confidence:** MEDIUM (interfaces verified from source; MCP server package selection from web search)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Each adapter exposes an HTTP trigger endpoint — `POST /run` returns `200 OK` or `409 Conflict` (if already in progress). Single-instance lock mechanism: the adapter itself rejects concurrent invocations.
- **D-02:** Use **FastAPI** for the trigger endpoint in each adapter. Async-native; pairs cleanly with asyncio-based aio-pika BusClient. One route per adapter.
- **D-03:** Adapter trigger ports follow the **22010–22014 band** (host-side). Inter-container calls use service name + internal port 8000.
- **D-04:** The **scheduler container** runs **Python + APScheduler**. Per-adapter cron expressions come from env vars. On each tick, calls `httpx.post(f"http://{adapter_host}:{port}/run")` and logs the response code.
- **D-05:** The Python `ingest-gmail` adapter communicates with the Node.js MCP server at `:22025` via **raw httpx JSON-RPC calls** — no `mcp` Python SDK.
- **D-06:** Gmail OAuth2 scopes: **`gmail.readonly` + `gmail.metadata`**.
- **D-07:** OAuth2 provision script writes `GMAIL_OAUTH2_REFRESH_TOKEN` to `.env`. Gmail MCP server mounts `.env` via `env_file`. Token never appears in a git-tracked file or Docker image layer.
- **D-08/D-09:** Obsidian clips use official Web Clipper frontmatter. Field mapping via `libs/contracts._codec.from_frontmatter()`.
- **D-10:** All adapter Dockerfiles use `COPY + pip install --no-deps` for local libs.
- **D-11:** Base image: `python:3.12-slim`. `psycopg[binary]` bundles libpq.

### Claude's Discretion

None specified — all key decisions are locked.

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| R1 | `ingest-imap` container: IMAP → Item → Postgres + bus; no Atom output | imap_to_atom.py fetch logic reusable; replace write_atom with put_item + bus.publish |
| R2 | `ingest-youtube` container: yt-dlp + stub transcription → Item + Atom XML; bus publish | yt_to_atom.py reusable; dual output (Atom + bus) pattern confirmed |
| R3 | `ingest-gmail` (MCP/OAuth2): gmail-mcp-server at :22025; thin MCP client adapter | @shinzolabs/gmail-mcp@1.7.4 confirmed OK; @googleapis/mcp-server-google-workspace does NOT exist — REMOVED |
| R4 | `ingest-obsidian` container: reads articles-inbox/*.md, normalizes to Item | from_frontmatter() in contracts already handles this; field mapping in D-09 |
| R5 | Scheduler container: cron-based, per-adapter config, single-instance lock | APScheduler 3.11.3 BackgroundScheduler; adapter 409 → skipped |
| R6 | Upsert idempotency: no duplicate rows or events on re-run | store.get_item() before put_item() pattern (see Critical Findings) |
| R7 | Legacy gmail_to_atom.py retired | git rm apps/ingest/gmail_to_atom.py |
</phase_requirements>

---

## Summary

Phase 4 containerizes four working Python ingest scripts, wires them to the Postgres store and RabbitMQ bus from Phases 2–3, and replaces the dead-end Gmail IMAP bridge with a self-hosted MCP/OAuth2 path. Each adapter runs as a long-lived FastAPI server that responds to `POST /run` trigger calls from a central APScheduler container.

The phase is primarily a packaging and integration task: the fetch logic in `imap_to_atom.py` and `yt_to_atom.py` is reusable as-is; the Atom output sections are replaced with `Item` construction + `put_item()` + `bus.publish()`. The `ingest-obsidian` adapter is greenfield but maps directly to `from_frontmatter()` which already exists in `libs/contracts`. The hardest new piece is the Gmail MCP path.

**Critical correction:** The SPEC and CONTEXT both name `@googleapis/mcp-server-google-workspace` as the Gmail MCP server package — this package does **not exist on npm**. The verified replacement is `@shinzolabs/gmail-mcp@1.7.4`, which supports Streamable HTTP transport via `PORT` env var and accepts `REFRESH_TOKEN`, `CLIENT_ID`, `CLIENT_SECRET` as environment variables, making it fully headless-safe for Docker operation.

**Primary recommendation:** Proceed with locked decisions as-is, but replace the package reference in the Gmail MCP server Dockerfile from the nonexistent `@googleapis/mcp-server-google-workspace` to `@shinzolabs/gmail-mcp@1.7.4`, and use the corrected `put_item()` idempotency pattern (pre-check with `get_item()` rather than relying on a return value).

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| IMAP fetch logic | `ingest-imap` container | — | Wraps existing script; no cross-tier concern |
| YouTube fetch + Atom | `ingest-youtube` container | `feeds` static server | Dual output: bus event + file for FreshRSS |
| Gmail OAuth2 token store | Host `.env` file | Docker `env_file` mount | D-07: never in image layers or git |
| Gmail MCP server | `gmail-mcp-server` container | — | Node.js process; isolated OAuth2 token holder |
| Gmail MCP client | `ingest-gmail` container | — | Python; calls gmail-mcp-server via httpx JSON-RPC |
| Obsidian vault read | `ingest-obsidian` container | Host filesystem (bind-mount) | Read-only bind mount; vault never modified |
| Cron scheduling | `scheduler` container | — | Single APScheduler instance; fires all adapters |
| Item persistence | `libs/store` (PostgresStore) | Postgres container | ADR-001: all persistence via store interface |
| Bus publish | `libs/contracts` (RabbitMQBus) | RabbitMQ container | ADR-007: all events via bus interface |

---

## Standard Stack

### Core (Python adapters)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `fastapi` | 0.138.1 [VERIFIED: pip registry] | HTTP trigger endpoint per adapter | Async-native; D-02 locked |
| `uvicorn` | 0.49.0 [VERIFIED: pip registry] | ASGI server for FastAPI | Required FastAPI runtime |
| `apscheduler` | 3.11.3 [VERIFIED: pip registry] | Cron scheduler container | D-04 locked; 3.x is latest stable |
| `httpx` | 0.28.1 [VERIFIED: pip registry] | Sync HTTP calls from scheduler; async MCP calls from ingest-gmail | D-04/D-05 locked |
| `aio-pika` | 9.6.2 [VERIFIED: pip registry] | RabbitMQ bus publish | Phase 3 — already in libs/contracts |
| `psycopg[binary]` | ≥3.3 [VERIFIED: pip registry] | Postgres store | Phase 2 — already in libs/store |

### Gmail MCP (Node.js server)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `@shinzolabs/gmail-mcp` | 1.7.4 [VERIFIED: npm registry] | Self-hosted Gmail MCP server with HTTP transport | Only npm-OK package supporting HTTP transport + headless REFRESH_TOKEN mode |
| `@modelcontextprotocol/sdk` | 1.29.0 [VERIFIED: npm registry] | MCP SDK (already a dep of gmail-mcp) | Official Anthropic MCP SDK |

### OAuth2 provision script

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `google-auth-oauthlib` | 1.4.0 [VERIFIED: pip registry] | InstalledAppFlow browser OAuth2 | Official Google auth library; D-06/D-07 |
| `google-api-python-client` | 2.198.0 [VERIFIED: pip registry] | Gmail API Python client (provision script + optional direct fallback) | Official Google client library |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `@shinzolabs/gmail-mcp` | Build custom Node.js MCP server | More control but >2 days of extra work; @shinzolabs/gmail-mcp has 60+ Gmail tools ready |
| APScheduler 3.x | APScheduler 4.x | 4.x API is completely different (Scheduler class, not BackgroundScheduler); 4.x is still pre-release on PyPI (3.11.3 is latest stable) |
| FastAPI `asyncio.create_task` lock | `asyncio.Event` | bool flag is simpler in practice; `asyncio.Event` requires `.is_set()` awareness; both work |

**Installation (adapter containers, Python):**
```bash
pip install fastapi uvicorn httpx aio-pika psycopg[binary] pgvector numpy pydantic PyYAML
```

**Installation (gmail-mcp-server, Node.js):**
```bash
npm install @shinzolabs/gmail-mcp
```

**Installation (provision script, host):**
```bash
pip install google-auth-oauthlib google-api-python-client
```

---

## Package Legitimacy Audit

> Package Legitimacy Gate run 2026-06-29 via `gsd-tools query package-legitimacy check`.

### npm packages

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| `@googleapis/mcp-server-google-workspace` | npm | — | — | none | SLOP | **REMOVED** — does not exist on registry |
| `@shinzolabs/gmail-mcp` | npm | ~11 mo | 1,795/wk | github.com/shinzo-labs/gmail-mcp | OK | Approved |
| `@modelcontextprotocol/sdk` | npm | ~3 mo | 40.9M/wk | github.com/modelcontextprotocol/typescript-sdk | OK | Approved |
| `mcp-google-workspace` | npm | ~1 mo | 93/wk | github.com/VSF-TTS/AI-Platform-A | SUS | Not recommended — too new, low downloads |

### PyPI packages (all established, SUS flags are PyPI API download-count limitation)

| Package | Registry | Source Repo | Verdict | Disposition |
|---------|----------|-------------|---------|-------------|
| `fastapi` | PyPI | github.com/fastapi/fastapi | SUS* | Approved — official, widely used; flag is PyPI download API limitation |
| `apscheduler` | PyPI | github.com/agronholm/apscheduler | SUS* | Approved — official, 10+ year project |
| `httpx` | PyPI | github.com/encode/httpx | SUS* | Approved — official encode project |
| `google-auth-oauthlib` | PyPI | github.com/googleapis/google-cloud-python | SUS* | Approved — official Google library |
| `google-api-python-client` | PyPI | github.com/googleapis/google-api-python-client | SUS* | Approved — official Google library |
| `aio-pika` | PyPI | github.com/mosquito/aio-pika | SUS* | Approved — Phase 3 already uses it |
| `psycopg` | PyPI | psycopg.org | SUS* | Approved — Phase 2 already uses it |
| `pgvector` | PyPI | github.com/pgvector/pgvector-python | SUS* | Approved — Phase 2 already uses it |
| `googleapis` | PyPI | — | SLOP | **REMOVED** — does not exist on PyPI; correct package is `google-api-python-client` |

*PyPI seam returns SUS/unknown-downloads for all PyPI packages because PyPI API doesn't expose weekly download counts in the same endpoint npm uses. All flagged PyPI packages here have official GitHub repos confirmed above.

**Packages removed due to SLOP verdict:** `@googleapis/mcp-server-google-workspace` (npm), `googleapis` (PyPI)
**Packages flagged as suspicious [SUS]:** `mcp-google-workspace` (npm) — planner must NOT use this

---

## Architecture Patterns

### System Architecture Diagram

```
 Host operator
      │ runs once: scripts/provision_gmail_oauth.py
      │ writes GMAIL_OAUTH2_REFRESH_TOKEN to .env
      ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Docker compose network: infotriage                                 │
│                                                                     │
│  ┌─────────────┐  POST /run   ┌──────────────┐                     │
│  │  scheduler  │─────────────▶│ ingest-imap  │─┐                   │
│  │ (APScheduler│  (cron tick) │  FastAPI     │ │ put_item()         │
│  │  3.11.3)    │──────────────▶ ingest-youtube│ ├──▶ Postgres       │
│  │  :22014     │──────────────▶ ingest-gmail  │ │    :22000         │
│  │             │──────────────▶ ingest-obsidian│ │                  │
│  └─────────────┘              └──────────────┘ │ bus.publish()      │
│                                                 └──▶ RabbitMQ       │
│  ingest-gmail ─httpx JSON-RPC──▶ gmail-mcp-server   :22001         │
│                                  (@shinzolabs/gmail-mcp             │
│                                   :3000, HTTP transport)            │
│                                  (REFRESH_TOKEN from .env)          │
│                                                                     │
│  ingest-youtube ───writes───▶ data/feeds/youtube-*.xml              │
│                               (served by feeds container            │
│                                for FreshRSS :8088)                  │
│                                                                     │
│  ingest-obsidian ◀─bind-mount── $OBSIDIAN_VAULT_PATH/articles-inbox │
└─────────────────────────────────────────────────────────────────────┘
```

### Recommended Project Structure

```
apps/
├── ingest-imap/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── main.py               # FastAPI app, imports imap fetch logic from imap_to_atom.py
├── ingest-youtube/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── main.py               # FastAPI app; dual output: Item+bus AND Atom XML
├── ingest-gmail/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── main.py               # FastAPI app; httpx calls to gmail-mcp-server:3000
├── ingest-obsidian/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── main.py               # FastAPI app; reads articles-inbox via bind-mount
└── scheduler/
    ├── Dockerfile
    ├── requirements.txt
    └── main.py               # APScheduler BackgroundScheduler; triggers all adapters
gmail-mcp-server/
├── Dockerfile                # Node.js 22-slim; npm install @shinzolabs/gmail-mcp
└── entrypoint.sh             # npx @shinzolabs/gmail-mcp with PORT and REFRESH_TOKEN
scripts/
└── provision_gmail_oauth.py  # One-time: InstalledAppFlow → write refresh token to .env
libs/
├── contracts/                # (existing) Item, BusClient, RabbitMQBus, from_frontmatter
└── store/                    # (existing) PostgresStore, put_item, get_item
```

### Pattern 1: FastAPI Trigger Endpoint (single-instance lock)

**What:** Every adapter exposes `POST /run`. Returns 409 if already running, starts work in background task and returns 200 immediately.
**When to use:** All 4 adapter containers (D-01/D-02).

```python
# Source: FastAPI docs (fastapi/fastapi) + phase decision D-01/D-02
import asyncio
from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI()
_running: bool = False

@app.post("/run")
async def trigger_run():
    global _running
    if _running:
        return JSONResponse(status_code=409, content={"status": "already_running"})
    _running = True
    asyncio.create_task(_ingest())
    return {"status": "started"}

async def _ingest():
    global _running
    try:
        await do_ingestion()
    finally:
        _running = False
```

**Run with:** `uvicorn main:app --host 0.0.0.0 --port 8000`

### Pattern 2: Store Idempotency (put_item + bus.publish only on new insert)

**What:** `put_item()` returns `None` — it does NOT indicate whether the row was new or updated. Adapters must call `get_item()` before `put_item()` to determine newness.
**When to use:** Every adapter that publishes `item.ingested` (all 4).

```python
# Source: libs/store/_protocol.py + libs/store/_postgres.py (Phase 2 — verified in this session)
# CRITICAL: put_item() returns None — CONTEXT.md description of (row, is_new_insert) is STALE

async def persist_and_publish(store, bus, item):
    existing = store.get_item(item.id)    # None = new, Item = duplicate
    store.put_item(item)                  # always upsert (ON CONFLICT on item.id)
    if existing is None:                  # only publish on genuine new insert
        await bus.publish(
            "item.ingested",
            item_id=item.id,
            payload={"source": item.source, "source_type": item.source_type,
                     "ts": item.ts.isoformat()}
        )
```

**Upsert key:** `item.id` = SHA-256 of `source_type + "\x00" + url + "\x00" + title`.

### Pattern 3: APScheduler 3.x cron scheduler

**What:** Single scheduler container fires adapter HTTP triggers on cron schedules. APScheduler 3.x jobs run in threads (not async); use `httpx.Client` (sync) not `httpx.AsyncClient`.
**When to use:** Scheduler container (D-04).

```python
# Source: PyPI apscheduler 3.11.3 [VERIFIED: pip registry]
# NOTE: APScheduler 4.x is NOT yet on PyPI stable — use 3.x API
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import httpx, os, logging, time

log = logging.getLogger(__name__)

ADAPTERS = {
    "ingest-imap":     (os.getenv("SCHEDULE_IMAP",     "0 */2 * * *"),  "http://ingest-imap:8000/run"),
    "ingest-youtube":  (os.getenv("SCHEDULE_YOUTUBE",  "0 */4 * * *"),  "http://ingest-youtube:8000/run"),
    "ingest-gmail":    (os.getenv("SCHEDULE_GMAIL",    "0 */2 * * *"),  "http://ingest-gmail:8000/run"),
    "ingest-obsidian": (os.getenv("SCHEDULE_OBSIDIAN", "*/30 * * * *"), "http://ingest-obsidian:8000/run"),
}

def fire_adapter(name: str, url: str):
    try:
        r = httpx.post(url, timeout=5.0)
        if r.status_code == 200:
            log.info("[%s] started (200)", name)
        elif r.status_code == 409:
            log.info("[%s] skipped — already running (409)", name)
        else:
            log.warning("[%s] unexpected status %d", name, r.status_code)
    except httpx.RequestError as e:
        log.error("[%s] connection error: %s", name, e)

scheduler = BackgroundScheduler()
for name, (cron, url) in ADAPTERS.items():
    scheduler.add_job(fire_adapter, CronTrigger.from_crontab(cron), args=[name, url], id=name)

scheduler.start()
try:
    while True:
        time.sleep(60)
except (KeyboardInterrupt, SystemExit):
    scheduler.shutdown()
```

### Pattern 4: Gmail MCP Client (raw httpx JSON-RPC)

**What:** Python adapter calls `@shinzolabs/gmail-mcp` Node.js server via Streamable HTTP transport — POST to MCP endpoint, JSON-RPC 2.0 format.
**When to use:** `ingest-gmail` adapter (D-05).

```python
# Source: MCP specification 2025-03-26 [CITED: modelcontextprotocol.io/specification/2025-03-26/basic/transports]
# MCP server: http://gmail-mcp-server:3000  (within Docker infotriage network)
# Transport: Streamable HTTP — every request is a new POST

import httpx, json, itertools

_id_counter = itertools.count(1)
MCP_URL = "http://gmail-mcp-server:3000"   # internal Docker service name

async def mcp_call(client: httpx.AsyncClient, session_id: str, method: str, params: dict) -> dict:
    """Send one JSON-RPC request to MCP endpoint, return result."""
    body = {"jsonrpc": "2.0", "method": method, "params": params, "id": next(_id_counter)}
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    resp = await client.post(f"{MCP_URL}/mcp", json=body, headers=headers, timeout=30.0)
    resp.raise_for_status()
    return resp.json()

async def init_mcp_session(client: httpx.AsyncClient) -> str:
    """Initialize MCP session, return session ID."""
    resp = await mcp_call(client, "", "initialize", {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "ingest-gmail", "version": "1.0"}
    })
    return resp.get("result", {}).get("sessionId", "")

async def list_gmail_messages(client, session_id, max_results=50):
    """Call list_threads tool via MCP."""
    result = await mcp_call(client, session_id, "tools/call", {
        "name": "list_threads",
        "arguments": {"maxResults": max_results, "labelIds": ["INBOX"]}
    })
    return result.get("result", {}).get("content", [])
```

### Pattern 5: Dockerfile for Python adapters (D-10/D-11)

```dockerfile
# Source: Phase 4 CONTEXT.md D-10/D-11 [VERIFIED: project decisions]
FROM python:3.12-slim

WORKDIR /app

# 1. Copy and install local libs (no-deps: their deps come from requirements.txt)
COPY libs/contracts /build/contracts
COPY libs/store /build/store
RUN pip install --no-deps /build/contracts /build/store

# 2. Install adapter requirements (includes all transitive deps)
COPY apps/ingest-imap/requirements.txt .
RUN pip install -r requirements.txt

# 3. Copy adapter source
COPY apps/ingest-imap/ .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Pattern 6: Gmail MCP server Dockerfile (Node.js)

```dockerfile
FROM node:22-slim
WORKDIR /app
RUN npm install @shinzolabs/gmail-mcp@1.7.4
# Env vars: CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN, PORT (=3000 default)
# All come from .env via docker-compose env_file — NEVER in image layers
CMD ["npx", "@shinzolabs/gmail-mcp"]
```

### Pattern 7: OAuth2 Provision Script

```python
# Source: google-auth-oauthlib 1.4.0 [VERIFIED: pip registry]
# Run once on operator machine: python scripts/provision_gmail_oauth.py
from google_auth_oauthlib.flow import InstalledAppFlow
import pathlib, re

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.metadata",
]

flow = InstalledAppFlow.from_client_secrets_file("client_secrets.json", SCOPES)
creds = flow.run_local_server(port=0)   # opens browser; blocks until complete
token = creds.refresh_token

env_path = pathlib.Path(".env")
env_content = env_path.read_text() if env_path.exists() else ""
env_content = re.sub(r"^GMAIL_OAUTH2_REFRESH_TOKEN=.*$", "", env_content, flags=re.M)
env_content = env_content.rstrip() + f"\nGMAIL_OAUTH2_REFRESH_TOKEN={token}\n"
env_path.write_text(env_content)
print("Refresh token written to .env")
```

### Anti-Patterns to Avoid

- **Calling `put_item()` and checking its return value for newness:** `put_item()` returns `None`. Call `get_item(item.id)` first instead. The CONTEXT.md description of `(row, is_new_insert)` is stale documentation from before Phase 2 was implemented.
- **Using APScheduler 4.x API (`from apscheduler import Scheduler`):** APScheduler 4.x is still pre-release on PyPI; latest stable is 3.11.3. Use `BackgroundScheduler` from `apscheduler.schedulers.background`.
- **Using `@googleapis/mcp-server-google-workspace` as the Gmail MCP server:** This package does not exist on npm. Use `@shinzolabs/gmail-mcp@1.7.4`.
- **`httpx.AsyncClient` in APScheduler jobs:** APScheduler 3.x runs jobs in threads, not async coroutines. Use `httpx.Client` (sync) for the scheduler's trigger calls, or wrap with `asyncio.run()`.
- **Binding Gmail MCP server to `0.0.0.0`:** Must be `127.0.0.1:22025:3000` in docker-compose (NF-6, ADR-008).
- **Baking credentials into Dockerfile with `ARG`/`ENV`:** All OAuth tokens and IMAP passwords must come from `.env` via `env_file` directive, never `ARG` or build-time `ENV`.
- **Direct Postgres calls from adapters:** Forbidden per ADR-001. All persistence must go through `libs/store` interface.
- **Publishing `item.ingested` unconditionally on every run:** Publish only when `get_item(item.id) is None` — i.e., genuine new insert.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Gmail API OAuth2 browser flow | Custom OAuth2 authorization code flow | `google-auth-oauthlib.InstalledAppFlow` | Handle PKCE, token refresh, state validation correctly |
| Gmail MCP server | Custom Node.js Gmail wrapper | `@shinzolabs/gmail-mcp@1.7.4` | 60+ Gmail tools, HTTP transport, headless REFRESH_TOKEN mode |
| Cron scheduling with overlap protection | Custom scheduler loop with locks | APScheduler 3.x + adapter 409 response | Overlap protection falls naturally from HTTP 409 pattern |
| IMAP MIME decoding | Custom email parser | stdlib `email` + `imaplib` (already in imap_to_atom.py) | MIME is complex; existing code handles it |
| YAML frontmatter parsing | Custom regex YAML parser | `libs/contracts._codec.from_frontmatter()` | Already handles tz-aware datetime, NO unicode, None→null |
| Content-addressed blob storage | Custom dedup logic | `store.put_blob()` | Already SHA-256 content-addressed, idempotent |
| MCP JSON-RPC client | Third-party MCP Python client lib | Direct `httpx` calls (D-05) | Simpler; avoids Python MCP SDK dependency; HTTP transport is straightforward |

---

## Critical Findings (read before planning)

### Finding 1: `@googleapis/mcp-server-google-workspace` does not exist on npm — SLOP

The SPEC.md and CONTEXT.md both reference `@googleapis/mcp-server-google-workspace` as the Gmail MCP server package. **This package does not exist on npm.** Registry verification returns 404.

**Replacement:** `@shinzolabs/gmail-mcp@1.7.4` [VERIFIED: npm registry]
- OK verdict from legitimacy gate (1,795 weekly downloads, GitHub repo)
- Supports Streamable HTTP transport via `PORT` env var (default 3000)
- Accepts `REFRESH_TOKEN`, `CLIENT_ID`, `CLIENT_SECRET` as env vars — fully headless
- Read-only tools: `list_threads`, `get_thread`, `list_messages`, `get_message`
- No credential files needed inside the container; env_file pattern works directly

**Impact on planning:** The Gmail MCP server Dockerfile must use `@shinzolabs/gmail-mcp` not the nonexistent `@googleapis` package.

### Finding 2: `put_item()` returns `None` — CONTEXT.md description is stale

CONTEXT.md states: `libs/store._postgres.PostgresStore — upsert(item) does ON CONFLICT on articles.url; returns (row, is_new_insert)`. Both claims are wrong:
- Method name is `put_item()`, not `upsert()`
- ON CONFLICT is on `articles.id` (SHA-256 of `source_type+url+title`), not `articles.url`
- Return type is `None`, not `(row, is_new_insert)`

**Correct idempotency pattern:**
```python
existing = store.get_item(item.id)   # pre-check
store.put_item(item)                 # upsert, always
if existing is None:
    await bus.publish("item.ingested", item_id=item.id, payload={...})
```

**Impact on planning:** Every task that references the `(row, is_new_insert)` return pattern must use the `get_item()` pre-check pattern instead.

### Finding 3: APScheduler 3.x (not 4.x) is the current stable release

The Context7 docs for APScheduler showed 4.x syntax (`from apscheduler import Scheduler`). PyPI shows latest stable is **3.11.3**. APScheduler 4.x is still pre-release. The CONTEXT.md says "APScheduler" without a version.

**Use:** APScheduler 3.11.3 with `BackgroundScheduler` + `CronTrigger.from_crontab()`.

**Impact on planning:** Task for scheduler container must use 3.x imports, not 4.x.

### Finding 4: MCP Streamable HTTP transport protocol detail

`@shinzolabs/gmail-mcp` uses MCP Streamable HTTP transport per the 2025-03-26 spec:
- Every JSON-RPC message = new HTTP POST to the MCP endpoint (e.g. `/mcp`)
- `Accept: application/json, text/event-stream` must be included
- Session tracking via `Mcp-Session-Id` header (server returns it on `initialize`)
- First call MUST be `initialize` — subsequent tool calls include the session ID
- Tools are called via `tools/call` method with `name` and `arguments` fields

**Impact on planning:** `ingest-gmail` main.py must initialize MCP session at startup and pass session ID on all subsequent calls.

---

## Common Pitfalls

### Pitfall 1: APScheduler jobs cannot call async functions directly
**What goes wrong:** APScheduler 3.x schedules jobs in a thread pool. Calling `async def` functions directly from a job raises `RuntimeWarning: coroutine was never awaited`.
**Why it happens:** `asyncio.create_task()` requires an active event loop; APScheduler 3.x thread pool has none.
**How to avoid:** Use `httpx.Client` (sync) for scheduler trigger calls, OR use `asyncio.run(async_fn())` inside the job function to create a fresh event loop for that call.
**Warning signs:** `RuntimeWarning` in scheduler logs; adapters never actually triggered.

### Pitfall 2: Docker build context excludes libs/ if COPY is relative
**What goes wrong:** `COPY libs/contracts /build/contracts` fails if the Docker build context is set to `apps/ingest-imap/` (the adapter subdirectory). The `libs/` tree is outside that context.
**Why it happens:** `docker build` can only access files within the build context directory.
**How to avoid:** Always run `docker build` from the project root (e.g., `docker build -f apps/ingest-imap/Dockerfile .`). The `docker-compose.yml` build stanza must use `context: .` (project root) and `dockerfile: apps/ingest-imap/Dockerfile`.
**Warning signs:** `COPY failed: file not found in build context`.

### Pitfall 3: Gmail MCP server may use stdio transport by default
**What goes wrong:** `@shinzolabs/gmail-mcp` defaults to stdio transport when launched without `PORT` set. In Docker, the Python adapter calling it via httpx would get connection refused.
**Why it happens:** MCP servers historically defaulted to stdio for direct Claude Desktop integration.
**How to avoid:** Always set `PORT=3000` (or another port) as an env var in the Gmail MCP server container via docker-compose. Confirm the server is listening with a health probe before the adapter starts.
**Warning signs:** Python adapter gets `httpx.ConnectError` when calling `http://gmail-mcp-server:3000/mcp`.

### Pitfall 4: Obsidian bind-mount requires exact vault path
**What goes wrong:** Container starts but no `.md` files are found in `articles-inbox/`. Adapter produces 0 items silently.
**Why it happens:** `OBSIDIAN_VAULT_PATH` env var points to the vault root, but the container bind-mount must expose `$OBSIDIAN_VAULT_PATH/articles-inbox/`.
**How to avoid:** Bind-mount `${OBSIDIAN_VAULT_PATH}/articles-inbox` directly as the container's read path, or mount the vault root and use `os.path.join(os.getenv("VAULT_PATH"), "articles-inbox")` inside the container.
**Warning signs:** 0 items ingested; no error logged.

### Pitfall 5: yt-dlp requires manual channel URL format
**What goes wrong:** `yt_dlp_list(channel_url)` fails or returns empty list for certain YouTube channel URL formats.
**Why it happens:** yt-dlp accepts `https://www.youtube.com/@ChannelHandle`, `https://www.youtube.com/channel/UCxxxxxx`, and `https://www.youtube.com/c/ChannelName` — but not all are equivalent in all versions.
**How to avoid:** Normalize channel URLs to `@handle` or `UCxxxxxx` format. Test each configured channel URL with `yt-dlp --flat-playlist --dump-json <url>` before containerizing.
**Warning signs:** yt-dlp returns empty metadata or 403/404.

### Pitfall 6: IMAP TLS connection settings differ by provider
**What goes wrong:** IMAP connection fails for non-Gmail providers (Outlook, Fastmail, ProtonMail).
**Why it happens:** `imaplib.IMAP4_SSL` defaults to port 993; some providers use STARTTLS on port 143 instead. `imap_to_atom.py` uses `IMAP4_SSL` which won't work with STARTTLS servers.
**How to avoid:** The existing `imap_to_atom.py` already handles provider dispatch via `infer_provider(host)`. Container config must document the correct port per provider. Check `IMAP_PORT` env var support.
**Warning signs:** `ssl.SSLError` or `TimeoutError` on connection.

---

## Code Examples

### imap_to_atom.py ingestion logic to adapt (existing)

The reusable parts from `apps/ingest/imap_to_atom.py`:
- `load_mailboxes()` — reads `MAILBOXES` env var (JSON array) or `.mailboxes.json`
- `infer_provider(host)` — returns `"gmail"` or `"imap"` based on host
- `search_ids(imap, query, provider)` — returns message IDs
- `fetch_entries(imap, ids, max_recent=60)` — returns `(subject, from_, snippet, message_id)` tuples

**Replace** `write_atom(name, entries)` with: construct `Item` per entry, call `persist_and_publish(store, bus, item)`.

**Item construction from IMAP entry:**
```python
from contracts import Item
from datetime import datetime, timezone

item = Item(
    source=mailbox["name"],
    source_type="imap",
    url=f"imap://{mailbox['host']}/{message_id}",   # synthetic URL; unique per message
    title=subject,
    ts=datetime.now(tz=timezone.utc),               # IMAP Date header parsing optional
    lang="und",                                      # unknown; Phase 5 adds lang detect
    summary=snippet[:500],
)
```

### Obsidian clip Item construction

```python
from contracts import Item, from_frontmatter
import re
from datetime import datetime, timezone

def item_from_obsidian_clip(path: str) -> Item:
    text = open(path).read()
    fm = from_frontmatter(text)   # libs/contracts._codec

    ts_raw = fm.get("date") or datetime.now(tz=timezone.utc)
    if isinstance(ts_raw, datetime) and ts_raw.tzinfo is None:
        ts_raw = ts_raw.replace(tzinfo=timezone.utc)

    title = fm.get("title") or ""
    lang = _infer_lang(title)

    return Item(
        source=fm.get("site") or "obsidian",
        source_type="obsidian",
        url=fm.get("url") or "",
        title=title,
        ts=ts_raw,
        lang=lang,
        summary=fm.get("description"),
    )

def _infer_lang(text: str) -> str:
    if re.search(r"[æøåÆØÅ]", text):
        return "no"
    return "en"
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Gmail IMAP + app passwords | Gmail MCP/OAuth2 | Google 2SV enforcement (ADR-008) | App passwords hard-blocked on 2SV accounts |
| Host-run Python scripts | Docker containers + FastAPI triggers | Phase 4 | Reproducible, scheduled, isolated |
| Atom XML file output for all sources | Atom only for YouTube; all sources → Postgres | Phase 4 | Email/Obsidian are triage-only, not FreshRSS feed items |
| APScheduler 3.x blocking API | APScheduler 3.x BackgroundScheduler | Stable since ~2014 | 4.x (async-native) is in pre-release; 3.x is production-safe |

**Deprecated/outdated:**
- `apps/ingest/gmail_to_atom.py`: Deleted in this phase (R7). No references to it should remain.
- `feedgen`: Phase 4 does not use feedgen except in `ingest-youtube` where it continues to write Atom XML.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `@shinzolabs/gmail-mcp` MCP endpoint path is `/mcp` (standard per MCP spec) | Code Examples, Pattern 4 | Python adapter would get 404; need to adjust to actual endpoint path the package exposes |
| A2 | APScheduler 3.x `BackgroundScheduler` is compatible with Python 3.12 | Standard Stack | Scheduler container would fail to start; could use a different cron library (e.g., `rq-scheduler`, `cron` wrapper) |
| A3 | `@shinzolabs/gmail-mcp` starts in HTTP transport mode when `PORT` env var is set | Pattern 3 / Pitfall 3 | MCP server defaults to stdio; Python adapter cannot connect via httpx |
| A4 | `yt-dlp` is installable via `pip install yt-dlp` inside `python:3.12-slim` without additional system packages | Standard Stack | Container build fails; may need `apt-get install ffmpeg` for certain operations |

---

## Open Questions (RESOLVED in planning — Plan 04-05 Task 1)

1. **What MCP endpoint path does `@shinzolabs/gmail-mcp` expose for HTTP transport?**
   - What we know: Streamable HTTP transport is supported; `PORT` env var configures the port
   - What's unclear: Whether the endpoint is `/mcp`, `/`, or something else
   - **Resolution:** Plan 04-05 Task 1 resolves this at execution time — build container, confirm endpoint path via `curl`, record result in SUMMARY before Task 2 consumes it. Default `/mcp` used as fallback.

2. **Does `@shinzolabs/gmail-mcp` start in HTTP transport mode without additional flags?**
   - What we know: README confirms `PORT` env var activates Streamable HTTP
   - What's unclear: Whether the server needs a `--transport http` flag or if `PORT` alone is sufficient
   - **Resolution:** Plan 04-05 Task 1 spike: `PORT=3000 npx @shinzolabs/gmail-mcp` — confirmed or corrected at execution time.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker 29+ | All containers | ✓ | 29.4.0 (OrbStack) | — |
| Python 3.12+ | Container base image (confirm local pip install too) | ✓ | 3.13.5 on host | — |
| Node.js 22+ | gmail-mcp-server container | ✓ | 22.12.0 | Node.js 20 LTS |
| yt-dlp | `ingest-youtube` | ✓ | 2026.06.09 | — |
| Postgres :22000 | All adapters (store) | ✓ | Running (pg_isready confirmed) | — |
| RabbitMQ :22001 | All adapters (bus) | ✗ | Not running | `docker compose up rabbitmq` before integration tests |

**Missing dependencies with no fallback:** RabbitMQ must be running for bus integration tests. Start with `docker compose up rabbitmq -d`.

**Missing dependencies with fallback:** None.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (pyproject.toml `[tool.pytest.ini_options]`) |
| Config file | `pyproject.toml` — `testpaths = ["tests"]`, `pythonpath = [...]` |
| Quick run command | `pytest tests/ -m "not db_live and not rabbitmq" -x` |
| Full suite command | `pytest tests/ -x` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| R1 | IMAP adapter: given mailbox with ≥1 message, produces ≥1 articles row + ≥1 bus event; no imap*.xml created | integration | `pytest tests/test_ingest_imap.py -x -m db_live` | ❌ Wave 0 |
| R2 | YouTube adapter: produces ≥1 articles row + ≥1 bus event + non-empty youtube-*.xml | integration | `pytest tests/test_ingest_youtube.py -x -m db_live` | ❌ Wave 0 |
| R3 | Gmail MCP: server starts healthy; adapter produces ≥1 row with source_type=gmail + ≥1 bus event | integration | `pytest tests/test_ingest_gmail.py -x -m db_live` | ❌ Wave 0 |
| R4 | Obsidian adapter: given ≥1 .md in articles-inbox, produces ≥1 row with source_type=obsidian | unit | `pytest tests/test_ingest_obsidian.py -x` | ❌ Wave 0 |
| R5 | Scheduler: overlapping invocations are skipped (409 logged as skip) | unit | `pytest tests/test_scheduler.py -x` | ❌ Wave 0 |
| R6 | Idempotency: running adapter twice against same data → same row count; bus event only on first run | unit | `pytest tests/test_ingest_idempotency.py -x` | ❌ Wave 0 |
| R7 | Legacy gmail_to_atom.py deleted | static | `git ls-files apps/ingest/gmail_to_atom.py \| grep -c .` returns 0 | — |

### Sampling Rate
- **Per task commit:** `pytest tests/ -m "not db_live and not rabbitmq" -x`
- **Per wave merge:** `pytest tests/ -x` (requires Postgres and RabbitMQ running)
- **Phase gate:** Full suite green + docker compose up smoke before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_ingest_imap.py` — covers R1 (unit-level: mock IMAP via imaplib mock; integration: real mailbox with `db_live` marker)
- [ ] `tests/test_ingest_youtube.py` — covers R2 (unit: mock yt-dlp subprocess; check Atom file created + Item constructed)
- [ ] `tests/test_ingest_gmail.py` — covers R3 (unit: mock MCP server via httpx_mock; integration: real MCP server with `db_live`)
- [ ] `tests/test_ingest_obsidian.py` — covers R4 (unit: write temp .md file, run adapter, check Item fields)
- [ ] `tests/test_scheduler.py` — covers R5 (unit: mock HTTP responses; first=200, second=409; verify log)
- [ ] `tests/test_ingest_idempotency.py` — covers R6 (unit: InMemoryStore + InMemoryBus; run twice same Item; verify 1 row + 1 event)

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes (OAuth2 token) | `google-auth-oauthlib` InstalledAppFlow; refresh token in `.env` only |
| V3 Session Management | partial (MCP session ID) | MCP session ID is ephemeral per-container-run; no persistent session state |
| V4 Access Control | yes (read-only constraint) | Gmail OAuth2 scope `gmail.readonly` only; no STORE/EXPUNGE in IMAP |
| V5 Input Validation | yes | `contracts.Item` Pydantic validation; `from_frontmatter()` uses `yaml.safe_load` |
| V6 Cryptography | no direct use | OAuth2 handled by `google-auth` library (never hand-rolled) |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| OAuth2 refresh token in container image | Information Disclosure | env_file docker-compose pattern; never `ARG`/`ENV` in Dockerfile |
| Gmail MCP server port reachable externally | Elevation of Privilege | `127.0.0.1:22025:3000` not `22025:3000` in docker-compose |
| IMAP write operations (STORE/EXPUNGE) | Tampering | Code review: grep for STORE/EXPUNGE/DELETE in adapter source |
| YAML injection via malformed Obsidian frontmatter | Tampering | `yaml.safe_load` (never `yaml.load`); validated by `from_frontmatter()` |
| DNS rebinding attack on local MCP server | Spoofing | MCP spec requires `Origin` header validation; `@shinzolabs/gmail-mcp` bound to `127.0.0.1` only |

---

## Sources

### Primary (MEDIUM confidence)
- `/fastapi/fastapi` (Context7) — POST endpoint, BackgroundTasks, asyncio.create_task pattern
- `/agronholm/apscheduler` (Context7) — CronTrigger, BackgroundScheduler, from_crontab()
- `libs/store/_protocol.py` (codebase) — `put_item()` signature, return type `None`
- `libs/store/_postgres.py` (codebase) — ON CONFLICT on `item.id`, audit row pattern
- `libs/contracts/_bus_rabbitmq.py` (codebase) — `publish(routing_key, item_id, payload)` signature
- `libs/contracts/_codec.py` (codebase) — `from_frontmatter()` YAML parser

### Secondary (MEDIUM confidence)
- [MCP specification 2025-03-26 transports](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports) — Streamable HTTP protocol, POST to /mcp, session ID
- [npm registry: @shinzolabs/gmail-mcp](https://www.npmjs.com/package/@shinzolabs/gmail-mcp) — 1.7.4, PORT env var, REFRESH_TOKEN
- [npm registry: @modelcontextprotocol/sdk](https://www.npmjs.com/package/@modelcontextprotocol/sdk) — 1.29.0, official MCP SDK

### Tertiary (LOW confidence — training knowledge supplemented by web search)
- yt-dlp `--flat-playlist --dump-json` flag for metadata-only channel listing
- `@shinzolabs/gmail-mcp` MCP endpoint path (assumed `/mcp` — unconfirmed; Wave 0 spike recommended)

---

## Metadata

**Confidence breakdown:**
- Standard stack: MEDIUM — all packages verified on registries; PyPI download counts unavailable from API
- Architecture: HIGH — based on verified Phase 2/3 interface code read directly
- Pitfalls: MEDIUM — derived from code analysis + known Docker/MCP patterns
- Gmail MCP server: MEDIUM — package exists and is OK; endpoint path and transport activation details are ASSUMED

**Research date:** 2026-06-29
**Valid until:** 2026-07-29 (30 days — stable stack; @shinzolabs/gmail-mcp is active development, check for updates)
