# ADR-006 — Microservice architecture + Postgres/pgvector entity resolution

**Status.** Accepted (2026-06-27). Source: Phase 0 spike R3 (`findings/R3-VERDICT.md`,
`.planning/phases/00-concept-spike/SPIKE-FINDINGS.md`) + the locked app-split re-architecture
(`docs/superpowers/specs/2026-06-24-app-split-architecture-design.md`). Continues the ADR lineage in
`docs/ARCHITECTURE.md` (ADR-001..004).

---

**Context.** The re-architecture (2026-06-24) splits InfoTriage from a monolithic spike into
**cooperating microservices** (ingest adapters → canonical Postgres store → triage → brief →
notify), coordinated over the RabbitMQ bus (ADR-007). Analysis requires linking the **same entity**
(person, org, place) across items and languages — none of which the spike had (no `entities` /
`entity_links` schema, no resolution). R3 spiked whether pgvector cosine linking can do this on
real corpus data.

---

**Decision.**

1. **Microservice frame.** Services communicate over the RabbitMQ event bus (ADR-007); **PostgreSQL
   is the single system of record** (ADR-001) holding the canonical item store + enrichment +
   pgvector embeddings + the entity graph. Each service owns its stage of the intelligence cycle and
   stays independently deployable.

2. **Entity-resolution schema (validated by R3, for Phase 8):**
   - `entities (id, name, name_norm, lang, type, embedding vector(1024))`
   - `entity_links (entity_id FK, item_id, mention, lang)`
   - **Linking:** pgvector **HNSW** index with `vector_cosine_ops`, the `<=>` cosine operator, and
     **`LINK_THRESHOLD = 0.85`**. Entity mentions are NER-extracted by the **local** qwen36 (oMLX,
     ADR-004) — no cloud.

R3 proved the mechanism on real data: 285 entities from 144 items, 599 entity_links; **NATO merged
to a single entity_id (166) across 5 items**; control entities **kept distinct** (Trump entity_id=6
≠ Putin entity_id=189; cosine ~0.72 ≪ 0.85). The entity graph is the spine of the SP-COP network
half (ADR-005, Phase 8).

---

**Consequences.**

- **PARTIAL verdict — cross-language coverage is conditional, not a pass.** R3 met every acceptance
  bar **except** the ≥2-language bar: all 5 NATO mentions came from TASS (`lang=ru`) because the
  2026-06-25 NRK/BBC feeds had zero NATO mentions. This is a **corpus-composition** limitation, not
  a mechanism failure — but it is recorded as a partial (SPEC Constraint: never silently elevated).
  Phase 8 must use corpus diversification (multi-day rolling window, multiple feeds per language) to
  create cross-language merge opportunities and re-confirm the ≥2-language bar.

- **R3/R2 embedding-model divergence — Phase-8 re-validation RISK.** R3 validated the 0.85 link
  threshold on **`BAAI/bge-m3`** vectors (R3 ran before R2 decided; the model string an R3 auto-parser
  captured was a misparse). R2 (`findings/R2-VERDICT.md`) chose **`mE5-large` @ 0.84** as the
  production embedding model. These differ. **Phase 8 must re-validate entity linking (threshold +
  control separation) on mE5-large vectors before production** — the 0.85 threshold is not
  transferable across embedding models without re-measurement. See SPIKE-FINDINGS.md "R3/R2
  Embedding-Model Divergence Note".

- **Dependency note.** The spike used a torchvision-mock workaround (`torchvision 0.24.0.dev` vs
  `torch 2.11.0` broken `nms`); Phase 8 needs a resolved dependency environment, not the throwaway
  workaround.

- **Downstream.** The entity graph feeds Phase 8 (entity resolution), Phase 10 (Wiki-LLM on-demand
  gather reuses `entity_links` — see R4), and SP-COP's network half (ADR-005).
