---
phase: 00-concept-spike
plan: "05"
subsystem: wiki-llm
tags: [wiki-llm, synthesis, qwen36, omlx, citations, entity-links, cross-language, r4]

requires:
  - 00-01  # items.json corpus
  - 00-04  # R3 entity_links table (on-demand cross-language gather)

provides:
  - "R4-VERDICT.md: PARTIAL — local qwen36 synthesis GO (coherent + grounded); cross-language synthesis drops ru sources"
  - "r4_wiki.py: generate_wiki(topic, items) + --on-demand --topic; extends write_bluf() cite-grounded [N] pattern"
  - "standing_page.md: NATO standing page (5 items, 5 grounded citations)"
  - "on_demand_article.md: Venezuela on-demand article (17 items gathered across en/no/ru, 8 cited)"

affects:
  - 00-07-PLAN.md  # closeout reads R4-VERDICT
  - Phase-10       # Wiki-LLM production
  - 999.1          # translation backlog — directly motivated by the ru-dropped finding

tech-stack:
  - qwen36-ud-4bit via oMLX (http://127.0.0.1:8000/v1, ADR-004 local-only)
  - score/triage_score.py llm() + score/digest.py write_bluf() pattern
  - pgvector entity_links (port 22062) for on-demand cross-language gather
---

# Plan 00-05 Summary — R4 Wiki-LLM Feasibility

**Verdict: PARTIAL** (operator coherence judgment, 2026-06-26). Local qwen36 produces coherent,
four-section, citation-grounded intel-wiki pages for both standing and on-demand modes. Marked
PARTIAL for a real cross-language synthesis limit, never silently elevated.

## What was proven (GO)

- **Local-only synthesis (ADR-004):** all generation through `llm()` → `127.0.0.1:8000/v1`, model
  `qwen36-ud-4bit`, on oMLX. DGX Spark was unavailable; R4 ran entirely on the oMLX fallback,
  confirming RESEARCH Assumption A2.
- **Standing page (NATO):** 5 corpus items, 5 distinct grounded citations, four sections
  (Bakgrunn / Sentrale utviklingstrekk / Aktuell vurdering / Åpne spørsmål), with explicit
  contradiction reporting (E5 burden-sharing vs. Medvedev/Russia narrative).
- **On-demand article (Venezuela):** genuinely distinct from the standing page — different topic,
  sources, content. Gathered **17 items across en/no/ru** via the R3 `entity_links` join (D-03
  reuse), 8 distinct sources cited, grounding PASS.
- **Citation grounding:** every `[N]` maps to a real source id; the script hard-exits non-zero on
  any ungrounded reference, so PASS is verified, not asserted.

## Caveats (carry-forward)

1. **Cross-language synthesis drops Russian sources.** The Venezuela gather pulled 17 items across
   3 languages, but synthesis cited only en (bbc) + no (nrk) — all 7 TASS (ru) items went uncited.
   Gather works; synthesis silently omits languages the model under-weights. → Phase 10 must verify
   non-no/en representation; **directly motivates backlog 999.1 (on-demand translation).**
2. **Minor internal contradiction** in the Venezuela page (embassy "ingen egen" vs. "ambassaden har
   kommet i kontakt"). Reader-level nit, not a grounding failure.

## Deviations

- `max_tokens` raised 800→1100 during execution: the RESEARCH-suggested 800 cap truncated the 4th
  section mid-page. Raised so all four prompted sections complete; the ~600-word prompt limit still
  bounds page length.

## Artifacts

| Path | Durable? |
|------|----------|
| `findings/R4-VERDICT.md` (verdict + both samples pasted inline) | **Durable** |
| `.spike/r4_wiki/r4_wiki.py` | Ephemeral (deleted Plan 07) |
| `.spike/r4_wiki/standing_page.md` | Ephemeral (copied into verdict) |
| `.spike/r4_wiki/on_demand_article.md` | Ephemeral (copied into verdict) |

## Commits

- `232929e` — R4 Task 1: r4_wiki.py + standing + on-demand on qwen36
- on-demand re-run on Venezuela (distinct topic, cross-language) during the coherence checkpoint
