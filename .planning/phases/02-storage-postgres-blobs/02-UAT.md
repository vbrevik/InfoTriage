---
status: complete
phase: 02-storage-postgres-blobs
source: [02-01-SUMMARY.md, 02-02-SUMMARY.md, 02-03-SUMMARY.md, 02-04-SUMMARY.md]
started: 2026-06-29T06:50:55Z
updated: 2026-06-29T06:55:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Cold Start Smoke Test
expected: From a clean slate (down + wipe ./data/postgres), `docker compose up -d postgres` boots healthy and `pytest -m db_live` passes against the fresh DB; init_schema() creates all 7 tables (articles, audit, ccir, embeddings, enrichment, entities, entity_links) on first use.
result: pass
evidence: Removed container + wiped ./data/postgres. `docker compose up -d postgres` → healthy in ~12s (127.0.0.1:22000). infotriage schema had 0 tables before pytest. `pytest -m db_live` → 7 passed / 154 deselected in 1.26s. After: exactly 7 tables present (articles, audit, ccir, embeddings, enrichment, entities, entity_links). Tested by Claude per user request 2026-06-29.

### 2. digest.py persists scored verdicts into Postgres (R6)
expected: With Postgres up and `INFOTRIAGE_PG_DSN` set, running the triage digest writes each scored verdict into Postgres `articles` via `store.put_item()` — rows appear in the DB, and nothing is appended to `data/verdicts.jsonl` (that path is gone). With `INFOTRIAGE_PG_DSN` unset, digest.py raises a clear KeyError instead of silently falling back.
result: pass
evidence: Exercised digest.map_verdict_to_item() + PostgresStore.put_item() against live :22000 — get_item roundtrip returned title + payload.score=7.5 + source_type=rss + lang=no intact; row confirmed via raw SQL in infotriage.articles (source=UAT-R6, score=7.5). grep: digest.py has no verdicts.jsonl/persist() (uses put_item at :379); the only remaining verdicts.jsonl reference is sab_html.py, a separate downstream consumer, not digest. digest.py:374 `os.environ["INFOTRIAGE_PG_DSN"]` direct subscript → KeyError raised when unset (verified). Test row deleted after (0 rows left). Tested by Claude per user request 2026-06-29.

### 3. Atom projection renders a valid feed from the store (R7)
expected: `render_atom(store)` returns valid Atom XML listing the stored rss/yt items (email excluded), deterministic output — a feed FreshRSS could subscribe to.
result: pass
evidence: Seeded store with rss + yt + imap items; render_atom(store) → 927 bytes, parsed with defusedxml → root `{http://www.w3.org/2005/Atom}feed`; entries = [YT Video, RSS Headline]; imap "Secret Email" excluded (D-04a); byte-identical on re-render (deterministic). Tested by Claude per user request 2026-06-29.

## Summary

total: 3
passed: 3
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

[none yet]
