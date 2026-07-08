---
id: SEED-001
status: dormant
planted: 2026-07-08
planted_during: v1.0 / Phase 6 (brief-app) UAT
trigger_when: when relevant
scope: unknown
---

# SEED-001: Make the CCIR / CNR (PIR/SIR/FFIR) list dynamic

## Why This Matters

Today the CCIR taxonomy lives in FOUR places that must be kept in sync by hand:

1. `ccir.md` — the operator-edited source of truth (hot-read by the scorer, D-5)
2. `apps/triage/digest.py` `CCIR_ORDER` — hardcoded (id, title) list for digest sections
3. `apps/triage/sab_html.py` `CCIR_ORDER` — a second, duplicate hardcoded copy
4. `triage_score.py:score_item` prompt — tier quick-reference + SIR-2 carve-out examples

Proven painful live on 2026-07-08: adding **SIR-3 (NATO-toppmøtet i Ankara)** to
ccir.md required editing both CCIR_ORDER copies AND rebuilding the brief image
before the new section rendered in the SAB — the scored item existed in the DB
with `ccir=SIR-3` but was invisible in brief.md/cluster.md/sab.html grouping.
The digest.py import-time sync guard (DRIFT-1) catches the drift only at the
next image build, not at edit time. A dynamic design would parse section
ids + display titles from ccir.md at render time (same hot-read the scorer
already does), leaving only the scorer-prompt worked examples as manual.

## When to Surface

**Trigger:** when relevant

Natural fits: any phase touching brief/digest rendering, the SP-COP canvas
(Phase-8+ UI reads the same taxonomy), or the next time an operator adds/retires
a SIR. Surfaces during `/gsd-new-milestone` scans.

## Scope Estimate

**Unknown** — likely Small/Medium: a `parse_ccir_sections(ccir_text)` helper in
one place (contracts or a shared lib), consumed by digest.py + sab_html.py +
renderer.py; delete both hardcoded lists and repurpose the DRIFT-1 guard as a
unit test.

## Breadcrumbs

- `ccir.md` — source of truth; `- **CODE**` bullet pattern already regex-parsed by the sync guard
- `apps/triage/digest.py:38` — `CCIR_ORDER` copy 1 + DRIFT-1 sync guard (lines 47–61)
- `apps/triage/sab_html.py:28` — `CCIR_ORDER` copy 2 (found stale during 06-UAT SIR-3 live test)
- `apps/brief/renderer.py` — takes `ccir_order` param, defaults from digest.py
- `apps/triage/triage_score.py:19` — `CCIR_PATH` hot-read (D-5); container needs the `./ccir.md:/ccir.md:ro` mount added 2026-07-08
- `.planning/codebase/CONCERNS.md` — DRIFT-1 documents this exact risk

## Notes

Captured during Phase 6 UAT session that live-verified SIR-3 end-to-end
(verdict `SIR-3|II|8|read`) after patching both lists + rebuilding brief.
