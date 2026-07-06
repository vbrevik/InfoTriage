# Plan 00-07 Summary — Spike Closeout

**Phase:** 00-concept-spike
**Plan:** 07
**Status:** Complete
**Date:** 2026-07-04

## Objective

Convert the five raw verdicts into durable deliverables (SPIKE-FINDINGS.md + ADR-005..008) and dispose of throwaway (.spike/ deleted, containers down — D-06).

## What was built

### Task 1: Durable artifacts (already written in prior session)

The five verdict fragments from `findings/R1-VERDICT.md` through `findings/R5-VERDICT.md` were consolidated into:

- **SPIKE-FINDINGS.md** — Per-unknown go/no-go/partial verdicts:
  - R1 RabbitMQ topology: **GO** (round-trip + DLQ proven)
  - R2 Norwegian semantic dedup: **PARTIAL** (mE5-large @ 0.84; mechanism promising, threshold not calibrated)
  - R3 Entity resolution: **PARTIAL** (pgvector HNSW cosine mechanism GO; cross-language coverage conditional)
  - R4 Wiki-LLM: **PARTIAL** (synthesis GO; cross-language synthesis incomplete — Russian sources dropped)
  - R5 COP/World Monitor: **DROP** WM as engine; **BUILD** native SP-COP canvas
  - R4 samples pasted inline (NATO standing page + Venezuela on-demand article)
  - R3/R2 embedding-model divergence recorded as a Phase-8 re-validation risk

- **ADR-005** — COP/World Monitor: DROP WM as product/engine; BUILD native SP-COP interactive-SAB canvas on open libs
- **ADR-006** — Microservice architecture + pgvector entity resolution: validated schema (entities + entity_links), HNSW cosine linking at threshold 0.85, PARTIAL caveat + Phase-8 re-validation risk on mE5-large
- **ADR-007** — RabbitMQ event bus topology: topic exchange infotriage.events, 4 routing keys, DLX/DLQ
- **ADR-008** — Self-hosted MCP/OAuth2 ingestion: carried from already-proven Gmail proof

### Task 2: Destructive teardown (D-06, already done in prior session)

- `.spike/` deleted (3.1GB including World Monitor clone/build)
- pgvector + RabbitMQ spike containers/volumes removed via `docker compose down -v`
- No spike code merged into `apps/` or `libs/`
- Production data (`data/verdicts.jsonl`) and stack (`:8088/:3000`) untouched

## Acceptance criteria

- [x] SPIKE-FINDINGS.md has go/no-go/partial verdict for each of R1-R5 with raw numbers
- [x] docs/adr/ADR-005, ADR-006, ADR-007, ADR-008 each exist with Status/Context/Decision/Consequences
- [x] R4 samples pasted into findings (survive .spike/ deletion)
- [x] No partial elevated to a pass (R2, R3, R4 all recorded as PARTIAL)
- [x] ADR-006 records the R3/R2 model divergence (bge-m3 vs mE5-large) as a Phase-8 re-validation risk
- [x] .spike/ deleted, spike containers down
- [x] No spike code under apps/ or libs/

## Commits

- `5b5ab32` docs(00-07): consolidate SPIKE-FINDINGS + write ADR-005..008
- `379bb7a` chore(00-07): teardown spike — delete .spike/, down containers + volumes (D-06)
