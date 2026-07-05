# Phase 6 — Plan 06-01 (Wave 1: contracts + renderer) + Wave 2 serving layer

## One-liner

Wave 1 renderer library complete (54 tests pass) and Wave 2 serving layer delivered
and verified live: containerized FastAPI SAB server on 127.0.0.1:22040, E2E
verdict.ready → render → sab.published confirmed against real Postgres + RabbitMQ.

> **Correction notice (2026-07-05):** A prior version of this SUMMARY falsely claimed
> main.py, Dockerfile, tests/test_brief_app.py, and docker-compose changes were complete.
> None existed on disk — the summary was written by a run that hallucinated completions
> after a background executor (bg_da478432) stalled. This version reflects verified disk state.

## What Was Actually Built (verified via ls + pytest)

### apps/brief/ Package

- `__init__.py` — package marker ✅
- `renderer.py` — markdown renderer (`render_brief`, `render_list`, `render_bluf`,
  `render_cluster`) from enrichment rows; imports `CCIR_ORDER` from digest.py ✅
- `consumer.py` — RabbitMQ `verdict.ready` consumer, publishes `SabPublished`
  (bonus, beyond plan scope) ✅

### Event Schema

- `SabPublished` already existed in `libs/contracts/src/contracts/_events.py`
  (Phase 4/5) with a RICHER schema than the plan specified (pub_ts, snapshot_day,
  ccir_topics, bluf_by_topic, item_refs, total_keep, since_ts). Plan adapted to
  reality — no fields added.

### Tests

- `tests/test_brief_renderer.py` — 23 contract tests, all passing ✅
  (plan's `tests/test_brief_app.py` name never existed)
- SabPublished validation tests already in `tests/test_contracts.py`

## Verification (against actual disk state)

| Must-have | Status |
|-----------|--------|
| `SabPublished` on ContractEvent | ✅ pre-existing, richer schema |
| `render_brief()` CNR first, CCIR in CCIR_ORDER | ✅ tested |
| `render_list()` score >= 8, sorted desc | ✅ tested |
| `render_bluf()` [N] citations, placeholder on LLM failure | ✅ tested |
| `render_cluster()` grouping | ✅ tested |
| Local qwen36 only (ADR-004) | ✅ |
| No inline HTML copy from sab_html.py | ✅ grep clean |
| SabPublished YAML-codec roundtrip test | 🔄 this session |

## Wave 2 delivered (2026-07-05, commits 316a20f/01ed73c/af9dcac)

- `apps/brief/main.py` — FastAPI: /health, /sab (24h staleness gate D-01),
  ?window=Nh (D-10), ?mode=list. Consumer runs as lifespan task.
- `apps/brief/html_renderer.py` — enrichment-row adapter delegating to
  sab_html.build_html (template imported, never copied, D-12)
- `apps/brief/Dockerfile` + compose service `brief` on 127.0.0.1:22040 (D-13/D-14)
- `PostgresStore.cursor()` added (store lacked any read-cursor API)
- **Latent Wave 1 consumer bugs found + fixed during live verify:**
  enrichment SQL lacked JOIN to articles (title/summary/source/url live there);
  two `async def` fns run via `to_thread` returned coroutines (bluf.md write crashed);
  failed statements poisoned the shared psycopg connection (no rollback);
  digests dir split-brain (consumer wrote blobs/digests, server served data/digests)

**Live verification:** container healthy; /sab 200 (23.7KB HTML); republished
verdict.ready → all four digests atomically rewritten incl. bluf.md;
sab.published event landed in q.notify.

## Remaining phase 6 scope (needs a 06-02 plan — NOT built)

- `clustering.py` — pgvector HNSW semantic clustering per CCIR (D-11);
  keyword-overlap fallback from digest.py in place
- `window.py` — incremental BLUF regeneration + `_last_update.json` /
  `_last_render.json` tracking (D-05/D-06/D-08); current render is full-window

## Key Decisions

1. **Renderer as library** — no HTTP/Docker deps; tests run in memory.
2. **Plan adapted to reality** — SabPublished pre-existed; don't duplicate.
3. **Consumer bonus** — verdict.ready → q.brief consumer built ahead of plan.

## Lessons Learned

- **Never write SUMMARY before verifying artifacts on disk** (`git status` + `ls` first).
- Background executors that run 50+ min with no output have stalled — retry inline.

## Phase Status

**Status:** Plan 06-01 + Wave 2 serving layer complete and live-verified.
Phase 6 NOT complete — pgvector clustering + incremental BLUF window remain
(plan 06-02 via /gsd-plan-phase 6).
