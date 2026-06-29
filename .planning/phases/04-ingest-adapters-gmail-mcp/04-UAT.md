---
status: testing
phase: 04-ingest-adapters-gmail-mcp
source: [04-VERIFICATION.md]
started: 2026-06-29T12:56:28Z
updated: 2026-06-29T12:56:28Z
---

## Current Test

number: 1
name: docker compose up --build — all 6 images build and start cleanly
expected: |
  All 6 Phase 4 services (ingest-imap, ingest-youtube, ingest-obsidian, ingest-gmail,
  gmail-mcp-server, scheduler) build and reach healthy/running state.
  No build errors. Ports 22010–22014 and 127.0.0.1:22025 are bound.
awaiting: user response

## Tests

### 1. docker compose up --build
expected: All 6 images build without errors; containers start and remain running; ports 22010–22014 + 127.0.0.1:22025:3000 bound
result: [pending]

### 2. Live IMAP run
expected: POST /run to ingest-imap:22010 returns 200; ≥1 Item row inserted in Postgres; no Atom XML written to data/feeds/
result: [pending]

### 3. Live YouTube run
expected: POST /run to ingest-youtube:22011 returns 200; ≥1 Item row + blob in Postgres; youtube-*.xml Atom file written to data/feeds/
result: [pending]

### 4. Gmail OAuth2 provision + live ingest run
expected: scripts/provision_gmail_oauth.py completes; token.json written; POST /run to ingest-gmail:22012 returns 200; ≥1 Item row in Postgres
result: [pending]

### 5. Live Obsidian clip ingest
expected: Markdown clip in $OBSIDIAN_VAULT_PATH/articles-inbox/ → POST /run to ingest-obsidian:22013 → ≥1 Item row; vault directory unchanged (read-only)
result: [pending]

### 6. Scheduler 409-skip under live conditions
expected: Two concurrent POST /run calls to any adapter → first returns 200, second returns 409; scheduler logs "skipped (locked)" for the 409
result: [pending]

## Summary

total: 6
passed: 0
issues: 0
pending: 6
skipped: 0
blocked: 0

## Gaps
