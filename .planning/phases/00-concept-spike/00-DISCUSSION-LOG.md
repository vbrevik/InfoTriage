# Phase 0: Concept spike - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-24
**Phase:** 0-concept-spike
**Areas discussed:** Test corpus sourcing, Spike infra footprint, World Monitor approach, Spike code lifecycle

---

## Test corpus sourcing

| Option | Description | Selected |
|--------|-------------|----------|
| Reuse + curate verdicts.jsonl | Pull triples & entities from the existing 176KB real scored corpus + cached feeds; hand-label same-story groupings. Read-only. | |
| Fetch fresh NRK/BBC/TASS | Pull live same-story sets now for max realism on current events. | ✓ |
| Hand-curate synthetic set | Author a small labeled fixture by hand for tight control over edge cases. | |

**User's choice:** Fetch fresh NRK/BBC/TASS
**Notes:** Needs events all three outlets covered concurrently + a hand-labeling step for R2 triples; R4/R5 reuse the same fresh items through the pipeline.

---

## Spike infra footprint

| Option | Description | Selected |
|--------|-------------|----------|
| Ephemeral throwaway containers | Separate compose/docker-run on distinct ports, torn down after; never touches the running stack or prod data. | ✓ |
| Extend existing docker-compose | Add pg/rabbit to the current stack. | |
| Local host installs | brew/pip on host, no Docker. | |

**User's choice:** Ephemeral throwaway containers
**Notes:** Strongest isolation; consistent with read-only + throwaway SPEC constraints.

---

## World Monitor approach (R5)

| Option | Description | Selected |
|--------|-------------|----------|
| Clone & run real repo | Run actual World Monitor vs oMLX, score 20 items + CCIR brief. Truest adopt/build/drop signal. | ✓ |
| Minimal CCIR harness mimic | Quick script scoring 20 items + writing a CCIR brief. Weaker adopt signal. | |
| Timeboxed clone, fall back | Attempt the real clone; drop to harness if setup fights back. | |

**User's choice:** Clone & run real repo
**Notes:** Directly informs ADR-005 adopt/build/drop; oMLX (ADR-004) local-LLM only.

---

## Spike code lifecycle

| Option | Description | Selected |
|--------|-------------|----------|
| Package as spike-findings skill | Wrap validated patterns/landmines into a project-local skill for downstream pickup. | |
| Archive to .planning/spikes/ | Keep raw scratch + results, no skill packaging. | |
| Delete after ADRs written | ADRs + SPIKE-FINDINGS.md are the only durable record; scratch deleted. | ✓ |

**User's choice:** Delete after ADRs written
**Notes:** Cleanest tree; findings preserved in ADRs 005–008 + SPIKE-FINDINGS.md.

---

## Claude's Discretion

- Exact scratch directory location for throwaway code.
- Embedding model serving mechanism for the bge-m3 vs mE5-large bake-off (the *outcome* — chosen model + threshold — is what R2 locks).
- Spike sequencing among the 5 unknowns and early-exit on a documented "partial".
- Same-story event selection + labeling format for the R2 triple set.

## Deferred Ideas

- Final embedding-infra build — Phase 5.
- Entity resolution production schema + Obsidian projection — Phase 8.
- Wiki-LLM production — Phase 10.
- Full COP/map UI build — SP-COP / later, gated on R5 verdict.
- Multi-user / auth / tenancy — Milestone 3.
