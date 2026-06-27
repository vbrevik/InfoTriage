# ADR-005 — COP / World Monitor: drop as engine, build native SP-COP

**Status.** Accepted (2026-06-27). Source: Phase 0 spike R5 (`findings/R5-VERDICT.md`,
`.planning/phases/00-concept-spike/SPIKE-FINDINGS.md`). Continues the ADR lineage in
`docs/ARCHITECTURE.md` (ADR-001..004).

---

**Context.** ADR-003 framed InfoTriage as an OSINT/all-source intelligence system with a **map/COP
as the navigation frame**, and named **World Monitor** (WM, `koala73/worldmonitor`, AGPL-3.0) as the
strongest map-COP + multi-source aggregation + local-LLM base — pending a hands-on test. R5 ran that
test (D-05): WM was cloned, installed (1617 pkgs), built and launched as a working desktop app (after
correcting the build command), the globe GUI judged hands-on, and the LLM wiring, provider fallback
chain, data architecture, and render stack read directly from source. The operator likes the globe
view + COP concept but needs **InfoTriage's own data + doctrinal CCIR/CNR presentation**, which WM
cannot do without fighting its design.

---

**Decision.** **DROP** World Monitor as the product/engine. **ADOPT** its globe-COP *concept* only.
**BUILD** an InfoTriage-native interactive-SAB canvas — **SP-COP** — on the open globe stack
(`globe.gl` / `three-globe`, MIT + `maplibre-gl`, BSD-3), local-LLM (oMLX, ADR-004), fed by the
canonical InfoTriage store + CCIR/CNR tiers.

**Aegis** (`github.com/FNBIP/aegis-osint-map`, a WM-lineage OSINT platform) is evaluated and **also
dropped as an engine** — it is *more* cloud-locked than WM (intelligence core = Valyu API cloud +
optional OpenAI, **no local-LLM path** → violates ADR-004; Mapbox GL commercial/token-gated;
Next.js 16/Vercel). Both WM and Aegis are kept as **concept references only — no code adopted**.

**SP-COP design direction (carried forward):** the SAB evolved from a static rendered document into
an **interactive canvas** — topics/news/info explorable on a map + panels, organized by
**CCIR-as-interests** (standing topics) and **CNR-as-urgency** at personal scale. Three modes the
operator moves between freely along two axes (known↔unknown, ambient↔focused):
- **LOOK** — ambient/lean-back; glance the operating picture; discovery comes to you.
- **HEADLINES** — digest level: CCIR-tiered cited headlines, CNR-elevated; ties to `write_bluf()`
  (Phase 6); also the presentation mode (explore ⟷ present). **Validated via sketch 001.**
- **FOCUS** — lean-forward deep dive: entity neighborhood graph + topic timeline + source items +
  action launchpad (follow-up / dig-in via RAG Phase 9 / Wiki-LLM Phase 10 / spin-up-POC).

The canvas is a **split view**: globe (geo half) + entity-link **Graph Canvas** (network half, fed by
R3 `entities`/`entity_links` → Phase 8) + a shared **timeline scrubber**, all cross-filtered, with
floating pickers borrowed (concept only) from WM.

---

**Why drop WM as the engine (decision inputs from R5):**
- **Cloud-coupled** — backend `remoteBase` defaults to `https://api.worldmonitor.app`; full product
  uses hosted Convex (DB), Clerk (auth), Vercel.
- **Own feeds / own region model** — ships ~hundreds of RSS feeds + `SOURCE_REGION_MAP` + a per-region
  instability index; presenting InfoTriage's store + CCIR/CNR means injecting against its design.
- **No CCIR doctrine** — has AOIs + source-tier priority + instability scoring, but not the operator's
  interest-profile-scored CCIR/CNR model.
- **No entity graph** — only entity *location* markers; no R3-style entity network / KG.
- **High setup friction / build trap** — `npm run tauri build` ships a broken app ("asset not found:
  index.html"); the desktop build needs `npm run desktop:build:full` (`VITE_DESKTOP_RUNTIME=1`).
- **oMLX-compatible (positive but not decisive)** — WM's `generic` OpenAI provider points at oMLX with
  no Ollama; cloud providers self-skip when keys are unset. Local-LLM is satisfiable, but does not
  outweigh the reasons above.

WM/Aegis are **commercial-grade north-stars** for "what good looks like" (globe COP, deep-research
exports, OSINT geo-asset layers mapping to CCIR PIR-4/PIR-2, command palette + density timeline); the
high-leverage path is to reproduce the surface on open libraries over InfoTriage's own data.

---

**Consequences.**
- A new build stream (SP-COP) is created on `globe.gl`/`three-globe` + `maplibre-gl`; no dependency on
  Convex/Clerk/Vercel/Valyu/Mapbox. License-clean (MIT/BSD).
- SP-COP is a **second reading-surface projection** of the same data; the Brief app / SAB renderer
  (`write_bluf()`, Phase 6) remains the **canonical** intelligence product.
- The network half depends on R3 entity resolution (`entities`/`entity_links`, pgvector → Phase 8) —
  see ADR-006. SP-COP planning inherits the R5 feature wishlist (timeline scrubber, multiple non-geo
  views, split geo+network, presentation mode, actionable topics/launchpad, park-leads).
- Build cost is higher than adopting WM outright, accepted in exchange for local-LLM purity (ADR-004),
  doctrinal CCIR/CNR, the entity graph, and freedom from a cloud-coupled commercial monorepo.
- The `.spike/r5_worldmonitor/` clone and the built `World Monitor.app` are throwaway reference
  artifacts, removed at the 00-07 teardown (D-06).
