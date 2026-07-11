# PMESII AJP-01 / AJP-5 Citation Addition

**Date:** 2026-07-11  
**Status:** Adopted  
**Scope:** `ccir.md`

## Context

The PMESII section in `ccir.md` described the six operational-environment domains but lacked a doctrinal citation. The TESSOC section already cited UK JDP 2-00 and Davies & Steward (2024). For consistency and credibility, PMESII needed a similar citation.

## Decision

Add a citation to NATO AJP-01 (*Allied Joint Doctrine*) and AJP-5 (*Allied Joint Doctrine for Planning*) in the PMESII section of `ccir.md`. The citation style mirrors the existing TESSOC citation (doctrinal publication + optional academic follow-up) for consistency.

## Rationale

- **Doctrinal alignment:** PMESII is a standard NATO analytical framework for understanding the operational environment.
- **Consistency:** The TESSOC section already includes a doctrinal citation; PMESII should too.
- **Transparency:** Future maintainers can trace the framework back to authoritative sources.

## What changed

The PMESII section introduction in `ccir.md` now reads:

> PMESII kategoriserer domener i det operasjonelle miljøet (operational environment domains). Rammeverket er etablert i NATO fellesdoktrine: **Political, Military, Economic, Social, Infrastructure, Information** (NATO *Allied Joint Publication* 01, *Allied Joint Doctrine*; se også AJP-5, *Allied Joint Doctrine for Planning*).

## Related notes

- [PMESII hybrid definitions](pmesii-hybrid-definitions.md)
- [TESSOC taxonomy correction](tessoc-taxonomy-correction.md)
- **Formal ADR:** [ADR-011 — PMESII AJP-01 / AJP-5 Citation](../../docs/adr/ADR-011-pmesii-ajp01-ajp5-citation.md)

## References

- NATO AJP-01, *Allied Joint Doctrine*
- NATO AJP-5, *Allied Joint Doctrine for Planning*

## Validation

- `ccir.md` markdown renders correctly.
- Full pytest suite: 275 passed, 2 skipped.
