---
status: complete
phase: 02-storage-postgres-blobs
source: [02-01-SUMMARY.md, 02-02-SUMMARY.md, 02-03-SUMMARY.md, 02-04-SUMMARY.md]
started: 2026-06-28T19:31:12Z
updated: 2026-06-28T19:39:50Z
---

## Current Test

[testing complete]

## Tests

### 1. Cold Start Smoke Test
expected: From a clean slate (down + wipe ./data/postgres), `docker compose up -d postgres` boots healthy and `pytest -m db_live` passes 7/7 against the fresh DB; init_schema() creates all 7 tables on first use.
result: pass
evidence: Wiped ./data/postgres, recreated container (healthy in ~12s, 127.0.0.1:22000). 0 tables before; `pytest -m db_live` 7 passed / 151 deselected; 7 tables after (articles, audit, ccir, embeddings, enrichment, entities, entity_links). Tested by Claude per user request.

### 2. digest.py persists scored verdicts into Postgres (R6)
expected: With Postgres up and `INFOTRIAGE_PG_DSN` set, running the triage digest writes each scored verdict into Postgres `articles` via `store.put_item()` — rows appear in the DB, and nothing is appended to `data/verdicts.jsonl` (that path is gone). With `INFOTRIAGE_PG_DSN` unset, digest.py raises a clear KeyError instead of silently falling back.
result: pass
evidence: Exercised digest's real map_verdict_to_item() + PostgresStore.put_item() against live Postgres — row read back via store.get_item (title + payload.score=7.5 intact) and confirmed in infotriage.articles via raw SQL. grep: 0 verdicts.jsonl/persist() matches (path removed). digest.py:374 os.environ["INFOTRIAGE_PG_DSN"] is a direct subscript → raises KeyError when unset. Test row cleaned up after. (Full main() needs live FreshRSS/Fever + scoring; the persistence seam was exercised directly.) Tested by Claude per user request.

### 3. Atom projection renders a valid feed from the store (R7)
expected: `render_atom(store)` returns valid Atom XML listing the stored rss/yt items (email excluded), deterministic output — a feed FreshRSS could subscribe to.
result: pass
evidence: render_atom(store) returned 929 bytes of valid Atom <feed> (parsed with defusedxml); entries = [RSS Headline, YT Video]; email source excluded (D-04a); byte-identical on re-render (deterministic). Tested by Claude per user request.

## Summary

total: 3
passed: 3
issues: 0
pending: 0
skipped: 0

## Gaps

[none yet]
