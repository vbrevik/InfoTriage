# PMESII Hybrid Definitions Decision

**Date:** 2026-07-11  
**Status:** Adopted  
**Scope:** `ccir.md`, `apps/triage/triage_score.py`

## Context

InfoTriage uses PMESII (Political, Military, Economic, Social, Information, Infrastructure) as one of two analytical enrichment axes alongside TESSOC. The PMESII section in `ccir.md` was updated to explicitly reference the NATO doctrinal framing of "operational environment" and to cite AJP-01 and AJP-5.

## Decision

Adopt **hybrid PMESII domain definitions** that prepend a brief NATO-style framing to the existing concrete, OSINT-tailored examples. The definitions are kept in both `ccir.md` (canonical taxonomy) and the hardcoded LLM prompt in `apps/triage/triage_score.py`.

## Rationale

- **Doctrinal accuracy:** NATO describes PMESII as operational-environment domains (AJP-01, AJP-5). The hybrid form makes this explicit.
- **LLM reliability:** A local, quantized LLM (`qwen36-ud-4bit`) performs better with concrete semantic anchors (e.g., "sanctions", "cyber operations", "undersea cables") than with abstract doctrinal language alone.
- **Consistency:** The hardcoded PMESII prompt block in `apps/triage/triage_score.py` was updated to mirror the definitions in `ccir.md`, so the LLM sees the same definitions as the human-readable taxonomy.

## Hybrid definitions

| Domain | Definition |
|---|---|
| **Political** | Power structures and diplomacy; treaties, government policy, elections, sanctions as policy instrument. |
| **Military** | Defense capabilities and warfare; posture, troop movements, weapons systems, military operations. |
| **Economic** | Resource production and markets; sanctions impact, trade wars, defence budgets, financial markets, energy markets. |
| **Social** | Demographic and cultural composition; protests, civil unrest, public opinion, cultural/sporting events with political dimension. |
| **Information** | Information flow and systems; cyber operations, OSINT investigations, propaganda, hybrid influence, media manipulation. |
| **Infrastructure** | Essential facilities; undersea cables, pipelines, logistics networks, energy grid, transport, maritime routes. |

## Alternatives considered

| Alternative | Verdict |
|---|---|
| Pure NATO-style abstract definitions | Rejected — too abstract for the local LLM; risk of misclassification. |
| Keep only concrete examples | Rejected — missed the opportunity to align with NATO doctrinal wording. |
| Add PMESII-PT (Physical Environment, Time) | Rejected — largely duplicates existing CCIR/CNR coverage; low added value for OSINT triage. |
| Add ASCOPE | Rejected — too tactical/civil-affairs focused for a strategic OSINT brief. |

## Validation

- `ccir.md` markdown renders correctly.
- Full pytest suite: 275 passed, 2 skipped.
- `triage_score.py --sample` produces expected scoring output.
- Broader regression test on 20 items (`scripts/regression_pmesii_tessoc.py`) showed no PMESII tag changes attributable to the wording update.

## Related notes

- [TESSOC taxonomy correction](tessoc-taxonomy-correction.md)
- [PMESII AJP-01 / AJP-5 citation](pmesii-citation-ajp01-ajp5.md)
- **Formal ADR:** [ADR-009 — PMESII Hybrid Definitions](../../docs/adr/ADR-009-pmesii-hybrid-definitions.md)

## References

- NATO AJP-01, *Allied Joint Doctrine*
- NATO AJP-5, *Allied Joint Doctrine for Planning*
- UK JDP 2-00, *Intelligence, Counter-Intelligence and Security Support to Joint Operations* (for TESSOC)

## Notes

- The hybrid pattern applies specifically to PMESII. TESSOC was not given hybrid definitions; instead, it was corrected from the old operational-variable interpretation (Time, Equipment, Space, etc.) to the threat-actor taxonomy (Terror, Espionage, Subversion, Sabotage and Organized Crime), with a doctrinal citation and an explicit statement that InfoTriage uses it as doctrine despite academic contestation.
