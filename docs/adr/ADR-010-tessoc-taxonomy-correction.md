# ADR-010 — TESSOC Taxonomy Correction

**Status.** Accepted (2026-07-11). Source:
`.planning/research/tessoc-taxonomy-correction.md`. Continues the ADR lineage in
`docs/ARCHITECTURE.md` (ADR-001..004).

---

**Context.** InfoTriage originally interpreted TESSOC as a set of operational
variables: Time, Equipment, Space, Skills, Organization, and Communications. That
interpretation was incorrect. TESSOC is a UK/NATO counterintelligence framework
that categorizes threat actors and their methods.

---

**Decision.** Correct TESSOC to the threat-actor taxonomy: **Terror, Espionage,
Subversion, Sabotage, and Organized Crime**. Adopt it as doctrine in InfoTriage
regardless of academic contestation.

| Category | Definition | Example CCIR |
|---|---|---|
| **Terror** | Terrorism, violent extremism, attacks against civilians or symbolic targets. | SIR-1, SIR-2 |
| **Espionage** | Spying, intelligence collection, covert information gathering by state or non-state actors. | PIR-1, PIR-2, PIR-4 |
| **Subversion** | Undermining authority, influence operations, destabilization, fifth-column activity. | PIR-4, PIR-5 |
| **Sabotage** | Deliberate destruction or disruption of infrastructure, logistics, or capabilities. | PIR-4, FFIR-1 |
| **Organized Crime** | Criminal networks, trafficking, money laundering, racketeering, corruption. | PIR-6, SIR-2 |

---

**Consequences.**

- **Doctrinal accuracy.** TESSOC is now aligned with UK *Joint Doctrine
  Publication* 2-00, *Intelligence, Counter-Intelligence and Security Support to
  Joint Operations*.
- **Analytical clarity.** The threat-actor categories align with the types of
  items InfoTriage processes (sabotage of infrastructure, espionage, influence
  operations, etc.).
- **Operational utility.** The old operational-variable interpretation (Time,
  Equipment, Space, etc.) did not map cleanly to open-source news items and was
  not useful for triage.
- **Academic context acknowledged.** Davies & Steward (2024), "The Trouble with
  TESSOC," *Defence Studies*, critiques the framework for conflating
  counterintelligence with internal security and law enforcement. InfoTriage
  acknowledges this debate but uses TESSOC as an operational analytical framework
  nonetheless.

**Changed files.** `ccir.md`; `apps/triage/triage_score.py` (prompt examples, JSON
schema, worked examples); `apps/triage/sab_html.py` (`TESSOC_ICONS`); tests
(`test_score_parse.py`, `test_triage_worker.py`, `test_brief_renderer.py`); seed
scripts.

**Validation.** Full pytest suite passes (275 passed, 2 skipped); code search for
old TESSOC values (`Time`, `Equipment`, `Space`, `Skills`, `Organization`,
`Communications`) in Python files returns 0 matches; `ccir.md` markdown renders
correctly.

**Related notes.** See `.planning/research/tessoc-taxonomy-correction.md` for the
original research note, and `docs/adr/ADR-009-pmesii-hybrid-definitions.md` for
PMESII.
