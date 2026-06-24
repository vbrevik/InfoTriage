# Phase 0: Concept spike — Specification

**Created:** 2026-06-24
**Ambiguity score:** 0.18 (gate: ≤ 0.20)
**Requirements:** 5 locked

## Goal

Resolve the five unproven architectural unknowns with falsifiable go/no-go answers — via throwaway
prototypes — before any production build begins, without re-validating the already-working
ingest→score→brief pipeline.

## Background

The spike (ingest → score → brief, incl. PMESII/TESSOC) already runs on host Python and is tested
(56 tests pass); bridges are verified by execution; Gmail is proven via OAuth2/MCP. What does NOT yet
exist is any code for the new architecture (Postgres, RabbitMQ, pgvector, entity resolution,
Wiki-LLM, COP). Several of those carry real risk that could change the design if assumed wrong. This
phase de-risks exactly those, and nothing already proven. Design source-of-truth:
`docs/superpowers/specs/2026-06-24-app-split-architecture-design.md`.

## Requirements

1. **RabbitMQ topology**: A working AMQP publish→consume round-trip proves the broker model for our events.
   - Current: no bus code exists; transport chosen (RabbitMQ) but topology unproven.
   - Target: a throwaway prototype with exchanges + routing keys for the 4 event types, publishing across 2 dummy services with acks + a DLQ.
   - Acceptance: a message published by service A is consumed by service B via the designed routing; a poisoned message lands in the DLQ. Outcome recorded in ADR-007.

2. **Norwegian semantic dedup**: Embedding dedup collapses same-story cross-language items at a measured rate.
   - Current: dedup is keyword overlap; fails across NRK/BBC/TASS phrasings/languages.
   - Target: a chosen embedding model (bge-m3 vs mE5-large) + cosine threshold that collapses a labeled test set.
   - Acceptance: on ≥10 NRK/BBC/TASS same-story triples, **≥80% of triples collapse** to one cluster at a single chosen threshold without over-merging unrelated control items; model + threshold recorded.

3. **Postgres entity resolution**: pgvector links entity mentions across items and languages.
   - Current: no entities/entity_links schema; no resolution.
   - Target: a prototype `entities` + `entity_links` schema + linking query on sample data.
   - Acceptance: one known entity is resolved across **≥3 items spanning 2 languages** into a single entity, without merging a distinct control entity. Outcome recorded in ADR-006.

4. **Wiki-LLM feasibility**: Local models synthesize a coherent, cited wiki page from the corpus.
   - Current: no Wiki-LLM code; feasibility on qwen36/DGX unknown.
   - Target: a throwaway generation of (a) one standing entity/topic wiki page and (b) one on-demand article.
   - Acceptance: the standing page is synthesized from **≥5 real corpus items**, carries citations back to source IDs, and is judged coherent; one on-demand article is produced. Sample saved to SPIKE-FINDINGS.md.

5. **COP need + World Monitor**: The COP decision is grounded in a real test, not aspiration.
   - Current: COP is aspiration ("Palantir at personal scale"); World Monitor unproven for CCIR/SAB.
   - Target: run World Monitor against oMLX on a sample (cross-ref SP-COP spike).
   - Acceptance: World Monitor **scores 20 InfoTriage items + writes a CCIR-structured brief**; adopt/build/drop decision recorded in ADR-005.

## Boundaries

**In scope:**
- Throwaway prototypes answering the 5 unknowns above.
- ADR stubs ADR-005 (COP/World Monitor), ADR-006 (microservice architecture + entity resolution), ADR-007 (RabbitMQ), ADR-008 (self-hosted MCP/OAuth2 ingestion).
- `SPIKE-FINDINGS.md` in the phase dir holding raw results + per-unknown go/no-go/partial.

**Out of scope:**
- Re-spiking ingest → score → brief or the bridges — already tested + verified (no risk to retire).
- Any production/durable code, schema migrations, or wiring into the real `apps/`/`libs/` tree — this is throwaway.
- Multi-user/auth/tenancy — deferred to Milestone 3.
- Final embedding-infra build — the spike only *chooses* the model; building it is Phase 5.

## Constraints

- **ADR-004 (all-local LLM)** holds even in the throwaway spike — no cloud LLM in any spike runtime.
- **No effort time-box**: run until each of the 5 unknowns has a firm go/no-go (or an explicitly documented "partial"). A partial result is allowed but must be recorded as such, never silently treated as a pass.
- **Read-only against production data**: the spike must not mutate `data/verdicts.jsonl`, real feed files, or the running pipeline.
- Throwaway code lives in a scratch/spike location, never merged into the production tree.

## Acceptance Criteria

- [ ] RabbitMQ: a real publish→consume round-trip across 2 dummy services succeeds; a poisoned message routes to a DLQ. (R1)
- [ ] Dedup: ≥10 NRK/BBC/TASS same-story triples assembled; ≥80% collapse at one chosen threshold with no control over-merge; model + threshold recorded. (R2)
- [ ] Entity resolution: 1 known entity merged across ≥3 items / 2 languages, no control-entity over-merge. (R3)
- [ ] Wiki-LLM: 1 coherent cited standing page from ≥5 corpus items + 1 on-demand article produced; samples saved. (R4)
- [ ] COP: World Monitor scores 20 InfoTriage items + writes a CCIR-structured brief; adopt/build/drop recorded. (R5)
- [ ] ADR-005, ADR-006, ADR-007, ADR-008 stubs written with each decision.
- [ ] `SPIKE-FINDINGS.md` exists with a per-unknown go/no-go/partial verdict.

## Edge Coverage

**Coverage:** 3/3 applicable edges resolved · 0 unresolved

| Category | Requirement | Status | Resolution / Reason |
|----------|-------------|--------|---------------------|
| Inconclusive result | R1–R5 | ✅ covered | Each unknown must end go/no-go/**partial**; partial is documented in SPIKE-FINDINGS.md, never treated as pass (Constraints + AC). |
| Insufficient test sample | R2 | ✅ covered | Acceptance fixes a floor: **≥10 triples**, single threshold, no control over-merge. |
| False merge / over-resolution | R3 | ✅ covered | Acceptance requires a distinct control entity NOT be merged (R3 + R2 control). |

## Prohibitions (must-NOT)

**Coverage:** 3/3 applicable prohibitions resolved · 0 unresolved

| Prohibition (must-NOT statement) | Requirement | Status | Verification / Reason |
|----------------------------------|-------------|--------|------------------------|
| MUST NOT call a cloud LLM in any spike runtime | R1–R5 | resolved | judgment — ADR-004; grep spike configs for cloud endpoints |
| MUST NOT mutate production data (`verdicts.jsonl`, real feeds) or the running pipeline | R1–R5 | resolved | judgment — spike reads copies / sample data only |
| MUST NOT merge throwaway spike code into `apps/`/`libs/` | R1–R5 | resolved | judgment — spike code lives in a scratch dir, deleted/archived at phase end |

## Ambiguity Report

| Dimension          | Score | Min  | Status | Notes                                                        |
|--------------------|-------|------|--------|--------------------------------------------------------------|
| Goal Clarity       | 0.85  | 0.75 | ✓      | 5 unknowns with explicit go/no-go deliverables               |
| Boundary Clarity   | 0.82  | 0.70 | ✓      | Throwaway; working pipeline explicitly out of scope          |
| Constraint Clarity | 0.75  | 0.65 | ✓      | No time-box (run until answered); local-LLM + read-only held |
| Acceptance Criteria| 0.85  | 0.70 | ✓      | All 5 items have falsifiable pass bars                        |
| **Ambiguity**      | 0.18  | ≤0.20| ✓      | Gate passed                                                  |

Status: ✓ = met minimum, ⚠ = below minimum (planner treats as assumption)

## Interview Log

| Round | Perspective | Question summary | Decision locked |
|-------|-------------|------------------|-----------------|
| 1 | Researcher | Spike effort ceiling? | No time-box — run until each of the 5 unknowns is answered |
| 1 | Researcher | Dedup pass bar? | ≥80% of ≥10 NRK/BBC/TASS triples collapse at one threshold |
| 1 | Researcher | Where do findings land? | ADR stubs 005–008 + SPIKE-FINDINGS.md in phase dir |
| 2 | Seed Closer | Wiki-LLM pass bar? | 1 coherent cited page from ≥5 corpus items + 1 on-demand article |
| 2 | Seed Closer | Entity-resolution pass bar? | Merge 1 known entity across ≥3 items / 2 languages, no control over-merge |
| 2 | Seed Closer | RabbitMQ + COP depth? | RabbitMQ working prototype; COP = WM scores 20 items + CCIR brief |
