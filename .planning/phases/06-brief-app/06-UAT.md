---
status: complete
phase: 06-brief-app
source: 06-01-SUMMARY.md, 06-02-SUMMARY.md, 06-03-SUMMARY.md, 06-04-SUMMARY.md
started: 2026-07-08T08:40:00Z
updated: 2026-07-08T20:10:00Z
---

## Current Test

[testing complete]

## Tests

### 1. View SAB via FastAPI /sab endpoint
expected: Server responds to GET /sab with HTML page, displays CNR alerts at top, CCIR sections with clusters, and includes "Since" timestamp. Container is healthy at /health.
result: issue
reported: "Page renders but shows no items - all CCIR sections show count 0. HTML structure correct but no enrichment data in database."
severity: major
retest: "Agent-run live 2026-07-08 20:00Z: symptom RESOLVED after root-cause fix + repopulation — /sab regenerated with 108 items, CNR alert at top, healthy /health. Root cause remains unfixed in code (see Gaps)."

### 2. Clustering shows multi-item semantic groups
expected: At least one CCIR section contains 2+ items grouped together via pgvector clustering (not just singletons)
result: pass
evidence: "Agent-run live 2026-07-08: after repopulating DB (108 articles/enrichments/embeddings via POST /run to ingest-imap+ingest-youtube), /sab shows FFIR-3 cluster '(5 kilder: gmail, hover)' — 5 items merged into one story; PIR-3 section count 6; section counts 1/2/5/6 present."

### 3. Vault writer creates .md files in brief-outbox
expected: Obsidian markdown files appear in ${OBSIDIAN_VAULT_PATH}/brief-outbox for high-value items and the SAB summary
result: pass
evidence: "Agent-run live 2026-07-08: 7 per-item .md files + obsidian-sab.md written to /Users/vidarbrevik/Vault/brief-outbox at 21:38 (fresh consumer rebuild on verdict.ready)."

### 4. Vault writer includes email-sourced items by default
expected: Items with source_type='imap' (email) appear in vault output unless VAULT_INCLUDE_EMAIL=0
result: pass
evidence: "Agent-run live 2026-07-08: 5 vault files contain imap:// links (gmail + hover sources) with VAULT_INCLUDE_EMAIL=1 (default-on) in container env."

### 5. CLUSTER_THRESHOLD validation works
expected: Out-of-range values (negative, >1) cause ValueError; default 0.75 is used when env var missing
result: pass
evidence: "Agent-run live 2026-07-08 inside infotriage-brief container: CLUSTER_THRESHOLD=1.5 → ValueError; =-0.2 → ValueError; unset → default 0.75."

## Summary

total: 5
passed: 4
issues: 1
pending: 0
skipped: 0

## Gaps

- truth: "SAB page displays CNR alerts, CCIR sections with clusters, and timestamp"
  status: failed
  reason: "User reported: Page renders but shows no items - all CCIR sections show count 0. HTML structure correct but no enrichment data in database."
  severity: major
  test: 1
  root_cause: "CONFIRMED 2026-07-08 (live forensics): (a) db_live test fixtures (tests/test_store_integration.py DEV_DSN, test_triage_enrichment.py, test_store_contract.py) point at PRODUCTION Postgres :22000 and TRUNCATE ALL infotriage tables incl. articles — every pytest run with :22000 reachable wipes live data. (b) A stuck fixture TRUNCATE (pid 100197) queued 8.5h behind an idle-in-transaction connection from infotriage-triage worker (pid 42033, open txn since a SELECT, never committed) — blocked all reads on the tables. Symptom resolved by: pg_cancel_backend on the TRUNCATE, restarting infotriage-triage, re-triggering ingest (POST /run to :22010/:22011) → 108 articles/enrichments/embeddings, /sab repopulated."
  artifacts:
    - path: "tests/test_store_integration.py"
      issue: "DEV_DSN = prod :22000; _truncate_all wipes live articles/enrichment/embeddings on every db_live test run"
    - path: "apps/triage/worker.py"
      issue: "worker psycopg connection left 'idle in transaction' (8.5h) — a read path opens a txn and never commits/rolls back; blocks any DDL/TRUNCATE and poisons lock queue"
  missing:
    - "Point db_live fixtures at a dedicated test database/port (or ephemeral container), never prod :22000"
    - "Fix triage worker read paths to commit/rollback (or use autocommit) so no idle-in-transaction connection persists"
  debug_session: ".planning/debug/sab-no-content.md"
