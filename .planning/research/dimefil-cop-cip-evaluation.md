# DIMEFIL / COP / CIP / CRP Evaluation

**Date:** 2026-07-11  
**Status:** Adopted (view-layer recommendation); DIMEFIL deferred pending stronger need  
**Scope:** Analytical framework expansion beyond PMESII/TESSOC

## Context

InfoTriage currently enriches each item with two analytical axes:

- **PMESII** — operational-environment domain (Political, Military, Economic, Social, Information, Infrastructure).
- **TESSOC** — threat-actor category (Terror, Espionage, Subversion, Sabotage, Organized Crime).

The user asked whether to add **DIMEFIL** (Diplomatic, Information, Military, Economic, Financial, Intelligence, Law Enforcement) as a third axis, and how **COP / CIP / CRP** concepts should fit.

## Research summary

### DIMEFIL

DIMEFIL is an **informal extension** of the traditional **DIME** (Diplomatic, Information, Military, Economic) instruments-of-national-power model. It adds **Financial**, **Intelligence**, and **Law Enforcement**.

| Dimension | Definition | OSINT example |
|---|---|---|
| **Diplomatic** | Statecraft, treaties, alliances, negotiations, diplomatic pressure. | G7 joint statement on Russia sanctions. |
| **Information** | Information environment, narratives, propaganda, strategic communications. | Counter-disinformation campaign during an election. |
| **Military** | Force or credible threat of force. | Carrier strike group deployment to the Eastern Mediterranean. |
| **Economic** | Trade, sanctions, foreign aid, investment, market leverage. | EU ban on Russian oil imports. |
| **Financial** | Capital flows, currency controls, asset freezes, banking networks. | Treasury/DOJ seizure of cartel assets; SWIFT exclusions. |
| **Intelligence** | Collection, analysis, covert information advantage. | Declassified satellite imagery of troop movements. |
| **Law Enforcement** | Justice systems, policing, regulatory action, criminal prosecution. | International arrest warrants for sanctions evaders. |

**Doctrinal status:** DIMEFIL is **not official US or NATO doctrine**. Official doctrine remains DIME. DIMEFIL appears in professional military education (Air University, Joint Force Quarterly) and academic writing as a "colloquial" extension for gray-zone analysis.

**Relationship to PMESII:**

- **DIMEFIL** = *instrument-focused* (tools a nation uses to project power).
- **PMESII** = *environment-focused* (conditions of the operational environment).
- They are complementary but overlapping: a sanctions story is **Economic** in PMESII and **Economic/Financial** in DIMEFIL.

### COP / CIP / CRP

| Concept | Definition | InfoTriage mapping |
|---|---|---|
| **COP — Common Operational Picture** | Shared view of friendly forces, operational environment, and ongoing operations. | Output view: FFIRs + PIR-3 + PMESII Infrastructure/Political/Military. |
| **CIP — Common Intelligence Picture** | Shared view of adversary/threat forces, intentions, and capabilities. | Output view: TESSOC != none + PIRs + PMESII Information/Military. |
| **CRP — Common Relevant Picture** | Tailored view of COP/CIP data for a specific decision-maker. | Configurable digest lens combining CCIR, PMESII, TESSOC, and optionally DIMEFIL filters. |

**Key insight:** COP/CIP/CRP are **output views or lenses**, not new analytical axes. The LLM already produces enough tags; these pictures become SQL/UI filters on top of them.

## Recommendation

### 1. Do not add DIMEFIL as a new LLM axis now

**Rationale:**

- **Not doctrine.** DIMEFIL is not official US/NATO doctrine, unlike PMESII (AJP-01/AJP-5) and TESSOC (UK JDP 2-00). Adding it would dilute the doctrinal rigor we just established.
- **Overlap with existing tags.** Most DIMEFIL dimensions map cleanly to PMESII + TESSOC + CCIR:
  - Diplomatic → PMESII Political
  - Information → PMESII Information
  - Military → PMESII Military
  - Economic → PMESII Economic
  - Financial → PMESII Economic (or TESSOC Organized Crime for illicit finance)
  - Intelligence → TESSOC Espionage or PMESII Information
  - Law Enforcement → TESSOC Organized Crime
- **Prompt complexity.** Adding a 7-value third axis increases cognitive load for the local LLM and risks inconsistent classification.
- **No current user need.** The existing two axes cover the Norway-focused OSINT brief well.

**When to revisit:** If the user later wants to produce briefs explicitly framed around "instruments of national power" (e.g., "show me all Financial/Law Enforcement actions against Russia"), DIMEFIL can be added as an optional third axis with its own validation cycle.

### 2. Implement COP/CIP/CRP as output views

**Rationale:**

- The LLM already produces enough tags.
- COP/CIP/CRP are **views**, not new classifications.
- They can be implemented as SQL filters + digest presets without touching the scorer.

**Proposed views:**

| View | Filter |
|---|---|
| **COP — Operational Picture** | `ccir IN (FFIR-1, FFIR-2, FFIR-3, PIR-3, SIR-2, SIR-3)` + `pmesii IN (Political, Military, Infrastructure)` |
| **CIP — Intelligence Picture** | `tessoc != 'none'` + `ccir LIKE 'PIR-%'` + `pmesii IN (Information, Military, Economic)` |
| **CRP — Relevant Picture** | User-configurable combination of CCIR, PMESII, TESSOC, score, and date range. |

These views can be exposed as:

- CLI flags on the brief renderer (e.g., `--view cop`, `--view cip`).
- FastAPI query parameters on the brief service.
- Pre-defined markdown digest templates.

## Alternatives considered

| Alternative | Verdict |
|---|---|
| Add DIMEFIL as third LLM axis now | Rejected — not doctrine, overlaps existing tags, adds prompt complexity. |
| Add DIME only (not DIMEFIL) | Rejected — same overlap issues; Financial/Intelligence/Law Enforcement are the only novel parts, and they are already covered. |
| Add COP/CIP/CRP as new LLM axes | Rejected — they are views, not classifications. |
| Add PMESII-PT or ASCOPE | Rejected earlier for PMESII expansion; still not relevant. |

## Implementation implications (if DIMEFIL is ever adopted)

1. **Schema:** Add `dimefil TEXT` to `infotriage.enrichment`.
2. **Taxonomy (`ccir.md`):** Add a DIMEFIL section defining the seven dimensions.
3. **Prompt (`triage_score.py`):** Add `dimefil` to the JSON schema and worked examples.
4. **Tests:** Update `test_score_parse.py`, `test_triage_worker.py`, etc.
5. **Views:** COP/CIP/CRP views can optionally include `dimefil` in their filters.

## Validation

- Research confirmed DIMEFIL is not official doctrine.
- Mapping table shows high overlap with existing PMESII/TESSOC/CCIR tags.
- Recommendation defers implementation until a concrete use case emerges.

## Related notes

- [PMESII hybrid definitions](pmesii-hybrid-definitions.md)
- [TESSOC taxonomy correction](tessoc-taxonomy-correction.md)
- [PMESII AJP-01 / AJP-5 citation](pmesii-citation-ajp01-ajp5.md)
- [Recognized Picture doctrine](recognized-picture-doctrine.md) — RAP, RMP, RIP, and the JDL fusion levels
- **Formal ADR:** [ADR-012 — DIMEFIL / COP / CIP / CRP Evaluation](../../docs/adr/ADR-012-dimefil-cop-cip-evaluation.md)

## References

- Air University Library Research Guide: DIMEFIL
- Rodriguez, C. A., et al. (2020), "Putting the 'FIL' into 'DIME': Growing Joint Understanding of the Instruments of Power," *Joint Force Quarterly*, Issue 97.
- McDonnell, J. P. (2009), "National Strategic Planning: Linking DIMEFIL/PMESII to a Theory of Victory," Joint Forces Staff College.
- NATO AJP-3, *Allied Joint Doctrine for the Conduct of Operations*
- US JP 2-0, *Joint Intelligence*
