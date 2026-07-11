# ADR-013 — Recognized Picture Doctrine

**Status.** Accepted (2026-07-11). Source:
`.planning/research/recognized-picture-doctrine.md`. Continues the ADR lineage in
`docs/ARCHITECTURE.md` (ADR-001..004).

---

**Context.** InfoTriage produces a daily SAB (Situation Awareness Brief) from
open-source items. As the project matures, the user wants to align its output
concepts with NATO/US/UK doctrine around situational-awareness pictures:
Common Operational Picture (COP), Common Intelligence Picture (CIP), Common
Relevant Picture (CRP), and the family of domain-specific **Recognized Pictures**
(RP) such as RAP, RMP, RGP, and RIP.

---

**Decision.** Adopt the following doctrinal framing for InfoTriage's output
layers:

- **Recognized Picture (RP)** = a domain-specific, fused, validated picture built
  from correlated data. Examples: RAP (air), RMP (maritime), RGP (ground),
  **RIP (intelligence)**.
- **Common Operational Picture (COP)** = cross-domain, shared operational view
  that integrates multiple RPs plus logistics, weather, cyber, etc.
- **Common Intelligence Picture (CIP)** = adversary-focused intelligence
  assessment; feeds the intelligence layer of the COP.
- **Common Relevant Picture (CRP)** = tailored, decision-maker-specific subset
  of COP/CIP.

InfoTriage does not build real-time RAP/RMP/RGP from sensors, but it
**contributes to and maintains a Recognized Intelligence Picture (RIP)** over
time by fusing, enriching, and deduplicating OSINT items.

---

**Consequences.**

- **Doctrinal alignment.** InfoTriage's daily brief and enrichment store now map
  onto recognized military C2/INT concepts.
- **Clear scope.** InfoTriage is an OSINT/all-source intelligence triage system,
  not a real-time sensor-fusion platform. Its product is the RIP layer, not the
  COP directly.
- **Output views.** COP/CIP/CRP become SQL/UI filters over existing enrichment
  tags (CCIR, CNR, PMESII, TESSOC), not new LLM axes.
- **Future extensibility.** If real-time sensor feeds (AIS, ADS-B, BarentsWatch)
  are added, they can feed RMP/RAP-style sub-pictures that InfoTriage fuses into
  the RIP.

**Doctrinal sources.** NATO AAP-06; NATO AJP-3.3, AJP-3.3.3, AJP-6; US JP 2-0,
JP 3-0, JP 3-01, JP 3-32; UK JDP 2-00; Llinas & White (1987) JDL Data Fusion
Model; Farina et al. (2014).

**Validation.** Research note `.planning/research/recognized-picture-doctrine.md`
rendered correctly; full pytest suite passes (275 passed, 2 skipped).

**Related notes.** See `.planning/research/recognized-picture-doctrine.md` for the
original research note, and `.planning/research/dimefil-cop-cip-evaluation.md`
for the COP/CIP/CRP view-layer recommendation.
