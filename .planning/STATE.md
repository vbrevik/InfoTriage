---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: in-progress
last_updated: "2026-06-26T08:30:00Z"
progress:
  total_phases: 13
  completed_phases: 0
  total_plans: 7
  completed_plans: 4
  percent: 57
---

# STATE — InfoTriage

> **Ephemeral.** Pick-up-next-session memory. Durable context lives in `docs/`, `PROJECT.md`,
> `REQUIREMENTS.md`, `ROADMAP.md`, `.planning/codebase/`. Trim aggressively.

## Session: 2026-06-26 — Phase 00 plan 03 verdict synced

### Just-completed

- **00-03-PLAN.md (R2 Norwegian Dedup Bake-off)**: mE5-large vs bge-m3 threshold sweep on 24-row
  hand-labeled corpus (13 yes / 11 no). bge-m3 disqualified (collapse_rate < 0.05 all thresholds).
  **mE5-large chosen @ threshold 0.84** (collapse_rate 0.783, control_overmerge 1). No pair cleared
  both bars — control set too topically narrow. Verdict: PARTIAL — mechanism + model GO; threshold
  needs held-out corpus in Phase 5. Commit: d5aacee. Input `title + summary[:512]`; `passage:`/`query:` prefixes.

### Just-completed (prior session)

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

- **R2 → mE5-large @ 0.84**: bge-m3 disqualified for Norwegian dedup (collapse_rate < 0.05).
  mE5-large locked as Q5 embedding model for ADR / Phase 5. Threshold 0.84 is a starting point —
  PARTIAL because no (model,threshold) cleared both bars on this narrow single-day corpus; Phase 5
  must recalibrate on a held-out corpus with genuinely off-topic controls.

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

- 00-05-PLAN.md: R4 Wiki-LLM feasibility spike
- 00-06-PLAN.md: R5 COP/World Monitor spike
- 00-07-PLAN.md: Spike closeout (ADRs + SPIKE-FINDINGS.md + teardown)

### Infrastructure corrections (2026-06-25)

- **No Ollama** — removed from all docs and configs. Stack is oMLX (Mac) + vLLM (Spark) only.
- **DGX Spark now active** — vLLM serving qwen 80B at `http://192.168.10.2:8000/v1`, key=EMPTY. Spark has no internet; models must be transferred from Mac.
- **Embedder**:
  - Mac: `intfloat/multilingual-e5-large` (1024-dim) via oMLX
  - Spark: `Alibaba-NLP/gte-Qwen2-7B-instruct` (7B) via vLLM
- **New source — The Telegraph (UK)**: Added for Ukraine coverage. RSS blocked (bot detection). Recommended path: subscribe to Telegraph Ukraine newsletter → ingest via IMAP bridge (`bridge/imap_to_atom.py`). No new code needed until Phase 4.

### Carried-over open questions

- Q1 World Monitor CCIR/SAB coverage → **R5 spike** (still open).
- Q5 embedding model (bge-m3 vs mE5-large) → **DECIDED: mE5-large @ 0.84** (R2, PARTIAL — recalibrate Phase 5).
