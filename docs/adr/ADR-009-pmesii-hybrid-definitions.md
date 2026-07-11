# ADR-009 — PMESII Hybrid Definitions

**Status.** Accepted (2026-07-11). Source:
`.planning/research/pmesii-hybrid-definitions.md`. Continues the ADR lineage in
`docs/ARCHITECTURE.md` (ADR-001..004).

---

**Context.** InfoTriage enriches each ingested item with two analytical axes:
PMESII (operational-environment domain) and TESSOC (threat-actor category).
The PMESII section in `ccir.md` originally listed only concrete, OSINT-tailored
examples (e.g., "Diplomacy, treaties, government policy, elections, sanctions as
political tool"). After a taxonomy review, the project wanted to align the
definitions with NATO doctrine while preserving the concrete anchors that a
local, quantized LLM needs for reliable zero-shot classification.

---

**Decision.** Adopt **hybrid PMESII domain definitions** that prepend a brief
NATO-style framing to the existing concrete examples. The definitions live in
both `ccir.md` (canonical taxonomy) and the hardcoded LLM prompt in
`apps/triage/triage_score.py`.

| Domain | Definition |
|---|---|
| **Political** | Power structures and diplomacy; treaties, government policy, elections, sanctions as policy instrument. |
| **Military** | Defense capabilities and warfare; posture, troop movements, weapons systems, military operations. |
| **Economic** | Resource production and markets; sanctions impact, trade wars, defence budgets, financial markets, energy markets. |
| **Social** | Demographic and cultural composition; protests, civil unrest, public opinion, cultural/sporting events with political dimension. |
| **Information** | Information flow and systems; cyber operations, OSINT investigations, propaganda, hybrid influence, media manipulation. |
| **Infrastructure** | Essential facilities; undersea cables, pipelines, logistics networks, energy grid, transport, maritime routes. |

---

**Consequences.**

- **Doctrinal accuracy.** The definitions explicitly reference NATO's
  operational-environment framing and cite AJP-01 and AJP-5.
- **LLM reliability preserved.** The local model (`qwen36-ud-4bit`) still sees
  concrete semantic anchors ("sanctions", "cyber operations", "undersea cables")
  that drive consistent classification.
- **Consistency.** `apps/triage/triage_score.py` mirrors `ccir.md`, so the LLM
  and human readers use the same definitions.
- **Alternatives rejected.** Pure NATO-style abstract definitions were rejected
  as too ambiguous for the local LLM; PMESII-PT and ASCOPE were rejected as
  duplicative or too tactical for strategic OSINT triage.

**Validation.** `ccir.md` markdown renders correctly; full pytest suite passes
(275 passed, 2 skipped); `triage_score.py --sample` output is unchanged; the
broader regression test on 20 items (`scripts/regression_pmesii_tessoc.py`)
showed no PMESII tag changes attributable to the wording update.

**Related notes.** See `.planning/research/pmesii-hybrid-definitions.md` for the
original research note, and `.planning/research/tessoc-taxonomy-correction.md`
for the parallel TESSOC taxonomy correction.
