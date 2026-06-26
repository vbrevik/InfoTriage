---
name: sketch-findings-infotriage
description: Validated design decisions, CSS patterns, and visual direction from sketch experiments. Auto-loaded during UI implementation on InfoTriage (SP-COP interactive-SAB canvas).
---

<context>
## Project: InfoTriage

**SP-COP** — the SAB reimagined as an interactive operating-picture canvas (replacing World Monitor,
which spike R5 dropped). Dark intel-console aesthetic, fully local, over the operator's own CCIR/CNR-
scored corpus. Organizing principle: **multiple modes, no limits — LOOK / HEADLINES / FOCUS** across two
axes — known↔unknown (directed CCIR vs serendipitous discovery) and ambient↔focused (glance vs deep-dive).
Topics are launchpads (dig-in → RAG/Wiki-LLM, spin-up POC); leads can be parked for later.

Reference points: World Monitor (globe + floating pickers, concept only) · Palantir Gotham · IBM i2 ·
Maltego · InfraNodus (gap/bridge discovery) · Sensecape · Shneiderman semantic-zoom · calm technology.

Sketch sessions wrapped: 2026-06-26
</context>

<design_direction>
## Overall Direction

Dark intel-console: near-black base (`#0a0e14`), mono labels, cyan=known/CCIR, amber=unknown/new,
magenta=serendipity, red/amber CNR urgency. The validated centerpiece is **HEADLINES** — a BLUF-first,
per-CCIR-topic brief that defaults to a **"since last read" delta view** (sparse by design), with a
segmented control for **Since-last-read / Latest / Back-in-time**. In Back-in-time, each topic's BLUF
**re-states to the selected moment** (time-versioned snapshots). Topics are launchpads (re-synthesize /
park / POC). LOOK (ambient geo+network discovery) and FOCUS (deep-dive + action launchpad) are designed
but parked. A persistent mode-switch keeps it one fluid canvas, not three apps.
</design_direction>

<findings_index>
## Design Areas

| Area | Reference | Key Decision |
|------|-----------|--------------|
| SP-COP Canvas — Headlines/SAB | references/sp-cop-canvas.md | BLUF-first per topic; default = delta view; time-aware BLUF; topic-as-launchpad |

## Theme

The winning theme file is at `sources/themes/default.css` (dark intel-console).

## Source Files

Original sketch HTML preserved in `sources/001-sp-cop-canvas/index.html` (all 3 variants; winner = B).
</findings_index>

<metadata>
## Processed Sketches

- 001-sp-cop-canvas
</metadata>
