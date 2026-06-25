---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: in-progress
last_updated: "2026-06-25T08:02:00Z"
progress:
  total_phases: 13
  completed_phases: 0
  total_plans: 7
  completed_plans: 3
  percent: 43
---

# STATE — InfoTriage

> **Ephemeral.** Pick-up-next-session memory. Durable context lives in `docs/`, `PROJECT.md`,
> `REQUIREMENTS.md`, `ROADMAP.md`, `.planning/codebase/`. Trim aggressively.

## Session: 2026-06-25 — Phase 00 plan 04 complete

### Just-completed

- **00-04-PLAN.md (R3 Entity Resolution)**: pgvector cosine entity resolution proven via bge-m3
  1024-dim embeddings + HNSW index. 285 entities, 599 entity_links from 144-item corpus.
  NATO → 1 entity_id across 5 TASS items (all lang=ru). Control test PASS (Trump≠Putin).
  Verdict: PARTIAL — mechanism GO, cross-language coverage limited by corpus date (no NATO
  in NRK/BBC on 2026-06-25). Commit: 5c17666 (R3-VERDICT.md).

- **00-02-PLAN.md (R1 RabbitMQ Topology)**: InfoTriage AMQP topology proven on RabbitMQ 3.13 /
  pika 1.4.1. DLX-first declaration (infotriage.dlx → infotriage.dlq → infotriage.events → 4 primary
  queues). Publish→consume round-trip passed. All 4 event-type publisher confirms passed. Poison
  nack (requeue=False) dead-lettered to infotriage.dlq (depth=1). Verdict: GO.
  Commit: 39711a0 (R1-VERDICT.md).

- **00-01-PLAN.md (Spike Infra + Corpus)**: Ephemeral RabbitMQ (22060/22061) + pgvector (22062)
  containers running and healthy. 144-item NRK/BBC/TASS corpus fetched via defusedxml into
  `.spike/items.json`. `.spike/` gitignored. All infra prerequisites for R1-R5 now in place.
  Commits: 14ead5e (infra), f317cd4 (fetcher).

### Decisions recorded

- **R3 PARTIAL**: pgvector HNSW cosine entity resolution mechanism GO; cross-language NATO coverage
  limited by corpus date. Schema (entities+entity_links+HNSW), threshold 0.85, bge-m3 1024-dim
  validated for ADR-006 / Phase 8.

- **HNSW over IVFFlat**: No minimum rows needed; correct for small corpora and incremental inserts.

- **LINK_THRESHOLD=0.85**: Separates distinct persons (Trump/Putin sim ~0.72) while merging entity
  variants (NATO/НАТО sim ~0.92). Confirmed empirically on R3 corpus.

- **bge-m3 1024-dim CLS-pool vectors**: Validated for multilingual entity resolution; primary
  candidate for Phase 5/8. R2-VERDICT.md needed to confirm bake-off result.

- **torchvision nightly incompatibility (0.24.0.dev vs torch 2.11.0)**: Phase 5 env must resolve
  torch/torchvision version mismatch; spike used XLMRobertaModel direct import with mock.

- **R1 GO**: InfoTriage AMQP topology (topic exchange infotriage.events, 4 routing keys, DLX
  infotriage.dlx, DLQ infotriage.dlq) proven on RabbitMQ 3.13 — proceed to ADR-007.

- **pika 1.4.1 confirm API**: `channel.confirm_delivery()` method call; `basic_publish()` raises
  `NackError`/`UnroutableError` on rejection (no `wait_for_confirms()` method). Phase 3 must use
  `aio-pika` with `connect_robust()`.

- `defusedxml.ElementTree` exclusively for any network-sourced RSS/XML (stdlib parser forbidden — XXE, T-00-01-XXE).
- Spike port band: 22060 (RabbitMQ AMQP), 22061 (RabbitMQ mgmt), 22062 (pgvector Postgres); credentials `spike`/`spike`.
- `.spike/` gitignored wholesale; spike config files committed via `git add -f`; ephemeral data (items.json) not committed.

### Pending — Phase 00 plans

- 00-03-PLAN.md: R2 Norwegian dedup spike
- 00-05-PLAN.md: R4 Wiki-LLM feasibility spike
- 00-06-PLAN.md: R5 COP/World Monitor spike
- 00-07-PLAN.md: Spike closeout (ADRs + SPIKE-FINDINGS.md + teardown)

### Carried-over open questions

- Q1 World Monitor CCIR/SAB coverage → **R5 spike** (still open).
- Q5 embedding model (bge-m3 vs mE5-large) → decided in **R2 spike** (still open).
