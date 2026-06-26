---
phase: 00-concept-spike
plan: "06"
subsystem: cop-worldmonitor
tags: [cop, world-monitor, adr-005, sp-cop, ccir, llm-fallback, cloud-leak, r5]

requires:
  - 00-01  # items.json corpus

provides:
  - "R5-VERDICT.md: DROP World Monitor as product/engine; ADOPT globe-COP concept; BUILD native COP (SP-COP) on open globe stack fed by InfoTriage data + CCIRs"
  - "r5_prep.py: scores 20 corpus items via existing pipeline; exports WM-compatible JSON"
  - "scored_20.json: 20 pre-scored items (ccir/cnr/score/why)"
  - "baseline_brief.md: InfoTriage write_bluf() CCIR brief over the same 20 items (comparison yardstick)"

affects:
  - 00-07-PLAN.md  # closeout writes ADR-005 from this verdict
  - SP-COP         # COP globe build-vs-adopt decision inherits this

tech-stack:
  - qwen36-ud-4bit via oMLX (scoring + baseline brief)
  - score/triage_score.py + score/digest.py write_bluf()
  - World Monitor (koala73/worldmonitor) — Tauri/Rust/Convex/Vercel monorepo (evaluated, dropped)
---

# Plan 00-06 Summary — R5 COP / World Monitor

**Verdict: DROP World Monitor as product/engine; ADOPT the globe-COP concept; BUILD a native COP
(SP-COP) on the open globe stack, fed by InfoTriage data + CCIRs** (operator decision, 2026-06-26).

## Method note

Grounded in a real test (D-05). WM was cloned, installed (1617 pkgs), **built and launched as a
working desktop app**, and the operator judged the globe UI hands-on. LLM wiring, provider fallback,
data architecture, and the render stack were read from source (more reliable than GUI inspection for
the safety/architecture questions). Required a build-command correction (see below).

## Key findings (see R5-VERDICT.md for the full evidence table)

- **Operator likes the globe view + concept** — but requires **own data + CCIR presentation**, which
  WM cannot do without fighting its design.
- **WM's globe is 100% open-source**: `globe.gl`/`three`/`three-globe` (MIT), `deck.gl` (Apache-2.0),
  `maplibre-gl`/protomaps (BSD/open). The view is reproducible natively — no WM dependency.
- **WM is an online aggregator with a local shell**: local Tauri window + Node sidecar, but backend
  defaults to `api.worldmonitor.app` (cloud-fallback off by default; docker self-host mode blocks it),
  and its DATA is open-internet (RSS feeds, basemap tiles, market/flight APIs). Full product uses
  hosted Convex/Clerk/Vercel.
- **No CCIR taxonomy** (0 repo matches); ships its own feed list. Presenting InfoTriage CCIRs = constant
  injection against the grain.
- **oMLX compatible** via WM's `generic` OpenAI provider — no Ollama (`llm.ts:87`); cloud-leak
  controllable (providers self-skip without keys, `llm.ts:61,74`).
- **Build trap (friction):** `npm run tauri build` ships a BROKEN app ("asset not found: index.html");
  must use `npm run desktop:build:full` (`VITE_DESKTOP_RUNTIME=1`). Build itself is fast (~2 min).
- **CCIR-like concept (operator correction):** WM HAS a geography-first analog — `SOURCE_REGION_MAP`
  (AOIs → curated feeds), source-tier priority, per-region instability scoring. Lacks the doctrinal
  layer (PIR/FFIR/SIR, LLM scoring vs ccir.md, CNR elevation). Validates the AOI→feed→globe pattern.
- **Product vision (operator):** SP-COP = the **SAB reimagined as an interactive canvas** — topics/news/
  info explorable on globe + panels over InfoTriage's CCIR/CNR data, not a static rendered brief. A
  second reading-surface projection alongside the canonical `write_bluf()` SAB (Phase 6).
- **Decision:** drop WM (cloud-coupled, own feeds/regions, instability-index not doctrinal CCIR); build
  own interactive-SAB canvas on the open globe stack (globe.gl/three-globe MIT + maplibre BSD) with
  InfoTriage data + CCIR/CNR doctrine → SP-COP.

## What was built (Task 1)

- `r5_prep.py` — `prep_20()`, source-stratified (bbc/nrk/tass) 20-item selection, scores via existing
  pipeline, exports WM-compatible `scored_20.json` + InfoTriage `baseline_brief.md`.
- 20 items: CCIR none 10 / SIR-1 3 / FFIR-2 3 / PIR-5 2 / PIR-1 2; CNR none 10 / II 7 / I 3.

## Artifacts

| Path | Durable? |
|------|----------|
| `findings/R5-VERDICT.md` | **Durable** |
| `.spike/r5_worldmonitor/r5_prep.py` / `scored_20.json` / `baseline_brief.md` | Ephemeral (deleted Plan 07) |
| `.spike/r5_worldmonitor/worldmonitor/` (clone + node_modules) | Ephemeral — remove at 00-07 teardown |

## Carry-forward

- **ADR-005:** DROP WM as engine; COP-globe build-vs-adopt → SP-COP (Deferred).
- InfoTriage `write_bluf()` CCIR brief stays canonical; no WM dependency.
- If SP-COP revisits WM for display only: wire `generic`→oMLX, keep cloud keys unset (ADR-004).

## Commit

- `da77120` — Task 1 (r5_prep + 20 scored + baseline_brief)
