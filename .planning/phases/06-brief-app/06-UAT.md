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
result: pass
evidence: |
  - Seeded 11 sample articles/enrichments/embeddings via `scripts/seed_sample_data.py`.
  - After clearing `data/digests/sab.html`, GET http://localhost:22040/sab rendered CCIR
    sections with multi-item clusters:
    - PIR-1: 4 saker · 1 klynger
    - PIR-2: 2 saker · 1 klynger
    - PIR-4: 2 saker · 1 klynger
    - FFIR-3: 2 saker · 1 klynger
  - Multi-source cluster tags appear in the HTML: `(3 kilder)`, `(2 kilder)`.
  - Root cause found and fixed: `psycopg` returned embeddings as JSON strings, which
    `apps/brief/html_renderer.py` discarded as non-list embeddings. Updated
    `_apply_semantic_clustering()` to parse string embeddings and pass the real
    `cluster_threshold` through to `cluster_items_in_memory()`.
  - Full pytest suite: 275 passed, 2 skipped after the fix.

### 4. Vault writer creates .md files in brief-outbox
expected: Obsidian markdown files appear in ${OBSIDIAN_VAULT_PATH}/brief-outbox for high-value items and the SAB summary. Files have valid front-matter parseable by existing codec.
result: pending

### 5. Vault writer includes email-sourced items by default
expected: Items with source_type='imap' (email) appear in vault output unless VAULT_INCLUDE_EMAIL=0. Front-matter codec round-trips correctly with punctuation and multiline fields.
result: pending

### 6. CLUSTER_THRESHOLD validation works
expected: Out-of-range values (negative, >1) cause ValueError; default 0.75 is used when env var missing. Threshold is validated in main.py and passed through consumer render path.
result: pass
evidence: |
  - Created `scripts/uat_test6_cluster_threshold.py` and ran it against the live DB.
  - Default: with `CLUSTER_THRESHOLD` unset, `apps.brief.main.CLUSTER_THRESHOLD == 0.75`.
  - Validation: `CLUSTER_THRESHOLD=-0.2` and `CLUSTER_THRESHOLD=1.5` both raise `ValueError`
    at import time.
  - Pass-through: `apps/brief/main.py` passes `cluster_threshold=CLUSTER_THRESHOLD` to both
    `build_html()` and the `run_consumer()` call.
  - End-to-end: rendering the same rows with `cluster_threshold=0.99` produced 7 total
    clusters, while `cluster_threshold=0.0` produced 5 total clusters, proving the threshold
    changes clustering behavior.

### 7. Event-driven rendering works end-to-end
expected: Republishing verdict.ready event regenerates all 4 digest files (brief.md, cluster.md, list.md, bluf.md) atomically via .tmp + os.replace. sab.published event lands on bus.
result: pending

### 8. Semantic clustering engages on real data
expected: pgvector HNSW clustering engages on real enrichment data (not keyword-overlap fallback). Items with similar embeddings merge into same cluster within same CCIR section. Items in different CCIR sections never merge.
result: pass
evidence: |
  - Created `scripts/uat_test8_semantic.py` to seed discriminating real data:
    - Two PIR-1 items with nearly identical embeddings but dissimilar titles (no keyword
      overlap that keyword fallback could use).
    - One PIR-2 item with title keywords overlapping a PIR-1 item but a divergent embedding.
  - Ran the script against the live Postgres + brief app.
  - Cluster assignments from the brief-app path showed the two PIR-1 items merged into
    one cluster, while the PIR-2 item remained a singleton.
  - Rendered `/sab` showed multi-item clusters (PIR-1: 6 saker · 2 klynger).
  - This confirms semantic clustering is active and not falling back to keyword overlap.

### 9. CLUSTER_THRESHOLD env var configurable and passed to renderer
expected: Setting CLUSTER_THRESHOLD env var changes clustering behavior. Value validated 0.0-1.0 in main.py. Threshold flows from main.py into renderer._cluster_rows().
result: pending

## Summary

total: 9
passed: 5
issues: 0
pending: 4
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

### Renderer regression caught during UAT re-run (2026-07-11)

`apps/brief/renderer.py::render_brief()` called `digest.line()` from
`apps/triage/digest.py` in its CCIR-iteration path. That helper is
`f"- {v.get('why') or v['title']}{withsrc}  [les]({v.get('url','')})"` —
when `why` is truthy, `or` short-circuits and both `title` and `score` are
dropped from the rendered line. Visible in the brief app as `- <why>  [les](<url>)`
under any CAT_II or ROUTINE CCIR section.

Root-caused by re-running `tests/test_brief_consumer.py` after the COP/CIP
view-filter work landed; `test_process_verdict_renders_default_cop_cip_files`
failed with `AssertionError: assert 'COP Item' in '# InfoTriage · SAB\n_1 saker · ~10 min_\n\n## FFIR-1 · Norsk forsvar & sikkerhetspolitikk\n- Test why  [les](http://example.com)\n'`
— note the missing `**[9] COP Item**` prefix.

Fix: replaced the single `_digest_line(lead, extra)` call inside the
CCIR-iteration loop with inline formatting (matches the CAT_I section's
style, includes `flag`, `why_str`, `score`, `title`, and `[les](url)`).
Also deleted pre-existing dead code `_group_by_ccir()` (was defined but
never called; return shape was broken).

Regression test: `tests/test_brief_renderer.py::TestRenderBriefIncludesAllItemFields`
asserts that for a CAT_II item with truthy `why`, all three of `title`,
`[score]`, and `why` appear in `render_brief()` output. A second test
asserts title+score for `Routine` (no-CCIR) items.

Live proof: rendered a CAT_II item with `why="Krigsøkonomi under press"`,
`title="Russland varsler nye sanksjoner"`, `score=7` through the live
`render_brief()` path. Output: `## PIR-1 · Russland / Ukraina\n- **[7] Russland
varsler nye sanksjoner** · Krigsøkonomi under press  [les](http://example.com)`.
Title, score, and why all present.

Full pytest suite after fix: 280 passed, 34 skipped. UAT 6 (CLUSTER_THRESHOLD)
and UAT 8 (semantic clustering) re-run live: both still pass.
