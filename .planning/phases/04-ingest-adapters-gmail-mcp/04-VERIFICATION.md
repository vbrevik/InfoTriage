---
phase: 04-ingest-adapters-gmail-mcp
verified: 2026-06-29T12:53:16Z
status: human_needed
score: 26/26 must-haves verified
behavior_unverified: 0
overrides_applied: 0
deferred:
  - truth: "ingest-web container normalizes web sources to Item, persists to Postgres+blobs, publishes item.ingested"
    addressed_in: "Phase 5+ (deferred per SPEC)"
    evidence: "04-SPEC.md line 68: 'ingest-web (direct HTTP scraper) — deferred to Phase 5+'; 04-CONTEXT.md line 34 identical. ROADMAP SC1 was written before SPEC narrowed scope."
human_verification:
  - test: "docker compose up — build and start all 6 Phase 4 services (ingest-imap, ingest-youtube, ingest-gmail, ingest-obsidian, gmail-mcp-server, scheduler)"
    expected: "All 6 containers start without build errors; health checks pass; scheduler logs show cron jobs registered"
    why_human: "Requires Docker daemon, image builds, and live Postgres+RabbitMQ services — cannot simulate in unit tests"
  - test: "Trigger ingest-imap via POST localhost:22010/run against a configured mailbox"
    expected: "Response 200 {status: started}; >=1 row in articles table with source_type=imap; >=1 item.ingested event on RabbitMQ; no imap-*.xml file written under data/feeds/"
    why_human: "Requires live IMAP server + Postgres + RabbitMQ; mailbox credentials needed"
  - test: "Trigger ingest-youtube via POST localhost:22011/run against a configured channel"
    expected: ">=1 row in articles table with source_type=yt; body_ref set and blob readable; non-empty youtube-*.xml written to data/feeds/; >=1 item.ingested event"
    why_human: "Requires yt-dlp in container, live Postgres+RabbitMQ, and a reachable YouTube channel"
  - test: "Provision Gmail OAuth2 token via scripts/provision_gmail_oauth.py, then trigger ingest-gmail via POST localhost:22012/run"
    expected: "MCP server starts (PORT=3000 HTTP transport); >=1 gmail row in articles table; >=1 item.ingested event; token not printed to stdout"
    why_human: "Requires live Gmail OAuth2 browser flow, running gmail-mcp-server container, Postgres+RabbitMQ"
  - test: "Drop >=1 Obsidian Web Clipper .md clip into the articles-inbox vault dir and trigger ingest-obsidian via POST localhost:22013/run"
    expected: ">=1 row with source_type=obsidian, D-09 field mapping (title, url, site→source, description→summary), correct lang inference"
    why_human: "Requires live vault mount, Postgres+RabbitMQ, and real clip files"
  - test: "Let the scheduler run for one cycle; verify it fires adapters on cron and handles a 409 (re-trigger while first is in-flight)"
    expected: "Scheduler logs '[name] started (200)' on first trigger; logs '[name] skipped — already running (409)' on overlap; no duplicate ingest run started"
    why_human: "Requires live stack + real time passage for cron to fire; behavioral invariant is time-dependent"
---

# Phase 04: Ingest Adapters + Gmail MCP — Verification Report

**Phase Goal:** Containerize all four ingest adapters (IMAP, YouTube, Obsidian, Gmail-via-MCP) using a shared ingest_common library, wire them into docker-compose with a cron scheduler, and retire the legacy gmail_to_atom.py.
**Verified:** 2026-06-29T12:53:16Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | persist_and_publish calls get_item BEFORE put_item; publishes item.ingested exactly once for new item; returns True on new, False on duplicate (R6 idempotency) | VERIFIED | persist.py lines 37-56: get_item pre-check is sole newness signal; 3/3 idempotency tests pass |
| 2 | POST /run returns 200+started (idle) or 409+already_running (in-flight); flag set synchronously before first await (no race window); flag cleared in finally | VERIFIED | trigger.py lines 79-88: synchronous flag check-and-set; test_trigger_200_then_409_then_200 PASSES |
| 3 | GET /health returns 200 regardless of run state | VERIFIED | trigger.py lines 90-93; test_trigger_health_always_200 PASSES |
| 4 | ingest-imap: >=1 articles row + >=1 item.ingested, source_type="imap" (SPEC R1) | VERIFIED | test_ingest_r1_dual_output passes: 2 messages → 2 rows, 2 events, source_type="imap" |
| 5 | ingest-imap NEVER writes data/feeds/imap-*.xml (email is triage-only, SPEC R1) | VERIFIED | grep data/feeds in imap_ingest.py + main.py → 0 matches |
| 6 | ingest-imap re-run leaves row count unchanged, publishes no second event (R6) | VERIFIED | test_ingest_r1_idempotency passes |
| 7 | ingest-imap empty mailbox: 0 rows, 0 events, no exception (R1-empty backstop) | VERIFIED | test_ingest_r1_empty_mailbox passes |
| 8 | ingest-youtube: >=1 row, >=1 event, non-empty youtube-*.xml; source_type="yt"; Item.body_ref set (SPEC R2) | VERIFIED | test_ingest_r2_dual_output passes: 2 videos → 2 rows, 2 events, Atom XML written, body_ref resolved |
| 9 | Item.body_ref points to valid blob; get_blob(body_ref) returns stored bytes | VERIFIED | test_ingest_r2_dual_output: each body_ref verified via store.get_blob |
| 10 | ingest-youtube transcribe forced false; mlx-whisper never invoked or installed (SPEC R2 constraint) | VERIFIED | grep mlx_whisper/openai-whisper/fetch_audio in youtube_ingest.py + Dockerfile + requirements.txt → 0 non-comment matches |
| 11 | ingest-youtube re-run leaves row count unchanged (R6) | VERIFIED | test_ingest_r2_idempotent_rerun passes |
| 12 | ingest-youtube empty channel: 0 rows, 0 events, no exception (R2-empty backstop) | VERIFIED | test_ingest_r2_empty_channel passes |
| 13 | Same transcript bytes twice → exactly one blob file (content-addressed dedup, R6) | VERIFIED | test_blob_dedup_same_content_one_file passes |
| 14 | ingest-obsidian: >=1 row, source_type="obsidian", >=1 item.ingested (SPEC R4) | VERIFIED | test_ingest_d09_field_mapping: 2 clips → 2 rows, 2 events, correct source_type |
| 15 | Obsidian Web Clipper frontmatter mapped via from_frontmatter (D-09): title/url/date/site/description/lang | VERIFIED | test_ingest_d09_field_mapping verifies each mapped field; Norwegian clip lang="no" |
| 16 | Missing required fields (title/url/date) fall back to safe defaults; clip NOT rejected; warning logged | VERIFIED | test_ingest_missing_fields_not_rejected passes + caplog confirms WARNING |
| 17 | ingest-obsidian re-run leaves row count unchanged (R4/R6) | VERIFIED | test_ingest_idempotency passes |
| 18 | Gmail MCP server (@shinzolabs/gmail-mcp@1.7.4) HTTP transport mode via PORT env; no credential values baked in | VERIFIED | gmail-mcp-server/Dockerfile: npm install @shinzolabs/gmail-mcp@1.7.4 + COPY entrypoint.sh; entrypoint.sh line 11: export PORT="${PORT:-3000}"; grep credential ARG/ENV → CLEAN |
| 19 | ingest-gmail: MCP session init + read-only tools via httpx JSON-RPC; source_type="gmail"; >=1 row + >=1 event (SPEC R3) | VERIFIED | test_ingest_r3_gmail passes: mocked MCP → 1 row, 1 event, source_type="gmail"; no Python MCP SDK imported |
| 20 | OAuth2 provision script requests gmail.readonly + gmail.metadata only (D-06, ADR-008) | VERIFIED | provision_gmail_oauth.py lines 29-30: gmail.readonly + gmail.metadata; grep gmail.send/modify/compose → 0 matches |
| 21 | apps/ingest/gmail_to_atom.py no longer exists; no reference in docker-compose.yml or README (SPEC R7) | VERIFIED | git ls-files apps/ingest/gmail_to_atom.py → empty; grep gmail_to_atom docker-compose.yml README.md → 0 matches |
| 22 | ingest-gmail re-run leaves row count unchanged (R3/R6) | VERIFIED | test_ingest_r3_idempotency passes |
| 23 | Scheduler fires all 4 adapters on per-adapter cron schedules via APScheduler 3.x BackgroundScheduler + CronTrigger.from_crontab (SPEC R5, D-04) | VERIFIED | test_scheduler.py: 9 tests pass; imports verified BackgroundScheduler from apscheduler.schedulers.background; no AsyncIOScheduler/4.x API |
| 24 | When adapter returns 409, scheduler logs "skipped — already running"; no second invocation started (SPEC R5 adjacency) | VERIFIED | test_overlapping_run_409_logged_as_skipped passes |
| 25 | docker-compose.yml defines all 6 new services on infotriage network; Gmail MCP port is 127.0.0.1:22025:3000 (localhost-only); adapter ports 22010–22014 localhost-only; vault mount :ro; env_file for all new services | VERIFIED | docker-compose.yml lines 91-238: all 6 services present; 127.0.0.1:22025:3000 confirmed; grep bare 22025:3000 → 0 matches; vault :ro at line 207 |
| 26 | All credentials (Postgres/RabbitMQ/Gmail OAuth2/IMAP passwords) reach containers via env_file only; no credential values in ARG/ENV in any Dockerfile | VERIFIED | grep credential ARG/ENV in all 5 new Dockerfiles + gmail-mcp-server/Dockerfile → CLEAN; env_file: required:false on all 6 services |

**Score:** 26/26 truths verified

### Deferred Items

Items not yet met but explicitly excluded from Phase 4 scope in the SPEC — not actionable gaps.

| # | Item | Addressed In | Evidence |
|---|------|-------------|----------|
| 1 | ingest-web container (direct HTTP scraper) normalizes web sources to Item | Phase 5+ | ROADMAP SC1 lists it, but 04-SPEC.md line 68 explicitly: "ingest-web (direct HTTP scraper) — deferred to Phase 5+"; 04-CONTEXT.md line 34 confirms. ROADMAP SC1 was written before SPEC narrowed scope. |

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `libs/ingest_common/src/ingest_common/persist.py` | Idempotent persist+publish helper | VERIFIED | 57-line implementation; get_item pre-check pattern |
| `libs/ingest_common/src/ingest_common/trigger.py` | FastAPI single-instance lock app factory | VERIFIED | 96-line implementation; synchronous flag, finally cleanup |
| `libs/ingest_common/src/ingest_common/runtime.py` | Env-driven store/bus constructors | VERIFIED | build_store + build_bus reading env vars; DSN never logged |
| `libs/ingest_common/pyproject.toml` | Package definition | VERIFIED | name=ingest_common, version=0.1.0, setuptools src-layout |
| `tests/test_ingest_idempotency.py` | Idempotency unit tests | VERIFIED | 3 tests, all pass |
| `tests/test_trigger_lock.py` | Concurrency lock unit tests | VERIFIED | 3 tests, all pass |
| `apps/ingest-imap/imap_ingest.py` | IMAP fetch → Item | VERIFIED | read-only (readonly=True); no Atom output; source_type="imap" |
| `apps/ingest-imap/main.py` | Trigger app wiring | VERIFIED | make_trigger_app(ingest, name="ingest-imap") |
| `apps/ingest-imap/Dockerfile` | Container definition | VERIFIED | python:3.12-slim; pip install --no-deps 3 libs; uvicorn :8000 |
| `apps/ingest-imap/requirements.txt` | Dependencies | VERIFIED | fastapi, uvicorn, aio-pika, psycopg[binary], etc. |
| `tests/test_ingest_imap.py` | R1 + empty-mailbox tests | VERIFIED | 3 tests, all pass |
| `apps/ingest-youtube/youtube_ingest.py` | YouTube → Item + blob + Atom | VERIFIED | dual output; stub transcription; source_type="yt"; write_atom |
| `apps/ingest-youtube/_util.py` | escape() helper copy | VERIFIED | file exists; used by write_atom |
| `apps/ingest-youtube/main.py` | Trigger app wiring | VERIFIED | make_trigger_app(ingest, name="ingest-youtube") |
| `apps/ingest-youtube/Dockerfile` | Container definition | VERIFIED | python:3.12-slim; yt-dlp; no whisper; pip --no-deps 3 libs |
| `apps/ingest-youtube/requirements.txt` | Dependencies | VERIFIED | includes yt-dlp; no mlx-whisper/openai-whisper |
| `tests/test_ingest_youtube.py` | R2 + blob-dedup + empty tests | VERIFIED | 5 tests, all pass |
| `apps/ingest-obsidian/obsidian_ingest.py` | Clip → Item (D-09) | VERIFIED | _infer_lang; from_frontmatter; read-only vault; fallback defaults |
| `apps/ingest-obsidian/main.py` | Trigger app wiring | VERIFIED | make_trigger_app(ingest, name="ingest-obsidian") |
| `apps/ingest-obsidian/Dockerfile` | Container definition | VERIFIED | python:3.12-slim; pip --no-deps 3 libs; uvicorn :8000 |
| `apps/ingest-obsidian/requirements.txt` | Dependencies | VERIFIED | no google/youtube/whisper libs |
| `tests/test_ingest_obsidian.py` | R4 + missing-field tests | VERIFIED | 3 tests, all pass |
| `gmail-mcp-server/Dockerfile` | Node.js MCP server container | VERIFIED | node:22-slim; @shinzolabs/gmail-mcp@1.7.4; no credential ARG/ENV |
| `gmail-mcp-server/entrypoint.sh` | HTTP transport activation | VERIFIED | export PORT="${PORT:-3000}"; exec npx @shinzolabs/gmail-mcp |
| `scripts/provision_gmail_oauth.py` | One-time OAuth2 setup | VERIFIED | gmail.readonly + gmail.metadata only; writes GMAIL_OAUTH2_REFRESH_TOKEN to .env; does not print token |
| `apps/ingest-gmail/mcp_client.py` | Raw httpx JSON-RPC MCP client | VERIFIED | initialize + Mcp-Session-Id; tools/call with list_messages + get_message only; no Python MCP SDK |
| `apps/ingest-gmail/gmail_ingest.py` | Gmail → Item | VERIFIED | source_type="gmail"; persist_and_publish; store as context manager |
| `apps/ingest-gmail/main.py` | Trigger app wiring | VERIFIED | make_trigger_app(ingest, name="ingest-gmail") |
| `apps/ingest-gmail/Dockerfile` | Container definition | VERIFIED | python:3.12-slim; pip --no-deps 3 libs; uvicorn :8000 |
| `apps/ingest-gmail/requirements.txt` | Dependencies | VERIFIED | httpx; no MCP SDK |
| `tests/test_ingest_gmail.py` | R3 + idempotency tests | VERIFIED | 5 tests, all pass |
| `apps/scheduler/scheduler_main.py` | APScheduler 3.x cron driver | VERIFIED | BackgroundScheduler; CronTrigger.from_crontab; sync httpx; 4 adapters |
| `apps/scheduler/main.py` | Scheduler entrypoint | VERIFIED | builds+starts scheduler; blocks; graceful shutdown |
| `apps/scheduler/Dockerfile` | Container definition | VERIFIED | python:3.12-slim; requirements.txt; CMD python main.py |
| `apps/scheduler/requirements.txt` | Dependencies | VERIFIED | apscheduler>=3.11,<4; httpx>=0.27 |
| `tests/test_scheduler.py` | R5 + 409-skip tests | VERIFIED | 9 tests, all pass |
| `docker-compose.yml` | 6 new services | VERIFIED | all 6 services with correct ports, env_file, mounts, depends_on |
| `.env.example` | Phase 4 env vars documented | VERIFIED | all new vars present; GMAIL_APP_PASSWORD absent |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `apps/ingest-imap/main.py` | `libs/ingest_common/trigger.py` | `make_trigger_app(ingest, name="ingest-imap")` | WIRED | main.py imports make_trigger_app and wires ingest coroutine |
| `apps/ingest-imap/imap_ingest.py` | `libs/ingest_common/persist.py` | `await persist_and_publish(store, bus, item)` | WIRED | imap_ingest.py line 182 |
| `imap_ingest.ingest()` | `libs/ingest_common/runtime.py` | `build_store() + build_bus()` | WIRED | imap_ingest.py lines 176-178 |
| `apps/ingest-youtube/youtube_ingest.py` | `libs/ingest_common/persist.py` | `await persist_and_publish(store, bus, item)` | WIRED | youtube_ingest.py line 188 |
| `youtube_ingest.ingest()` | `store._protocol.put_blob` | `body_ref = store.put_blob(text.encode())` | WIRED | youtube_ingest.py line 176 |
| `apps/ingest-obsidian/obsidian_ingest.py` | `libs/contracts._codec.from_frontmatter` | `fm = from_frontmatter(text)` | WIRED | obsidian_ingest.py line 77 |
| `apps/ingest-gmail/gmail_ingest.py` | `apps/ingest-gmail/mcp_client.py` | `await mcp_client.init_mcp_session(client)` + `list_messages` + `get_message` | WIRED | gmail_ingest.py lines 131-150 |
| `apps/ingest-gmail/mcp_client.py` | gmail-mcp-server | `POST {GMAIL_MCP_URL}/mcp` JSON-RPC 2.0 with Mcp-Session-Id | WIRED | mcp_client.py lines 59-74 |
| `apps/scheduler/scheduler_main.py` | all 4 adapter /run endpoints | `httpx.Client.post(url)` in fire_adapter | WIRED | scheduler_main.py lines 55-56; ADAPTERS dict maps 4 adapter URLs |
| `docker-compose.yml` | all 6 new Dockerfiles | `build: { context: ., dockerfile: apps/.../Dockerfile }` | WIRED | All 6 services use project-root build context per RESEARCH Pitfall 2 |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|-------------------|--------|
| `imap_ingest.ingest()` | items (list[Item]) | IMAP fetch via imaplib (mocked in tests; real in container) | Yes (MAILBOXES env → imaplib IMAP4_SSL) | FLOWING |
| `youtube_ingest.ingest()` | items + body_ref | yt_dlp_list subprocess + store.put_blob (mocked in tests) | Yes (YT_CHANNELS → yt-dlp → blob store) | FLOWING |
| `obsidian_ingest.ingest()` | items from glob | OBSIDIAN_VAULT_PATH → *.md files → from_frontmatter | Yes (real file reads) | FLOWING |
| `gmail_ingest.ingest()` | raw_messages list | MCP session → list_messages → get_message (mocked in tests) | Yes (GMAIL_MCP_URL → JSON-RPC) | FLOWING |
| `scheduler_main.fire_adapter()` | HTTP response | httpx.Client.post to adapter /run URLs | Yes (real HTTP POST in production) | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Lock invariant: 200→409→200 sequence (behavior-dependent truth) | `pytest tests/test_trigger_lock.py::test_trigger_200_then_409_then_200 -v` | 1 passed | PASS |
| All Phase 4 unit tests | `pytest tests/test_ingest_idempotency.py tests/test_trigger_lock.py tests/test_ingest_imap.py tests/test_ingest_youtube.py tests/test_ingest_obsidian.py tests/test_ingest_gmail.py tests/test_scheduler.py -q` | 31 passed | PASS |
| Full test suite (without live services) | `pytest tests/ -m "not db_live and not rabbitmq" -q` | 183 passed, 12 deselected | PASS |
| ingest_common importable (pytest path) | `python3 -c "import sys; sys.path.insert(0,'libs/ingest_common/src'); import ingest_common"` | ok | PASS |
| gmail_to_atom.py absent from git tree | `git ls-files apps/ingest/gmail_to_atom.py` | (empty) | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| ADR-003 | All plans | Containerized Collection adapters on Postgres+bus architecture | SATISFIED | 4 adapter containers + scheduler; all wire to Postgres+RabbitMQ |
| ADR-004 (read-only) | Plans 02, 03, 04 | Read-only against all source systems | SATISFIED | IMAP readonly=True; yt-dlp public-channel only; vault :ro mount; no write methods called |
| ADR-008 (MCP/OAuth2) | Plan 05 | Gmail via OAuth2+MCP; token in env only | SATISFIED | @shinzolabs/gmail-mcp@1.7.4; gmail.readonly+metadata scopes; no credential ARG/ENV; localhost-only :22025 |
| C-9 (YouTube yt-dlp) | Plan 03 | YouTube channels via yt-dlp | SATISFIED | ingest-youtube installs yt-dlp; yt_dlp_list subprocess call |
| C-13 (Multi-mailbox IMAP) | Plan 02 | Multi-mailbox IMAP ingestion | SATISFIED | ingest-imap handles multiple mailboxes from MAILBOXES env |
| NF-4 (read-only Gmail) | Plan 02/05 | Read-only against source systems | SATISFIED | IMAP readonly=True; Gmail read-only OAuth2 scopes |
| NF-6 (.env external) | Plan 06 | .env is external/gitignored | SATISFIED | env_file: required:false on all 6 services; no secret values in any Dockerfile |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `pip show ingest_common` | N/A | Editable install points to deleted worktree path: `.claude/worktrees/agent-a1766265e34394007/libs/ingest_common` | WARNING | `python3 -c "import ingest_common"` fails outside pytest; tests pass via pyproject.toml pythonpath (libs/ingest_common/src); Docker containers install correctly via `pip install --no-deps /build/ingest_common`. Fix: run `pip install -e libs/ingest_common` from project root. |

No TBD/FIXME/XXX markers found in any Phase 4 files.
No stub implementations found — all code paths are wired.

### Prohibition Verification

| Prohibition | Verification Method | Result |
|-------------|---------------------|--------|
| IMAP MUST NOT write to mailbox (no STORE/EXPUNGE/COPY/APPEND; select readonly) | `grep -niE '\.store\(|\.expunge\(|\.copy\(|\.append\(' imap_ingest.py \| grep -vE comment` | CLEAN |
| IMAP MUST NOT write data/feeds/imap-*.xml | `grep -c data/feeds imap_ingest.py main.py` | 0 matches |
| YouTube MUST NOT install/invoke mlx-whisper | `grep -niE 'mlx_whisper|mlx-whisper|openai-whisper|fetch_audio' youtube_ingest.py Dockerfile requirements.txt` | CLEAN |
| YouTube MUST NOT use YouTube credentials | `grep -niE '^(ARG|ENV)\s+\S*(PASSWORD|SECRET|TOKEN|YOUTUBE|GOOGLE)\s*=' Dockerfile` | CLEAN |
| Obsidian MUST NOT write to vault | `grep -nE 'open\([^,)]*,\s*["\x27][wa]' obsidian_ingest.py` | CLEAN |
| Obsidian MUST use yaml.safe_load only (via from_frontmatter) | `grep -nE 'yaml\.load\(' obsidian_ingest.py` | CLEAN |
| Gmail MUST NOT invoke write/mutate tools | `grep -niE 'send_message|create_draft|trash|modify_message|delete_message|mark_read|markAsRead' mcp_client.py gmail_ingest.py` | CLEAN |
| OAuth2 refresh token MUST NOT be in git-tracked file | `git ls-files .env client_secrets.json` | CLEAN |
| Gmail MCP port MUST NOT bind to 0.0.0.0 | `grep '22025:3000' docker-compose.yml \| grep -v 127.0.0.1` | CLEAN |
| No credential values in image layers | `grep -niE '^(ARG|ENV)\s+\S*(SECRET|REFRESH_TOKEN|CLIENT_ID)\s*=\S' */Dockerfile` | CLEAN |

### Human Verification Required

#### 1. Docker compose build and start

**Test:** Run `docker compose up --build` from project root
**Expected:** All 6 new service images build without error; containers start; health checks on postgres and rabbitmq pass; scheduler logs show 4 cron jobs registered
**Why human:** Requires Docker daemon, network stack, and live service start — unit tests mock all of this

#### 2. Live IMAP ingest run

**Test:** Configure MAILBOXES env with a real mailbox; POST to localhost:22010/run; check Postgres articles table
**Expected:** >=1 row with source_type="imap"; >=1 item.ingested event in RabbitMQ; no data/feeds/imap-*.xml created; second POST triggers 409 if run still in-flight
**Why human:** Requires live IMAP credentials and a running Postgres+RabbitMQ stack

#### 3. Live YouTube ingest run

**Test:** Configure YT_CHANNELS env; POST to localhost:22011/run; check articles table and data/feeds/
**Expected:** >=1 row with source_type="yt"; body_ref set and resolvable; non-empty youtube-*.xml in data/feeds/; FreshRSS can subscribe to http://feeds/youtube-*.xml
**Why human:** Requires yt-dlp in container, reachable YouTube channel, live services

#### 4. Gmail OAuth2 provision + live ingest run

**Test:** Run scripts/provision_gmail_oauth.py with client_secrets.json; then docker compose up gmail-mcp-server ingest-gmail; POST to localhost:22012/run
**Expected:** gmail-mcp-server starts in HTTP transport mode (PORT=3000 exported); >=1 gmail row in articles table; >=1 item.ingested event; GMAIL_OAUTH2_REFRESH_TOKEN written to .env (not printed)
**Why human:** Requires live Gmail OAuth2 browser flow, provisioned credentials, running MCP server

#### 5. Live Obsidian clip ingest

**Test:** Set OBSIDIAN_VAULT_PATH; add >=1 .md clip with frontmatter to articles-inbox; POST to localhost:22013/run
**Expected:** >=1 row with source_type="obsidian"; title/url/source/summary mapped per D-09; lang="no" for Norwegian clips; vault files unmodified after run
**Why human:** Requires host vault directory, live Postgres+RabbitMQ, real clip files

#### 6. Scheduler 409-skip under live conditions

**Test:** While an adapter run is in-flight, trigger it again via the scheduler's next cron fire (or manual POST)
**Expected:** Scheduler log shows "[name] skipped — already running (409)"; exactly one ingest run executes; no concurrent execution
**Why human:** Requires live stack + concurrent timing; unit tests simulate this but live confirmation is needed

---

## Notes on ROADMAP vs SPEC Discrepancy

**ROADMAP SC1** lists `ingest-web` alongside `ingest-imap` and `ingest-youtube`. **ROADMAP SC4** references "FreshRSS (:22010)" — however :22010 is the ingest-imap trigger port, not the FreshRSS UI port (:8088). These are ROADMAP documentation errors:

1. **ingest-web**: 04-SPEC.md (line 68) and 04-CONTEXT.md (line 34) both explicitly state "ingest-web (direct HTTP scraper) — deferred to Phase 5+". The SPEC was the authoritative scope document for Phase 4 planning. The 4 implemented adapters (imap, youtube, obsidian, gmail) match the SPEC's "all 4: imap, youtube, gmail, obsidian" scope statement.

2. **:22010 reference**: FreshRSS is on :8088 in docker-compose. :22010 is the ingest-imap trigger port. The intent of SC4 (YouTube Atom feeds FreshRSS via data/feeds volume + feeds static server) is correctly implemented.

These discrepancies exist at the ROADMAP level only; the SPEC + PLAN + implementation are internally consistent. Recommendation: update ROADMAP SC1 to read `ingest-imap/ingest-youtube/ingest-obsidian` and SC4 to remove the port reference.

---

_Verified: 2026-06-29T12:53:16Z_
_Verifier: Claude (gsd-verifier)_
