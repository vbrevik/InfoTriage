# Phase 4: Ingest adapters + Gmail MCP — Specification

**Created:** 2026-06-29
**Ambiguity score:** 0.166 (gate: ≤ 0.20)
**Requirements:** 7 locked

## Goal

Containerize the four working ingest bridges (imap, youtube, gmail-MCP, obsidian), wire them to the Postgres store + RabbitMQ bus from Phases 2–3, and retire the legacy IMAP-based Gmail bridge — so every source normalizes to `Item`, persists to Postgres+blobs, and publishes `item.ingested` without any host-run scripts.

## Background

Three host-run Python scripts exist today (`apps/ingest/imap_to_atom.py`, `yt_to_atom.py`, `gmail_to_atom.py`). They write Atom XML to `data/feeds/` for FreshRSS. None is integrated with Postgres or the bus. The Gmail script is a dead-end: the target account has 2-Step Verification ON and app passwords hard-blocked (ADR-008). No Docker containers, no scheduler, no `ingest-obsidian`, no `ingest-web` exist. Phase 4 bridges this gap: containerize, wire to bus+store, solve Gmail via OAuth2/MCP.

## Requirements

1. **ingest-imap container**: Multi-mailbox IMAP adapter runs as a Docker container, normalizes each message to `Item`, upserts to Postgres+blobs via `libs/store`, publishes `item.ingested` on the bus. No Atom XML written (email is triage-only — not projected to FreshRSS).
   - Current: `imap_to_atom.py` runs on host, writes Atom XML, no Postgres/bus integration
   - Target: Docker container reads all configured mailboxes, produces `Item` records in Postgres, publishes bus events; no `data/feeds/` output for IMAP sources
   - Acceptance: Given a configured test mailbox with ≥1 message, container run produces ≥1 `articles` row in Postgres and ≥1 `item.ingested` event consumed from the bus; no `data/feeds/imap-*.xml` file is created

2. **ingest-youtube container**: YouTube adapter runs as a Docker container using `yt-dlp`; transcription is stub-only (`transcribe=false`) because `mlx-whisper` requires macOS Metal (unavailable in Linux Docker). Normalizes each video to `Item`, upserts to Postgres+blobs, publishes `item.ingested`. Also writes `data/feeds/youtube-*.xml` Atom files for FreshRSS river browsing.
   - Current: `yt_to_atom.py` runs on host; transcription optional; writes Atom XML; no Postgres/bus
   - Target: Docker container fetches configured channels with stub transcription, produces `Item` rows in Postgres, publishes bus events, and writes `data/feeds/youtube-*.xml`
   - Acceptance: Given a configured test channel, container run produces ≥1 `articles` row, ≥1 `item.ingested` bus event, and a non-empty `data/feeds/youtube-*.xml` file; `Item.body_ref` points to a valid blob path

3. **ingest-gmail (MCP/OAuth2)**: Self-hosted Gmail MCP server (`@googleapis/mcp-server-google-workspace` or equivalent official package) runs as a Docker container on `127.0.0.1:22025`, holding the OAuth2 refresh token (from `.env` only). A thin `ingest-gmail` MCP client adapter container calls it, normalizes Gmail messages to `Item`, upserts to Postgres+blobs, publishes `item.ingested`. A one-time OAuth2 provision script ships with Phase 4. Legacy `apps/ingest/gmail_to_atom.py` is retired (deleted).
   - Current: `gmail_to_atom.py` uses IMAP + app password — hard-blocked on 2SV account; no MCP server, no OAuth2 token provisioned
   - Target: Gmail MCP server running on :22025 with pre-provisioned refresh token; `ingest-gmail` adapter reads via MCP, produces `Item` rows, publishes bus events; `gmail_to_atom.py` deleted
   - Acceptance: Gmail MCP server container starts healthy; adapter run produces ≥1 `articles` row with `source_type="gmail"` and ≥1 `item.ingested` bus event; `apps/ingest/gmail_to_atom.py` does not exist in the repo

4. **ingest-obsidian container**: Reads `$OBSIDIAN_VAULT_PATH/articles-inbox/*.md` via Docker bind-mount, normalizes each clip to `Item`, upserts to Postgres+blobs, publishes `item.ingested`. Poll-based (checks for new/modified files on each scheduler trigger).
   - Current: No Obsidian adapter exists
   - Target: Docker container with `OBSIDIAN_VAULT_PATH` bind-mounted reads Markdown clips, produces `Item` rows with frontmatter fields mapped via `libs/contracts` codec, publishes bus events
   - Acceptance: Given ≥1 `.md` file in `$OBSIDIAN_VAULT_PATH/articles-inbox/`, container run produces ≥1 `articles` row with `source_type="obsidian"` and ≥1 `item.ingested` event

5. **Scheduler container**: A single scheduler container fires each ingest adapter (imap, youtube, gmail, obsidian) on a per-adapter configurable cron schedule. If an adapter's previous run is still in progress when the next trigger fires, the new invocation is skipped with a log warning (single-instance lock per adapter).
   - Current: No scheduler; adapters are manual one-shot host scripts
   - Target: Docker scheduler container with per-adapter cron expressions in config/env; adapters run as short-lived tasks; overlapping runs skipped
   - Acceptance: Scheduler starts all four adapters on their configured schedules; when a test adapter sleep is injected to simulate a long run, the next scheduled invocation is logged as skipped rather than started concurrently

6. **Upsert idempotency**: Re-running any adapter with the same source data produces no duplicate `articles` rows and no duplicate `item.ingested` bus events. Identity key is source URL + provider message-id (IMAP UID / Gmail message ID / YouTube video ID / file path for Obsidian).
   - Current: No dedup — re-running scripts would produce duplicate Atom entries
   - Target: `libs/store` upsert (ON CONFLICT DO UPDATE) on `articles.url`; adapters always call upsert (not insert), always republish bus event only if row was newly inserted
   - Acceptance: Running an adapter twice against the same source data leaves exactly the same number of `articles` rows after both runs; `item.ingested` event count matches new-inserts only

7. **Legacy gmail_to_atom.py retired**: `apps/ingest/gmail_to_atom.py` is deleted from the repo as part of Phase 4, once `ingest-gmail` MCP path is functional.
   - Current: File exists at `apps/ingest/gmail_to_atom.py`
   - Target: File does not exist; no references to it remain in docker-compose or README (except as a historical note in ADR-008)
   - Acceptance: `git ls-files apps/ingest/gmail_to_atom.py` returns empty; `docker-compose.yml` contains no reference to it

## Boundaries

**In scope:**
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

**Out of scope:**
- `ingest-web` (direct HTTP scraper) — deferred to Phase 5+; no existing script to wrap
- Real mlx-whisper transcription in Docker — mlx requires macOS Metal; deferred until a macOS container or host-delegation pattern is designed
- Atom XML for IMAP or Gmail — per architecture decision: email is triage-only, not projected to FreshRSS
- FreshRSS Atom for `ingest-obsidian` — Obsidian clips go to SAB/Obsidian output (Phase 6), not FreshRSS
- LLM scoring, PMESII/TESSOC enrichment — Phase 5 (triage app)
- Container healthchecks, structured logging, DLQ ops — Phase 7
- Multi-user / team-server concerns — Milestone 3

## Constraints

- All adapters must be **read-only** against source systems: no STORE/EXPUNGE/DELETE/send/mark on IMAP; no write operations via Gmail MCP; no writes to Obsidian vault (NF-4, ADR-008)
- **No cloud LLM** (ADR-004) — adapters normalize + persist only; no LLM calls at ingest time
- Gmail MCP server port `:22025` must be **localhost-only** (`127.0.0.1:22025:...` in docker-compose; not `0.0.0.0`)
- OAuth2 refresh tokens, IMAP app passwords, and all credentials live in `.env` only — **never committed to git, never baked into Docker image layers** (NF-6)
- `ingest-youtube`: `transcribe=false` forced; `mlx-whisper` not installed in the container (Apple Silicon Metal unavailable in Linux Docker)
- All persistence via `libs/store` interface (ADR-001); direct Postgres calls from adapters are forbidden
- Bus publish via `libs/contracts` aio-pika BusClient from Phase 3 (ADR-007)

## Acceptance Criteria

- [ ] `ingest-imap` container run produces ≥1 `articles` row + ≥1 `item.ingested` bus event from a configured test mailbox; no `data/feeds/imap-*.xml` created
- [ ] `ingest-youtube` container run produces ≥1 `articles` row + ≥1 `item.ingested` event + non-empty `data/feeds/youtube-*.xml`; `Item.body_ref` points to a valid blob
- [ ] Gmail MCP server starts healthy on `127.0.0.1:22025`; `ingest-gmail` adapter produces ≥1 `articles` row with `source_type="gmail"` + ≥1 `item.ingested` event
- [ ] OAuth2 provision script completes browser flow and writes refresh token to `.env`; token not present in any git-tracked file
- [ ] `ingest-obsidian` container run produces ≥1 `articles` row with `source_type="obsidian"` + ≥1 `item.ingested` event from `articles-inbox/*.md`
- [ ] Scheduler fires all 4 adapters on their configured schedules; overlapping invocations are skipped with a log warning (no concurrent runs of same adapter)
- [ ] Running any adapter twice against identical source data: `articles` row count unchanged after second run; `item.ingested` event published only on first (new-insert) run
- [ ] `git ls-files apps/ingest/gmail_to_atom.py` returns empty
- [ ] All 6 new containers appear in `docker-compose.yml`; Gmail MCP port entry uses `127.0.0.1:22025:...`
- [ ] MUST NOT: No adapter writes to, marks, deletes, or modifies any source item — verified by grep for `STORE`/`EXPUNGE`/`DELETE`/`send_message`/`mark_read` in adapter source + Gmail MCP client uses read-only OAuth2 scope
- [ ] MUST NOT: No credential appears in any git-tracked file or Docker image layer — verified by grep on committed files and Dockerfile inspection (no `ARG`/`ENV` bearing credential values at build time)
- [ ] MUST NOT: `docker-compose.yml` Gmail MCP port entry is `127.0.0.1:22025:...` not `22025:...`

## Edge Coverage

**Coverage:** 7/21 applicable edges resolved · 11 dismissed · 3 backstop

| Category | Requirement | Status | Resolution / Reason |
|----------|-------------|--------|---------------------|
| adjacency | R1 | ✅ covered | Acceptance criterion #7: upsert idempotency on IMAP message-id / URL |
| adjacency | R2 | ✅ covered | Acceptance criterion #7: upsert idempotency on YouTube video ID |
| adjacency | R3 | ✅ covered | Acceptance criterion #7: upsert idempotency on Gmail message ID |
| adjacency | R4 | ✅ covered | Acceptance criterion #7: upsert idempotency on file path |
| adjacency | R5 | ✅ covered | Acceptance criterion #6: single-instance lock; overlapping run skipped |
| adjacency | R6 | 🧪 backstop | `libs/store` handles content-addressed blob dedup by hash; held-out integration test: same blob path inserted twice yields one blob file |
| empty | R1 | 🧪 backstop | Adapter exits 0 with "no new items" log; held-out test: empty mailbox → 0 rows inserted, 0 bus events |
| empty | R2 | 🧪 backstop | Same: empty channel → 0 rows, 0 events |
| empty | R3 | dismissed | Empty Gmail query: exits 0 silently — routine engineering |
| empty | R4 | dismissed | Empty articles-inbox/: exits 0 silently — routine engineering |
| empty | R5 | dismissed | No adapters configured: scheduler idles — trivial |
| empty | R6 | dismissed | Empty Item is impossible; adapters construct Item before calling store |
| empty | R7 | dismissed | R7 is a scope/boundary statement, not functional |
| ordering | R1 | dismissed | Items are independent; bus order not specified |
| ordering | R2 | dismissed | Items are independent; bus order not specified |
| ordering | R3 | dismissed | Items are independent; bus order not specified |
| ordering | R4 | dismissed | Items are independent; bus order not specified |
| ordering | R5 | dismissed | Schedule trigger order not specified; adapters are independent |
| ordering | R6 | dismissed | Blob writes are independent; order irrelevant |
| adjacency | R7 | dismissed | R7 is a scope/boundary statement |
| ordering | R7 | dismissed | R7 is a scope/boundary statement |

## Prohibitions (must-NOT)

**Coverage:** 3/3 applicable prohibitions resolved · 0 unresolved

| Prohibition (must-NOT statement) | Requirement | Status | Verification / Reason |
|----------------------------------|-------------|--------|------------------------|
| MUST NOT write to, mark, delete, or modify any item in any source system (Gmail, IMAP, Obsidian vault) | R1, R3, R4 | resolved | verification: test — grep adapter source for `STORE`/`EXPUNGE`/`DELETE`/`send_message`/`mark_read`; Gmail MCP client uses read-only OAuth2 scope |
| MUST NOT store OAuth2 refresh tokens, app passwords, or IMAP credentials in any git-tracked file or bake them into Docker image layers | R3, R1 | resolved | verification: test — grep all git-tracked files for credential patterns; Dockerfile inspection: no `ARG`/`ENV` with credential values at build time |
| MUST NOT bind Gmail MCP server port :22025 to 0.0.0.0 | R3 | resolved | verification: test — `docker-compose.yml` port entry for Gmail MCP must be `127.0.0.1:22025:...`; grep for `"22025:"` (without host prefix) must return empty |

## Ambiguity Report

| Dimension          | Score | Min  | Status | Notes                                          |
|--------------------|-------|------|--------|------------------------------------------------|
| Goal Clarity       | 0.88  | 0.75 | ✓      | 4 containers + Gmail MCP + scheduler specified |
| Boundary Clarity   | 0.88  | 0.70 | ✓      | ingest-web / real transcription explicit OOS   |
| Constraint Clarity | 0.78  | 0.65 | ✓      | read-only, no MLX, localhost port, libs/store  |
| Acceptance Criteria| 0.75  | 0.70 | ✓      | 12 pass/fail criteria                          |
| **Ambiguity**      | 0.166 | ≤0.20| ✓      |                                                |

## Interview Log

| Round | Perspective      | Question summary                        | Decision locked                                              |
|-------|------------------|-----------------------------------------|--------------------------------------------------------------|
| 1     | Researcher       | ingest-web scope?                       | Direct HTTP scraper — but NOT in Phase 4 (see round 2)       |
| 1     | Researcher       | Obsidian vault mount?                   | Docker bind-mount, OBSIDIAN_VAULT_PATH env var               |
| 1     | Researcher       | Gmail MCP implementation?               | Official `@googleapis/mcp-server-google-workspace`           |
| 2     | Researcher       | How are adapters triggered?             | Separate scheduler container (cron, per-adapter config)      |
| 2     | Simplifier       | Must-ship adapters?                     | All 4: imap, youtube, gmail, obsidian (ingest-web deferred)  |
| 2     | Simplifier       | Atom output after containerization?     | Dual output: Atom (YT only) + bus                            |
| 3     | Boundary Keeper  | mlx-whisper in Docker on Mac?           | transcribe=false in Phase 4; mlx deferred                    |
| 3     | Boundary Keeper  | OAuth2 provision script in scope?       | Yes — one-time setup script ships with Phase 4               |
| 3     | Boundary Keeper  | IMAP Atom output?                       | Email triage-only; no Atom for IMAP or Gmail                 |
| 5.5   | Edge probe       | Duplicate item handling?                | Upsert (overwrite if newer) via libs/store                   |
| 5.5   | Edge probe       | Schedule overlap?                       | Single-instance lock — skip overlapping run                  |
| 5.6   | Prohibition probe| Read-only constraint?                   | Resolved/test: grep for write calls in adapter source        |
| 5.6   | Prohibition probe| Credential hygiene?                     | Resolved/test: grep committed files + Dockerfile inspection  |
| 5.6   | Prohibition probe| Port :22025 localhost-only?             | Resolved/test: verify 127.0.0.1 prefix in docker-compose    |

---

*Phase: 04-ingest-adapters-gmail-mcp*
*Spec created: 2026-06-29*
*Next step: /gsd-discuss-phase 4 — implementation decisions (Gmail MCP server choice, scheduler tech, libs/store upsert contract, container image strategy)*
