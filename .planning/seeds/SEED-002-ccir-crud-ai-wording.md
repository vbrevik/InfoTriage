---
id: SEED-002
status: dormant
planted: 2026-07-08
planted_during: v1.0 / Phase 6 (brief-app) UAT
trigger_when: when relevant
scope: unknown
---

# SEED-002: CCIR/CNR list CRUD + AI-assisted wording improvement

## Why This Matters

Managing the CCIR taxonomy (PIR/SIR/FFIR + CNR thresholds) today means hand-editing
`ccir.md` prose. Two ideas in one:

1. **CRUD surface** — add/edit/retire/list CCIR entries as first-class operations
   (CLI, API, or SP-COP UI) instead of raw markdown edits. Especially SIRs, which
   are time-boxed by design ("oppheves ved endt hendelse") — retirement should be
   an operation, not a manual delete. Live example 2026-07-08: adding SIR-3
   (NATO-toppmøtet i Ankara) was a raw-markdown edit with no validation of the
   `- **CODE**` bullet format the sync-guard regex expects.

2. **AI-assisted wording** — the CCIR text IS the scorer prompt (hot-read into
   `score_item`, D-5). Wording quality directly drives triage quality. Use the
   local LLM to: propose sharper requirement wording, suggest kildegruppe/PMESII/
   TESSOC tags, flag overlap with existing PIRs (e.g. SIR-3 vs PIR-3 needed a
   manual disambiguation note), and generate worked scoring examples like the
   SIR-2 carve-out has.

## When to Surface

**Trigger:** when relevant

Natural fits: SP-COP canvas phases (operator-facing UI), or after SEED-001
(dynamic CCIR parsing) lands — CRUD wants a structured representation first.
Builds on [[SEED-001]].

## Scope Estimate

**Unknown** — CRUD is Medium (needs structured storage or a validated markdown
round-trip); AI wording assist is Small once CRUD exists (one prompt + review loop
against the local oMLX/vLLM model).

## Breadcrumbs

- `ccir.md` — current freeform source of truth; SIR-2 section shows the worked-example pattern AI could generate
- `.planning/seeds/SEED-001-dynamic-ccir-list.md` — prerequisite: parse CCIR structure from one place
- `apps/triage/triage_score.py:score_item` — wording lands verbatim in the scorer prompt; disambiguation guides live here too
- `apps/triage/digest.py` / `apps/triage/sab_html.py` — CCIR_ORDER consumers a CRUD layer must update (or replace via SEED-001)
- R5-VERDICT / `sketch-findings-infotriage` skill — SP-COP vision where a CCIR management panel would live

## Notes

Captured during Phase 6 UAT right after live-adding SIR-3 by hand exposed the
friction. Enrich via `/gsd-capture --seed --enrich SEED-002`.
