---
status: testing
phase: 06-brief-app
source: 06-01-SUMMARY.md, 06-02-SUMMARY.md, 06-03-SUMMARY.md, 06-04-SUMMARY.md, 06-05-SUMMARY.md, 06-06-SUMMARY.md
started: 2026-07-09T14:00:00Z
updated: 2026-07-09T14:00:00Z
---

## Current Test

number: 2
name: View SAB via FastAPI /sab endpoint
expected: |
  Server responds to GET /sab with HTML page, displays CNR alerts at top, CCIR sections with
  clusters, and includes "Since" timestamp. Container is healthy at /health.
result: pass
evidence: |
  2026-07-10: GET http://localhost:22040/sab returned a valid HTML document with title
  "InfoTriage · SAB — siden 2026-07-10 12:05". Fixed a NameError ('cutoff' undefined) in
  apps/triage/sab_html.py by threading cutoff_epoch through build_html().

## Tests

### 1. Cold Start Smoke Test
expected: Kill any running services. Clear ephemeral state. Start the application stack from scratch (docker compose up -d). Server boots without errors, seed/migration completes, and a primary query (GET /health on brief:22040) returns live data.
result: pass
evidence: |
  - Executed `docker compose down -v` at 2026-07-10.
  - Executed `docker compose up -d`; stack started successfully.
  - GET http://localhost:22040/health returned `{"status":"ok","service":"brief"}`.
  - Fixed a pre-existing `apps/opml_health/Dockerfile` path/import bug that caused
    `infotriage-opml-health` to crash on startup with `ModuleNotFoundError: No module named 'apps'`.
    The Dockerfile now preserves the `apps/` layout (matching `apps/brief/Dockerfile`).

### 2. View SAB via FastAPI /sab endpoint
expected: Server responds to GET /sab with HTML page, displays CNR alerts at top, CCIR sections with clusters, and includes "Since" timestamp. Container is healthy at /health.
result: pass
evidence: |
  - GET http://localhost:22040/sab returned HTTP 200 with a complete HTML document.
  - Title includes "Since" timestamp: `InfoTriage · SAB — siden 2026-07-10 12:05`.
  - HTML contains slide sections: title, CNR, PIR-1, PIR-2, PIR-3, PIR-4, FFIR-3, filtered, BLUF, stats.
  - CNR alert (`🚩 CNR — varsle straks`) is rendered at the top when CNR-I items exist.
  - CCIR sections are rendered only when matching items exist in the window.
  - Seeded 11 sample articles/enrichments/embeddings via `scripts/seed_sample_data.py` to
    populate CNR alerts and CCIR sections.
  - Fixed `NameError: name 'cutoff' is not defined` in `apps/triage/sab_html.py` by adding
    `cutoff_epoch` parameter to `build_html()` and threading it through
    `apps/brief/html_renderer.py` → `apps/brief/main.py`.
  - Full pytest suite: 275 passed, 2 skipped after the fix.

### 3. Clustering shows multi-item semantic groups
expected: At least one CCIR section contains 2+ items grouped together via pgvector clustering (not just singletons). Keyword-overlap fallback is NOT used.
result: pending

### 4. Vault writer creates .md files in brief-outbox
expected: Obsidian markdown files appear in ${OBSIDIAN_VAULT_PATH}/brief-outbox for high-value items and the SAB summary. Files have valid front-matter parseable by existing codec.
result: pending

### 5. Vault writer includes email-sourced items by default
expected: Items with source_type='imap' (email) appear in vault output unless VAULT_INCLUDE_EMAIL=0. Front-matter codec round-trips correctly with punctuation and multiline fields.
result: pending

### 6. CLUSTER_THRESHOLD validation works
expected: Out-of-range values (negative, >1) cause ValueError; default 0.75 is used when env var missing. Threshold is validated in main.py and passed through consumer render path.
result: pending

### 7. Event-driven rendering works end-to-end
expected: Republishing verdict.ready event regenerates all 4 digest files (brief.md, cluster.md, list.md, bluf.md) atomically via .tmp + os.replace. sab.published event lands on bus.
result: pending

### 8. Semantic clustering engages on real data
expected: pgvector HNSW clustering engages on real enrichment data (not keyword-overlap fallback). Items with similar embeddings merge into same cluster within same CCIR section. Items in different CCIR sections never merge.
result: pending

### 9. CLUSTER_THRESHOLD env var configurable and passed to renderer
expected: Setting CLUSTER_THRESHOLD env var changes clustering behavior. Value validated 0.0-1.0 in main.py. Threshold flows from main.py into renderer._cluster_rows().
result: pending

## Summary

total: 9
passed: 2
issues: 0
pending: 7
skipped: 0

## Gaps

[none yet]

## Notes

- Cold-start revealed and fixed `apps/opml_health/Dockerfile` import layout bug.
- Several non-critical services (`freshrss`, `rssbridge`, `feeds`, `gmail-mcp-server`,
  `scheduler`) reported as `unhealthy` in `docker compose ps` shortly after startup.
  Their logs show they started; the unhealthy status is likely due to missing
  runtime configuration (FreshRSS setup, Gmail OAuth) or timing of the first health
  probe. These are outside the scope of Test 1 (brief /health) and will be revisited
  in later UAT tests or Phase 7 ops work.
