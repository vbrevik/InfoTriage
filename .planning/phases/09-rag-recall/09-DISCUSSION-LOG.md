# Phase 9: RAG recall - Discussion Log

**Date:** 2026-07-13
**Participants:** Operator + Claude (Buffy)
**Mode:** `/gsd-discuss-phase 9`

## Gray areas identified

1. CCIR vector representation
2. Pre-filter threshold τ
3. Pipeline integration point
4. Audit logging details
5. Recall search scope
6. Recall output format
7. DGX synthesis trigger
8. Embedding reuse / table design

## Discussion

All eight gray areas were presented to the operator. The operator confirmed the recommended decisions without override.

### Locked decisions

| # | Decision | Rationale |
|---|---|---|
| 1 | One vector per CCIR from `ccir.md` text, stored in `infotriage.ccir_vectors` | Simple, sufficient for pre-filter; multi-vector per CCIR deferred |
| 2 | Fixed threshold τ = 0.50, configurable via `INFOTRIAGE_PREFILTER_THRESHOLD` | Conservative starting point; skips only clearly off-topic items |
| 3 | Pre-filter runs in `apps/triage/worker.py` after embedding, before `score_item()` | Maximizes LLM cost savings; reuses existing embedding call |
| 4 | Audit pre-filter skips in `infotriage.audit` with `details JSONB` | Meets success criterion "logged in audit"; captures score/threshold/best CCIR |
| 5 | Recall searches `title + summary + enrichment.why` by default; optional `--include-body` | Cheap semantic search over existing embeddings; full body deferred |
| 6 | `recall.py` CLI outputs Markdown by default; `--json` and `--obsidian` flags | Flexible output surfaces without scope creep |
| 7 | Local qwen36 only; DGX synthesis deferred to Phase 10 | Keeps Phase 9 focused on retrieval; respects ADR-004 |
| 8 | Reuse `infotriage.embeddings` for items; add `infotriage.ccir_vectors` for CCIRs | Avoids duplicate embedding table; uses mE5 asymmetric prefixes |

## Scope notes

- SAB `/recall` endpoint deferred out of Phase 9.
- DGX synthesis deferred to Phase 10 (Wiki-LLM).
- Full-body chunking/indexing deferred to Phase 10.

## Next step

Proceed to `/gsd-plan-phase 9` using the locked decisions in `09-CONTEXT.md`.
