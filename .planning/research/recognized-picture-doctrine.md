# Recognized Picture Doctrine

**Date:** 2026-07-11  
**Status:** Research note  
**Scope:** COP/CIP/CRP family, recognized-picture variants, and doctrinal sources

## Context

The user asked about "recognized ... picture" concepts beyond COP/CIP/CRP — specifically the **Recognized Intelligence Picture** (RIP) and related domain-specific recognized pictures. This note documents doctrinal definitions and sources.

## What is a "Recognized Picture"?

In NATO/US/UK doctrine, a **Recognized Picture (RP)** is an electronically produced, compiled, and maintained display of a specific subset of the battlespace. It integrates data from active and passive sensors to provide a consolidated situational understanding of a domain.

The term "recognized" implies that raw sensor data has been **correlated, associated, identified, and fused** into a coherent, validated picture — not just a raw feed.

## Recognized Picture variants

| Variant | Definition | Typical sources |
|---|---|---|
| **RAP — Recognized Air Picture** | Display compiled from air surveillance data (radar, IFF, data links) to track and identify aircraft and airborne objects. | AWACS, ground radar, ADS-B, IFF |
| **RMP — Recognized Maritime Picture** | Composite display of surface and sub-surface tracks (vessels, submarines) from maritime sensors and reports. | AIS, coastal radar, sonar, satellite imagery |
| **RGP — Recognized Ground Picture** | Tactical consolidation of land force positions and movements. | Blue-force tracking, UAV feeds, tactical reports |
| **RIP — Recognized Intelligence Picture** | Focused integration of multi-source intelligence data to identify and monitor areas of interest, threats, and indicators. | SIGINT, IMINT, HUMINT, OSINT, all-source fusion |
| **RCISP — Recognized CIS Picture** | Status and topology of communications and information systems. | Network monitoring, link status |
| **RLP — Recognized Logistic Picture** | Status of logistics, supply chains, and sustainment. | Logistics reports, supply tracking |
| **RMedP — Recognized Medical Picture** | Medical situational awareness, casualties, treatment capacity. | Medical reporting systems |

## Recognized Picture vs. Common Operational Picture vs. Common Intelligence Picture

| Concept | Focus | Relationship |
|---|---|---|
| **Recognized Picture (RP)** | Domain-specific, sensor/INT fusion (air, maritime, ground, intelligence) | Input feed to the COP |
| **Common Operational Picture (COP)** | Cross-domain, shared operational view | Integrates multiple RPs + logistics/weather/cyber |
| **Common Intelligence Picture (CIP)** | Adversary-focused intelligence assessment | Feeds the intelligence layer of the COP |
| **Common Relevant Picture (CRP)** | Tailored, decision-maker-specific view | Filtered subset of COP/CIP |

**Key distinction:** RPs are **functional/domain-specific** compilations. The COP is the **integrated, cross-domain** common view. The CIP is the **intelligence-specific** picture. RPs feed into the COP; the CIP is both an input to and a layer of the COP.

## The "recognition" process

"Recognition" in an RP is an intelligence fusion process, not just AI pattern matching. It typically involves:

1. **Collection** — raw data from sensors and sources.
2. **Correlation/Association** — determining if different data points refer to the same object or activity.
3. **Identification** — assigning a degree of certainty to what the object is (class, type, nationality, intent).
4. **Synthesis** — combining identified entities into a temporal and spatial context (the "Picture").

This aligns with the **JDL Data Fusion Model** levels:

| Level | Name | Description |
|---|---|---|
| 0 | Signal Preprocessing | Filtering, digitizing, noise suppression |
| 1 | Object Assessment | Position, velocity, identity estimates (tracks) |
| 2 | Situation Assessment | Tactical/operational context, grouping, intent |
| 3 | Impact Assessment | Threat evaluation, consequences for friendly forces |
| 4 | Process Refinement | Sensor/resource management optimization |
| 5 | Cognitive Refinement | Human-machine interaction support |
| 6 | Mission Refinement | Higher-level tactical/strategic objective integration |

## Doctrinal sources

### NATO

- **AAP-06** — *NATO Glossary of Terms and Definitions*: authoritative source for "Recognized Maritime Picture," "Common Operational Picture," and related terms.
- **AJP-3.3** — *Allied Joint Doctrine for Air and Space Operations*: discusses the RAP in air battle management.
- **AJP-3.3.3** — *Allied Joint Doctrine for Air and Maritime Operations*: formally defines RAP and RMP.
- **AJP-6** — *Allied Joint Doctrine for Command and Control*: broader C2 services, situational awareness, decision support.
- **NISP** — *NATO Interoperability Standards and Profiles*: technical standards for data exchange models and services to produce these pictures across coalition networks.

### US

- **JP 2-0** — *Joint Intelligence*: intelligence support, integration into COP.
- **JP 3-0** — *Joint Operations*: overarching framework for joint operations and C2.
- **JP 3-01** — *Countering Air and Missile Threats*: sensor integration for air defense, RAP.
- **JP 3-32** — *Joint Maritime Operations*: maritime C2, RMP.

### UK

- **JDP 2-00** — *Intelligence, Counter-Intelligence and Security Support to Joint Operations*: intelligence support to joint operations (also cited for TESSOC).

### Academic/technical

- **Llinas, J. & White, F.E. (1987)** — "Revisions to the JDL Data Fusion Model." Foundational framework for JDL levels.
- **Farina, A., et al. (2014)** — "Integrated Sensor Systems and Data Fusion for Homeland Protection." Fusion architectures and levels.

## Implications for InfoTriage

InfoTriage is an **OSINT/all-source intelligence triage system**, not a real-time sensor-fusion platform. The most relevant concepts are:

- **RIP (Recognized Intelligence Picture):** The closest analog to what InfoTriage builds over time — a fused, validated picture of threats and topics of interest from open sources.
- **COP/CIP/CRP:** Output views or lenses on top of the enrichment data, as described in [DIMEFIL / COP / CIP / CRP evaluation](dimefil-cop-cip-evaluation.md).

InfoTriage does not build a real-time RAP/RMP/RGP from sensors, but it can contribute to a **recognized intelligence picture** by:

- Collecting and triaging OSINT items.
- Enriching them with CCIR, CNR, PMESII, and TESSOC tags.
- Clustering and deduplicating semantically similar items.
- Producing structured digests (SAB) that feed into a higher-level RIP/CIP.

## Related notes

- [DIMEFIL / COP / CIP / CRP evaluation](dimefil-cop-cip-evaluation.md)
- [PMESII hybrid definitions](pmesii-hybrid-definitions.md)
- [TESSOC taxonomy correction](tessoc-taxonomy-correction.md)
- **Formal ADR:** [ADR-013 — Recognized Picture Doctrine](../../docs/adr/ADR-013-recognized-picture-doctrine.md)

## References

- NATO AAP-06, *NATO Glossary of Terms and Definitions*
- NATO AJP-3.3, *Allied Joint Doctrine for Air and Space Operations*
- NATO AJP-3.3.3, *Allied Joint Doctrine for Air and Maritime Operations*
- NATO AJP-6, *Allied Joint Doctrine for Command and Control*
- US JP 2-0, *Joint Intelligence*
- US JP 3-0, *Joint Operations*
- US JP 3-01, *Countering Air and Missile Threats*
- US JP 3-32, *Joint Maritime Operations*
- UK JDP 2-00, *Intelligence, Counter-Intelligence and Security Support to Joint Operations*
- Llinas, J. & White, F.E. (1987), "Revisions to the JDL Data Fusion Model"
- Farina, A., et al. (2014), "Integrated Sensor Systems and Data Fusion for Homeland Protection"
