# TESSOC Taxonomy Correction

**Date:** 2026-07-11  
**Status:** Adopted  
**Scope:** `ccir.md`, `apps/triage/triage_score.py`, `apps/triage/sab_html.py`, tests, seed scripts

## Context

InfoTriage originally interpreted TESSOC as a set of operational variables: Time, Equipment, Space, Skills, Organization, and Communications. This interpretation was incorrect. TESSOC is a UK/NATO counterintelligence framework that categorizes threat actors and their methods.

## Decision

Correct TESSOC to the threat-actor taxonomy: **Terror, Espionage, Subversion, Sabotage, and Organized Crime**. Adopt it as doctrine in InfoTriage regardless of academic contestation.

## Rationale

- **Doctrinal accuracy:** TESSOC is established in UK *Joint Doctrine Publication* 2-00, *Intelligence, Counter-Intelligence and Security Support to Joint Operations*.
- **Analytical clarity:** The threat-actor categories align with the types of items InfoTriage processes (sabotage of infrastructure, espionage, influence operations, etc.).
- **Operational utility:** The old operational-variable interpretation (Time, Equipment, Space, etc.) did not map cleanly to open-source news items and was not useful for triage.

## What changed

| Area | Before | After |
|---|---|---|
| `ccir.md` | TESSOC described as operational variables | TESSOC described as threat-actor taxonomy with citation |
| `apps/triage/triage_score.py` | Prompt examples used old values | Prompt examples, JSON schema, and worked examples use new values |
| `apps/triage/sab_html.py` | `TESSOC_ICONS` mapped to old values | Updated to new threat-actor icons |
| Tests | Used `Time`, `Equipment`, etc. | Updated to `Terror`, `Subversion`, etc. (`tests/test_score_parse.py`, `tests/test_triage_worker.py`, `tests/test_brief_renderer.py`) |
| Seed scripts | Used old values | Updated to new values |

## New TESSOC categories

| Category | Definition | Example CCIR |
|---|---|---|
| **Terror** | Terrorism, violent extremism, attacks against civilians or symbolic targets. | SIR-1, SIR-2 |
| **Espionage** | Spying, intelligence collection, covert information gathering by state or non-state actors. | PIR-1, PIR-2, PIR-4 |
| **Subversion** | Undermining authority, influence operations, destabilization, fifth-column activity. | PIR-4, PIR-5 |
| **Sabotage** | Deliberate destruction or disruption of infrastructure, logistics, or capabilities. | PIR-4, FFIR-1 |
| **Organized Crime** | Criminal networks, trafficking, money laundering, racketeering, corruption. | PIR-6, SIR-2 |

## Academic context

TESSOC is contested in academic literature. Davies & Steward (2024), "The Trouble with TESSOC," *Defence Studies*, critiques the framework for conflating counterintelligence with internal security and law enforcement. InfoTriage acknowledges this debate but uses TESSOC as an operational analytical framework nonetheless.

## Validation

- Full pytest suite: 275 passed, 2 skipped.
- Code search for old TESSOC values (`Time`, `Equipment`, `Space`, `Skills`, `Organization`, `Communications`) in Python files: 0 matches.
- `ccir.md` markdown renders correctly.

## Related notes

- [PMESII hybrid definitions](pmesii-hybrid-definitions.md)
- [PMESII AJP-01 / AJP-5 citation](pmesii-citation-ajp01-ajp5.md)
- **Formal ADR:** [ADR-010 — TESSOC Taxonomy Correction](../../docs/adr/ADR-010-tessoc-taxonomy-correction.md)

## References

- UK JDP 2-00, *Intelligence, Counter-Intelligence and Security Support to Joint Operations*
- Davies & Steward (2024), "The Trouble with TESSOC," *Defence Studies*
