---
phase: 04-ingest-adapters-gmail-mcp
plan: "05"
subsystem: ingest-gmail
tags: [gmail, mcp, oauth2, ingest, adapter, httpx, json-rpc]
status: complete

decisions:
  - "D-05 confirmed: raw httpx JSON-RPC to @shinzolabs/gmail-mcp; no Python MCP SDK"
  - "MCP endpoint path: /mcp (Streamable HTTP; PORT env var activates HTTP transport)"
  - "MCP transport: PORT env var forces Streamable-HTTP; without PORT server defaults to stdio"
  - "Session handling: init_mcp_session returns result.sessionId; empty string if not returned"
  - "list_messages tool wraps result in content[0].text as JSON string; parsed in adapter"

dependency_graph:
  requires: [04-01, libs/ingest_common, libs/contracts, libs/store]
  provides: [apps/ingest-gmail, gmail-mcp-server, scripts/provision_gmail_oauth.py]
  affects: [docker-compose.yml, README.md]

tech_stack:
  added:
    - "@shinzolabs/gmail-mcp@1.7.4 (Node.js Gmail MCP server — HTTP transport)"
    - "httpx.AsyncClient (raw JSON-RPC to MCP; D-05)"
    - "google-auth-oauthlib (provision script OAuth2 browser flow)"
    - "email.utils.parsedate_to_datetime (RFC 2822 date parsing)"
  patterns:
    - "MCP Streamable HTTP: POST /mcp, Accept: application/json+text/event-stream, Mcp-Session-Id header"
    - "TDD RED/GREEN: failing test committed before implementation"
    - "testability seam: _build_store/_build_bus in gmail_ingest.py, monkeypatched in tests"

key_files:
  created:
    - gmail-mcp-server/Dockerfile
    - gmail-mcp-server/entrypoint.sh
    - scripts/provision_gmail_oauth.py
    - apps/ingest-gmail/mcp_client.py
    - apps/ingest-gmail/gmail_ingest.py
    - apps/ingest-gmail/main.py
    - apps/ingest-gmail/requirements.txt
    - apps/ingest-gmail/Dockerfile
    - tests/test_ingest_gmail.py
  modified:
    - docker-compose.yml (removed gmail_to_atom.py comment reference)
    - README.md (removed operational references, updated diagram/status/bridges sections)
  deleted:
    - apps/ingest/gmail_to_atom.py (retired per SPEC R7)

metrics:
  duration: "13 minutes"
  completed: "2026-06-29T11:42:50Z"
  tasks_completed: 3
  tasks_total: 3
  files_created: 9
  files_modified: 2
  files_deleted: 1
  tests_added: 5
  tests_green: 5
---

# Phase 04 Plan 05: Gmail MCP Adapter + OAuth2 Bridge Summary

Gmail ingest containerized via self-hosted @shinzolabs/gmail-mcp@1.7.4 with raw httpx JSON-RPC client (D-05), replacing the dead-end IMAP/app-password path with a read-only OAuth2/MCP flow (ADR-008); legacy gmail_to_atom.py retired (SPEC R7).

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Gmail MCP server container + OAuth2 provision script | bbebeee | gmail-mcp-server/Dockerfile, entrypoint.sh, scripts/provision_gmail_oauth.py |
| 2 (RED) | Failing tests for ingest-gmail MCP adapter | fb25afa | tests/test_ingest_gmail.py |
| 2 (GREEN) | Implement ingest-gmail MCP client adapter | fcc8477 | apps/ingest-gmail/* (5 files) |
| 3 | Retire legacy gmail_to_atom.py (SPEC R7) | 66477b8 | DELETE apps/ingest/gmail_to_atom.py, README.md, docker-compose.yml |

## MCP Endpoint Resolution (RESEARCH Open Questions 1+2)

**Open Question 1 — MCP endpoint path:**
`@shinzolabs/gmail-mcp` binds to `/mcp` (per the MCP Streamable HTTP 2025-03-26 spec). The adapter posts to `{GMAIL_MCP_URL}/mcp`. Confirmed in Pattern 4 of the RESEARCH file and encoded as the default in `mcp_client.py` (`_ENDPOINT = "/mcp"`).

**Open Question 2 — HTTP transport activation:**
HTTP transport is activated by setting `PORT` env var (e.g. `PORT=3000`). Without `PORT`, the server defaults to stdio and the Python adapter gets `httpx.ConnectError` (RESEARCH Pitfall 3). The entrypoint.sh exports `PORT="${PORT:-3000}"` before launching the server.

## Verification Results

All acceptance criteria and grep gates pass:

| Gate | Check | Result |
|------|-------|--------|
| T-04-SC | `@shinzolabs/gmail-mcp@1.7.4` in Dockerfile | PASS |
| T-04-11 | No credential ARG/ENV in either Dockerfile | PASS |
| T-04-12 | Only gmail.readonly + gmail.metadata scopes | PASS |
| T-04-13 | No write tool names in adapter source | PASS |
| D-05 | No `import mcp` / `from mcp` in ingest-gmail | PASS |
| R3 | pytest tests/test_ingest_gmail.py -x → 5/5 green | PASS |
| R7 | git ls-files apps/ingest/gmail_to_atom.py → empty | PASS |
| R7 | No gmail_to_atom references in docker-compose.yml or README.md | PASS |

## Architecture

```
Host operator
    │ python3 scripts/provision_gmail_oauth.py (once)
    │ writes GMAIL_OAUTH2_REFRESH_TOKEN to .env
    ▼
gmail-mcp-server container (node:22-slim)
    @shinzolabs/gmail-mcp@1.7.4
    PORT=3000 → Streamable HTTP on :3000/mcp
    REFRESH_TOKEN/CLIENT_ID/CLIENT_SECRET from .env via env_file
         ▲ httpx JSON-RPC (POST /mcp, Mcp-Session-Id header)
ingest-gmail container (python:3.12-slim)
    mcp_client.py → init_mcp_session → list_messages → get_message
    gmail_ingest.py → fetch_items → Item(source_type="gmail") → persist_and_publish
    main.py → make_trigger_app(ingest, name="ingest-gmail")
    Postgres (persist) + RabbitMQ (item.ingested event)
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Comment in mcp_client.py triggered write-tool grep gate**
- **Found during:** Task 2 verification
- **Issue:** A comment mentioning "markRead" in a list of prohibited tool names was matched by the acceptance criteria `grep -niE 'send_message|...|markAsRead'` pattern (which intentionally checks all occurrences including comments in some variants)
- **Fix:** Rewrote comment to `# Read-only tool wrappers (list/get only — no mutating operations)` so no forbidden tool name appears anywhere in the source
- **Files modified:** apps/ingest-gmail/mcp_client.py
- **Commit:** fcc8477

**2. [Rule 3 - Blocker] Worktree at b0994bb (before wave 1 commits)**
- **Found during:** Plan startup
- **Issue:** Worktree HEAD was at `b0994bb` (pre-wave-1), not the expected base `84548c0`. The `libs/ingest_common`, `apps/`, `libs/contracts`, `libs/store` and planning files were absent from the worktree checkout.
- **Fix:** `git merge main --ff-only` to fast-forward the worktree branch to `84548c0` before starting implementation. All wave 1 artifacts became available.
- **Impact:** Zero — fast-forward merge; no conflicts; worktree now correctly tracks main HEAD as its base

### Comment-Only Changes (not deviations)

The provision script's comment was initially `# NO gmail.send, gmail.modify, gmail.compose` (to document what was NOT requested). This was changed to a neutral phrasing because the grep gate checks ALL occurrences of those strings regardless of comment context. Final comment: `# Read-only scopes only — mutating scopes are not requested (D-06, ADR-008)`.

## Known Stubs

None — the adapter is functionally complete. `fetch_items()` populates all required Item fields; `ingest()` performs real MCP calls (mocked in tests). The MCP server requires a provisioned refresh token at runtime (expected — operator runs provision script once).

## Threat Flags

No new threat surface beyond what is already in the plan's `<threat_model>`. All mitigations (T-04-11 through T-04-SC) verified via grep gates above.

## Self-Check: PASSED

- gmail-mcp-server/Dockerfile: FOUND
- gmail-mcp-server/entrypoint.sh: FOUND
- scripts/provision_gmail_oauth.py: FOUND
- apps/ingest-gmail/mcp_client.py: FOUND
- apps/ingest-gmail/gmail_ingest.py: FOUND
- apps/ingest-gmail/main.py: FOUND
- apps/ingest-gmail/requirements.txt: FOUND
- apps/ingest-gmail/Dockerfile: FOUND
- tests/test_ingest_gmail.py: FOUND
- apps/ingest/gmail_to_atom.py: DELETED (confirmed by git ls-files returning empty)
- Commits bbebeee, fb25afa, fcc8477, 66477b8: FOUND
