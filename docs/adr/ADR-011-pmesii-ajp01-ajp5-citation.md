# ADR-011 — PMESII AJP-01 / AJP-5 Citation

**Status.** Accepted (2026-07-11). Source:
`.planning/research/pmesii-citation-ajp01-ajp5.md`. Continues the ADR lineage in
`docs/ARCHITECTURE.md` (ADR-001..004).

---

**Context.** The PMESII section in `ccir.md` described the six
operational-environment domains but lacked a doctrinal citation. The TESSOC
section already cited UK JDP 2-00 and Davies & Steward (2024). For consistency
and credibility, PMESII needed a similar citation.

---

**Decision.** Add a citation to NATO AJP-01 (*Allied Joint Doctrine*) and AJP-5
(*Allied Joint Doctrine for Planning*) in the PMESII section of `ccir.md`.
The citation style mirrors the existing TESSOC citation (doctrinal publication
+ optional academic follow-up) for consistency.

The PMESII section introduction now reads:

> PMESII kategoriserer domener i det operasjonelle miljøet (operational
> environment domains). Rammeverket er etablert i NATO fellesdoktrine:
> **Political, Military, Economic, Social, Infrastructure, Information** (NATO
> *Allied Joint Publication* 01, *Allied Joint Doctrine*; se også AJP-5, *Allied
> Joint Doctrine for Planning*).

---

**Consequences.**

- **Doctrinal alignment.** PMESII is now explicitly anchored to NATO's
  authoritative joint doctrine.
- **Consistency.** The PMESII citation matches the style and rigor of the TESSOC
  citation.
- **Transparency.** Future maintainers can trace the framework back to
  authoritative sources.
- **Scope limited to `ccir.md`.** The LLM prompt in
  `apps/triage/triage_score.py` inlines `ccir.md`, so the citation flows to the
  model automatically.

**Validation.** `ccir.md` markdown renders correctly; full pytest suite passes
(275 passed, 2 skipped).

**Related notes.** See `.planning/research/pmesii-citation-ajp01-ajp5.md` for
the original research note, and `docs/adr/ADR-009-pmesii-hybrid-definitions.md`
for the hybrid-definitions decision.
