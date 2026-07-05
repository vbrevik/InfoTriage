# Phase 6 — Plan 06-01 (Wave 1: contracts + renderer)

## One-liner

Wave 1 renderer library complete and tested (23 tests pass); Wave 2 serving layer
(main.py, html_renderer.py, Dockerfile, compose entry) in progress this session.

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

## Remaining (Wave 2 — tracked in .continue-here.md, being closed this session)

- `apps/brief/main.py` — FastAPI SAB server, port 22040
- `apps/brief/html_renderer.py` — HTML output (imports HTML_TEMPLATE)
- `apps/brief/Dockerfile` + docker-compose service entry
- pgvector clustering (`clustering.py`) — deferred to a later plan (keyword fallback in place)

## Key Decisions

1. **Renderer as library** — no HTTP/Docker deps; tests run in memory.
2. **Plan adapted to reality** — SabPublished pre-existed; don't duplicate.
3. **Consumer bonus** — verdict.ready → q.brief consumer built ahead of plan.

## Lessons Learned

- **Never write SUMMARY before verifying artifacts on disk** (`git status` + `ls` first).
- Background executors that run 50+ min with no output have stalled — retry inline.

## Phase Status

**Status:** Wave 1 complete; Wave 2 in progress — phase NOT complete
