# ADR-012 — DIMEFIL / COP / CIP / CRP Evaluation

**Status.** Accepted (2026-07-11). Source:
`.planning/research/dimefil-cop-cip-evaluation.md`. Continues the ADR lineage in
`docs/ARCHITECTURE.md` (ADR-001..004).

---

**Context.** InfoTriage enriches each item with PMESII (operational-environment
domain) and TESSOC (threat-actor category). The user asked whether to add
**DIMEFIL** (Diplomatic, Information, Military, Economic, Financial,
Intelligence, Law Enforcement) as a third analytical axis, and how COP/CIP/CRP
concepts should fit.

---

**Decision.**

1. **Do not add DIMEFIL as a new LLM axis.** DIMEFIL is an informal extension of
   DIME used in professional military education and academic research; it is
   **not official US or NATO doctrine**. It also overlaps heavily with existing
   PMESII/TESSOC/CCIR tags. Revisit only if a concrete use case for
   "instruments of national power" briefs emerges.

2. **Implement COP/CIP/CRP as output views/lenses**, not new LLM axes. The LLM
   already produces enough tags; these pictures become SQL/UI filters on top of
   existing enrichment data.

| View | Filter |
|---|---|
| **COP — Operational Picture** | `ccir IN (FFIR-1, FFIR-2, FFIR-3, PIR-3, SIR-2, SIR-3)` + `pmesii IN (Political, Military, Infrastructure)` |
| **CIP — Intelligence Picture** | `tessoc != 'none'` + `ccir LIKE 'PIR-%'` + `pmesii IN (Information, Military, Economic)` |
| **CRP — Relevant Picture** | User-configurable combination of CCIR, PMESII, TESSOC, score, and date range. |

---

**Consequences.**

- **Doctrinal rigor preserved.** PMESII and TESSOC remain the only LLM-assigned
  analytical axes, both anchored in authoritative doctrine.
- **Prompt simplicity maintained.** The local LLM is not burdened with a third,
  seven-value axis.
- **View-layer extensibility.** COP/CIP/CRP can be added to the brief renderer,
  FastAPI endpoints, or digest templates without touching the scorer.
- **DIMEFIL deferred.** If later needed, DIMEFIL can be added as an optional
  third axis with its own schema migration, taxonomy update, and validation
  cycle.

**Validation.** Research confirmed DIMEFIL is not official doctrine; mapping
shows high overlap with existing tags. Full pytest suite passes (275 passed,
2 skipped).

**Related notes.** See `.planning/research/dimefil-cop-cip-evaluation.md` for the
original research note, and `docs/adr/ADR-013-recognized-picture-doctrine.md` for
the recognized-picture framing.
