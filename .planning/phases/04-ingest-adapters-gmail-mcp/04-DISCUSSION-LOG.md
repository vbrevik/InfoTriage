# Phase 4: Ingest adapters + Gmail MCP - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-29
**Phase:** 04-ingest-adapters-gmail-mcp
**Areas discussed:** Adapter invocation model, Gmail MCP client transport, Obsidian clip frontmatter schema, Local libs in Docker

---

## Adapter invocation model

| Option | Description | Selected |
|--------|-------------|----------|
| One-shot via docker compose run | Scheduler runs `docker compose run --rm` per tick; overlap detection = check container status | |
| Long-running daemon + APScheduler | Each adapter is a daemon; APScheduler fires internally; no separate scheduler container | |
| HTTP trigger endpoint | POST /run → 200 or 409; single-instance lock lives in adapter | ✓ |

**User's choice:** HTTP trigger endpoint

| Option | Description | Selected |
|--------|-------------|----------|
| FastAPI | Async-native, single POST /run route; pairs cleanly with aio-pika | ✓ |
| Flask | Sync-only; awkward alongside async aio-pika | |
| Bare http.server | Zero extra dependency but more boilerplate | |

**User's choice:** FastAPI

| Option | Description | Selected |
|--------|-------------|----------|
| 22010–22014 band | imap=22010, youtube=22011, gmail=22012, obsidian=22013, scheduler=22014 | ✓ |
| Internal-only, no host binding | Adapter trigger only on Docker network | |

**User's choice:** 22010–22014 band

| Option | Description | Selected |
|--------|-------------|----------|
| Python + APScheduler | Fires httpx POST /run per adapter per cron tick | ✓ |
| ofelia | Docker-aware cron sidecar; adds non-Python binary | |
| Supercronic + shell | Drop-in cron; curl-based; shell config | |

**User's choice:** Python + APScheduler

---

## Gmail MCP client transport

| Option | Description | Selected |
|--------|-------------|----------|
| mcp Python SDK over HTTP/SSE | Official `mcp` package; streamable-HTTP transport; library-managed session | |
| Raw httpx JSON-RPC calls | Direct JSON-RPC to :22025; transparent but duplicates protocol logic | ✓ |
| stdio subprocess | Run Node.js MCP server as subprocess inside adapter; loses :22025 boundary | |

**User's choice:** Raw httpx JSON-RPC calls

| Option | Description | Selected |
|--------|-------------|----------|
| gmail.readonly only | Minimum scope; satisfies NF-4 | |
| gmail.readonly + gmail.metadata | Adds label/thread metadata; still read-only | ✓ |
| Let Claude decide | Claude picks gmail.readonly | |

**User's choice:** gmail.readonly + gmail.metadata

| Option | Description | Selected |
|--------|-------------|----------|
| Write to .env, container mounts it | Provision script writes GMAIL_OAUTH2_REFRESH_TOKEN to .env; container uses env_file | ✓ |
| Write to credential file in data/ | credentials.json in data/gmail-oauth/; bind-mounted | |
| Inject via ARG | Violates NF-6 (bakes into image layer) | |

**User's choice:** Write to .env, container mounts it

---

## Obsidian clip frontmatter schema

| Option | Description | Selected |
|--------|-------------|----------|
| Obsidian Web Clipper (official) | Official browser extension; keys: title, url, date, tags, author, site, description | ✓ |
| MarkDownload | Browser extension; slightly different keys | |
| Custom / manual | Operator-defined keys | |

**User's choice:** Obsidian Web Clipper (official)

| Option | Description | Selected |
|--------|-------------|----------|
| Use defaults as-is | title→title, url→url, date→ts, site→source, description→summary; lang inferred | ✓ |
| Strict mapping — fail if missing | Error on absent required fields | |
| I'll specify exact keys | Custom mapping | |

**User's choice:** Use defaults as-is

| Option | Description | Selected |
|--------|-------------|----------|
| Infer from title text | Detect æ/ø/å → "no"; else "en"; fallback "und" | ✓ |
| Always "en" default | Simpler but wrong for NO clips | |
| Always "und" | Most honest; no inference logic | |

**User's choice:** Infer from title text

---

## Local libs in Docker

| Option | Description | Selected |
|--------|-------------|----------|
| COPY + pip install in each Dockerfile | Simple, no shared base; a libs change rebuilds that layer | ✓ |
| Shared base image | Faster adapter builds after base; easy to forget to rebuild base on lib changes | |
| Build wheels in CI | Explicit artifacts; more build script overhead | |

**User's choice:** COPY + pip install in each Dockerfile

| Option | Description | Selected |
|--------|-------------|----------|
| python:3.12-slim | Small, official; psycopg[binary] bundles libpq | ✓ |
| python:3.12-alpine | Smaller but musl/glibc compat issues for psycopg3 + numpy | |
| python:3.12 (full Debian) | Largest; only needed if gcc required (not here) | |

**User's choice:** python:3.12-slim

---

## Claude's Discretion

None — user made explicit choices for all options presented.

## Deferred Ideas

None — discussion stayed within phase scope.
