---
sketch: 001
name: sp-cop-canvas
question: "How does one canvas flex across LOOK / HEADLINES / FOCUS without caging the user — while serving both known (CCIR) and unknown (discovery)?"
winner: null
tags: [cop, canvas, sab, network, geo, timeline, discovery, modes]
---

# Sketch 001: SP-COP Canvas

## Design Question
The operator's ask: **multiple modes, no limits** — "possibility to look, get headlines, or focus,"
over their own CCIR/CNR-scored corpus, serving both **known** interests (directed) and **unknown**
(serendipitous discovery). Two axes: known↔unknown, ambient↔focused. How does a single canvas express
this without forcing one fixed view?

## How to View
open .planning/sketches/001-sp-cop-canvas/index.html

The three variants are the three **modes** (top tabs, also the floating mode-switch). They share one
substrate: geo + entity-network + timeline scrubber, over the spike corpus (NATO/Venezuela/Ukraine/Iran,
nrk/bbc/tass). Real interactions: drag the timeline cursor (fades out-of-window geo dots), ▶ play to
animate, click a network node → drops into FOCUS, park leads → tray, hover headlines → focus/park.

## Variants (= modes)
- **A · LOOK** — ambient/lean-back. Split geo ‖ network; discovery foregrounded (new-signal nodes pulse
  magenta, bridge links dashed, "what you didn't ask about" picker). Calm-tech glance state.
- **B · HEADLINES** — digest/SAB. CCIR-tiered, CNR-elevated, cited brief (the `write_bluf()` projection)
  with a ▶ Present toggle. Scannable; hover a line to focus or park it.
- **C · FOCUS** — lean-forward deep-dive. Neighborhood graph (2 hops) + source items + the **action
  launchpad**: Dig in (RAG, Ph9) · Synthesize (Wiki-LLM, Ph10) · Start POC (AI/FFIR-3) · Park lead.

## What to Look For
- Does mode-switching feel like "no limits" (move freely) rather than three separate apps?
- LOOK: is the discovery treatment (pulse/bridge/anomaly) legible without being a doomscroll feed?
- Is the split geo‖network the right primary, or should one dominate?
- FOCUS: does the launchpad (dig-in / synthesize / POC / park) land as "intel → doing"?
- Timeline scrubber: right altitude at the bottom spanning both halves?
- Dark intel-console aesthetic — right direction?

## Prior art referenced (see R5-VERDICT.md)
Shneiderman semantic-zoom mantra · info-foraging/berrypicking · serendipity scents · IBM i2 (geo+net+time) ·
Maltego transforms (dig-in) · InfraNodus gap/bridge discovery · Sensecape (LLM multilevel) · calm tech (ambient).
