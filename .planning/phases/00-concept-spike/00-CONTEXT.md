# Phase 0: Concept spike - Context

**Gathered:** 2026-06-24
**Status:** Ready for planning

<domain>
## Phase Boundary

A throwaway spike that resolves five unproven architectural unknowns with falsifiable go/no-go
(or documented "partial") answers before any production build — RabbitMQ topology, Norwegian
semantic dedup, Postgres entity resolution, Wiki-LLM feasibility, and COP/World Monitor need.
Does NOT re-spike the already-working, tested ingest→score→brief pipeline (incl. PMESII/TESSOC).

</domain>

<spec_lock>
## Requirements (locked via SPEC.md)

**5 requirements are locked.** See `00-SPEC.md` for full requirements, boundaries, and acceptance criteria.

Downstream agents MUST read `00-SPEC.md` before planning or implementing. Requirements are not duplicated here.

**In scope (from SPEC.md):**
- Throwaway prototypes answering the 5 unknowns (R1 RabbitMQ topology, R2 dedup, R3 entity resolution, R4 Wiki-LLM, R5 COP/World Monitor).
- ADR stubs ADR-005 (COP/World Monitor), ADR-006 (microservice arch + entity resolution), ADR-007 (RabbitMQ), ADR-008 (self-hosted MCP/OAuth2 ingestion).
- `SPIKE-FINDINGS.md` in the phase dir holding raw results + per-unknown go/no-go/partial.

**Out of scope (from SPEC.md):**
- Re-spiking ingest→score→brief or the bridges (already tested + verified).
- Any production/durable code, schema migrations, or wiring into the real `apps/`/`libs/` tree.
- Multi-user/auth/tenancy (deferred to Milestone 3).
- Final embedding-infra build (spike only *chooses* the model; building it is Phase 5).

</spec_lock>

<decisions>
## Implementation Decisions

### Test corpus sourcing
- **D-01:** Source spike test data by **fetching fresh from NRK/BBC/TASS** (not reusing
  `data/verdicts.jsonl`, not synthetic). Read-only against sources — honors the SPEC constraint;
  no mutation of prod data/feeds.
- **D-02:** For R2, pick real events all three outlets covered **concurrently** so genuine
  same-story triples exist; the same-story groupings require a **hand-labeling step** to measure
  the ≥80% collapse rate (and to seed control items that must NOT over-merge).
- **D-03:** R4 (≥5 corpus items) and R5 (20 InfoTriage items) **reuse the same fresh-fetched items**,
  run through the existing pipeline where needed, rather than fetching a second independent set.

### Spike infrastructure footprint
- **D-04:** Stand up Postgres+pgvector (R3) and RabbitMQ (R1) as **ephemeral throwaway containers**
  — separate compose/`docker run`, distinct ports, torn down after. **Must not** touch the running
  `:8088`/`:3000` stack or production data. Strongest isolation; consistent with read-only +
  throwaway constraints.

### World Monitor approach (R5)
- **D-05:** Evaluate the COP go/no-go by **cloning and running the real World Monitor repo** against
  oMLX (local LLM, ADR-004) to score 20 items + write a CCIR-structured brief — the truest
  adopt/build/drop signal for ADR-005. (Cross-ref SP-COP spike.)

### Spike code lifecycle
- **D-06:** After ADRs (005–008) + `SPIKE-FINDINGS.md` are written, **delete the throwaway spike
  code**. ADRs + SPIKE-FINDINGS.md are the only durable record. Spike code never merges to
  `apps/`/`libs/`. (No spike-findings skill packaging; findings live in the markdown artifacts.)

### Claude's Discretion
- Exact scratch directory location for throwaway code (kept out of `apps/`/`libs/`).
- Embedding model serving mechanism for the bge-m3 vs mE5-large bake-off (host sentence-transformers
  / oMLX / Ollama) — researcher/planner choose; the *outcome* (chosen model + threshold) is what R2 locks.
- Spike sequencing among the 5 unknowns and any early-exit on a documented "partial".
- Same-story event selection and labeling format for the R2 triple set.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase requirements (locked)
- `.planning/phases/00-concept-spike/00-SPEC.md` — Locked requirements, acceptance bars, boundaries, prohibitions. MUST read before planning.

### Architecture source-of-truth
- `docs/superpowers/specs/2026-06-24-app-split-architecture-design.md` — Design source-of-truth for the re-architecture (the 5 unknowns originate here).
- `docs/ARCHITECTURE.md` — ADRs + Phase 0–4 plan; ADR-003 north-star; ADR-004 (all-local LLM, load-bearing in the spike).
- `docs/RESEARCH-REPORT.md` — 2026-06-23 prior art (World Monitor §1–2, Taranis §3, embedding model choice §8). Relevant to R2 and R5.

### Project frame + requirements
- `.planning/PROJECT.md` — Hard constraints (all-local LLM, no paid services, read-only sources, throwaway).
- `.planning/REQUIREMENTS.md` — Status map; P-5/P-7/A-1 (Q5 embedding choice → R2), N-1/N-2 (Q1 World Monitor → R5), A-3 (entity graph → R3).
- `.planning/ROADMAP.md` — Phase 0 success criteria + downstream phase dependencies (P2 storage, P3 bus, P5 dedup, P8 entity res, P10 Wiki-LLM).
- `ccir.md` — Triage taxonomy; R5 CCIR-structured brief scores against it.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `data/verdicts.jsonl` (176KB, real scored corpus): NOT used as the R2/R3 source (D-01 chose fresh fetch), but available as a reference/comparison oracle for what "real" InfoTriage items look like.
- `score/triage_score.py` (`llm()` env contract; oMLX `:8000/v1`, Ollama `:11434/v1` fallback): the local-LLM call pattern the spike reuses for R4/R5 (ADR-004 compliance).
- `bridge/` (`imap_to_atom.py`, `yt_to_atom.py` — verified working): fetch/atom-gen patterns reusable for fresh NRK/BBC/TASS pulls if a fetcher is needed.
- `score/digest.py` `cluster()` (keyword-overlap): the current dedup baseline R2's embedding approach is measured *against*.

### Established Patterns
- All-local LLM (ADR-004) is non-negotiable inside the spike runtime — no cloud LLM endpoint in any spike config.
- Read-only against sources; spike must not mutate `data/verdicts.jsonl`, real feeds, or the running pipeline.
- Stdlib-first; existing Docker stack on `:8088`/`:3000` — spike infra uses *distinct* ports/containers.

### Integration Points
- None durable — this phase produces ADRs + findings only; no wiring into `apps/`/`libs/`. Findings feed planning for P2/P3/P5/P8/P10 and SP-COP.

</code_context>

<specifics>
## Specific Ideas

- "Palantir Gotham-grade fusion at personal scale" is the north-star the COP/World Monitor decision (R5) serves — the adopt/build/drop call should be judged against that aspiration but grounded in the real 20-item test, not aspiration.
- Embedding bake-off is explicitly bge-m3 vs mE5-large (RESEARCH-REPORT §8 / REQUIREMENTS Q5); pick one model + one cosine threshold.

</specifics>

<deferred>
## Deferred Ideas

- Building the final embedding infrastructure — Phase 5 (spike only chooses the model).
- Entity resolution production schema + Obsidian projection — Phase 8.
- Wiki-LLM production (standing auto-wiki + on-demand) — Phase 10.
- Full COP/map UI build — SP-COP gated spike / later, depending on R5 verdict.
- Multi-user / auth / tenancy — Milestone 3.

</deferred>

---

*Phase: 0-concept-spike*
*Context gathered: 2026-06-24*
