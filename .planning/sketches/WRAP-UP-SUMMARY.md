# Sketch Wrap-Up Summary

**Date:** 2026-06-26
**Sketches processed:** 1
**Design areas:** SP-COP Canvas — Headlines/SAB
**Skill output:** `./.claude/skills/sketch-findings-infotriage/`

## Included Sketches
| # | Name | Winner | Design Area |
|---|------|--------|-------------|
| 001 | sp-cop-canvas | B · HEADLINES | SP-COP Canvas — Headlines/SAB |

## Excluded Sketches
| # | Name | Reason |
|---|------|--------|
| — | — | none |

## Design Direction
SP-COP — the SAB reimagined as an interactive operating-picture canvas (replaces World Monitor, dropped
in spike R5). Dark intel-console aesthetic, fully local, over the operator's own CCIR/CNR-scored corpus.
Multiple modes, no limits: **LOOK / HEADLINES / FOCUS** across two axes (known↔unknown, ambient↔focused).
HEADLINES is the validated centerpiece; LOOK and FOCUS are designed but parked.

## Key Decisions
- **HEADLINES = BLUF-first per CCIR topic** — synthesized analyst summary + `[N]` citations, then evidence.
- **Default = "since last read" delta view** — only changed topics, only new items; embrace sparseness (calm).
- **Time-aware BLUF** — segmented control Since-last-read / Latest / Back-in-time; in Back-in-time the BLUF
  re-states to the selected moment (time-versioned snapshots).
- **Topic-as-launchpad** — re-synthesize (Wiki-LLM), park lead (tray), POC (AI/FFIR-3 topics).
- **Palette/typography** — dark intel-console; cyan=known, amber=unknown/new, magenta=serendipity, red/amber CNR.
- **Anti-patterns** — don't default to the full brief; don't build an ambient doomscroll feed; don't adopt
  World Monitor's cloud-coupled stack (reuse only open globe libs for the eventual geo half).

## Carried-forward (parked)
- LOOK (ambient geo+network discovery) and FOCUS (deep-dive + neighborhood graph + action launchpad) —
  designed in sketch 001 but not iterated; revisit via `/gsd-sketch` frontier mode when ready.
- Full SP-COP vision + prior-art research: `.planning/phases/00-concept-spike/findings/R5-VERDICT.md`.
