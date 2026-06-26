# R5 COP / World Monitor Verdict

**Verdict: DROP World Monitor as the product/engine; ADOPT its globe-COP concept; BUILD a native
COP under SP-COP on the open globe stack, fed by InfoTriage data + CCIRs.**

ADR-005 decision: **DROP** World Monitor. **BUILD** an InfoTriage-native COP (SP-COP) that reuses the
same open-source globe rendering WM is built on, presenting InfoTriage's own data and CCIR/CNR tiers.
The operator judged the WM globe UI hands-on (likes the view + concept) but requires **own data + CCIR
presentation**, which WM cannot do without fighting its design.

## Method

Grounded in a real test (D-05): the repo was cloned, installed (1617 pkgs), and **built + launched as
a working desktop app** (after a build-command correction, below). The operator ran the GUI and judged
the globe. LLM wiring, the provider fallback chain, the data architecture, and the render stack were
read directly from source — more reliable than GUI inspection for the safety/architecture questions.

## Decision inputs (ADR-005)

| Input | Finding | Evidence |
|-------|---------|----------|
| Globe UI quality | **Good — operator likes the view + concept.** Worth having as a COP. | hands-on GUI run |
| Globe stack | **100% open-source, not proprietary to WM:** `globe.gl` + `three` + `three-globe` (MIT), `deck.gl` (Apache-2.0), `maplibre-gl` + `@protomaps/basemaps` (BSD-3/open). InfoTriage can build the same view directly. | `package.json` deps + license check |
| Local vs online | **Online aggregator with a local shell.** Runs a local Tauri window + Node sidecar, but defaults its backend `remoteBase` to `https://api.worldmonitor.app` (cloud-fallback off by default in desktop; a `docker` self-host mode hard-blocks the proxy). Its **data** is open-internet: ~hundreds of RSS feeds, online basemap tiles, market/flight APIs. Full product also uses hosted Convex (DB), Clerk (auth), Vercel. | `src-tauri/sidecar/local-api-server.mjs:554,737,760`; `src/config/feeds.ts`; `basemap-styles.ts` |
| CCIR-like concept | **Close analog.** At personal scale, InfoTriage's CCIR/CNR is a **"what I'm interested in" (standing interests/topics) + "how much it matters to me" (urgency)** model — not rigid military doctrine. WM expresses essentially the same shape: AOIs/topics via `SOURCE_REGION_MAP` (worldwide/us/europe/middleeast/africa/latam/asia/topical/intel → curated feed sets) + source-tier priority + per-region instability scoring + map overlays. The InfoTriage difference is just *whose* priority model: items are LLM-scored against the **operator's own interest profile** (`ccir.md`) rather than WM's generic instability index. | `src/config/feeds.ts:1024` (SOURCE_REGION_MAP), `server/_shared/source-tiers.ts`, `src/app/country-intel.ts` |
| Own data / CCIRs | **WM ships its own feed list and its own region model.** Presenting InfoTriage's data + doctrinal CCIR/CNR means injecting against WM's design (its feeds, its regions, its instability index — not InfoTriage's store or doctrine). | `src/config/feeds.ts` |
| oMLX compatibility | **Yes** — `generic` OpenAI provider (`LLM_API_URL`/`LLM_API_KEY`/`LLM_MODEL`). No Ollama needed. | `server/_shared/llm.ts:87` |
| Cloud-leak risk | **Controllable** — groq/openrouter self-skip when their keys are unset (`llm.ts:61,74`); `providerOrder:['generic']` hard-excludes them. Wired oMLX via in-app settings; cloud keys left blank. | `server/_shared/llm.ts:59-103` |
| Native brief | Market brief + forecasting deduction — **not** a CCIR/CNR analyst brief. | `daily-market-brief.ts`, `deduction-prompt.ts` |
| Setup friction | **Mixed.** Build is FAST (~2 min, cargo cached; not the 10-20 min RESEARCH predicted) but the repo is a large commercial monorepo (1617 pkgs, Tauri/Rust/Convex/Vercel, 5 variants, 38.9K `.env.example`). **Non-obvious build trap:** the obvious `npm run tauri build` ships a BROKEN app ("asset not found: index.html") because the web build renames the entry; the desktop build requires `npm run desktop:build:full` (`VITE_DESKTOP_RUNTIME=1`, which skips the `index.html`→`dashboard.html` rename, `vite.config.ts:920-921`). | clone + build |

## Brief comparison

InfoTriage `write_bluf()` baseline (`.spike/r5_worldmonitor/baseline_brief.md`, 20 pre-scored items)
produces a CCIR-tiered, cited, CNR-elevated analyst brief. World Monitor has no equivalent native
output (instability-index + market forecasting). WM does not compete as an intelligence engine; its
value is the COP **display** concept — which is reproducible on open libraries.

## Rationale

The operator's target is **the SAB reimagined as an interactive canvas** — not a static rendered brief
but an explorable operating picture of topics, news, and info (globe + panels) over InfoTriage's own
CCIR/CNR-scored data. World Monitor is the **inspiration for the interactive surface** (AOI → curated
feeds → globe/panels), and proves the pattern works on open libraries — but it cannot be the product:
it inherits a large cloud-coupled codebase (api.worldmonitor.app backend, Convex, Clerk, Vercel) and
imposes its own feeds, its own region model, and an instability index instead of doctrinal CCIR/CNR.
Since the view is open MIT/BSD libraries and the information architecture is simple, the high-leverage
path is to **build a native interactive-SAB canvas** on that stack, fed from the InfoTriage store.
Therefore: drop WM, build own.

## Implications / carry-forward

- **ADR-005:** DROP World Monitor; BUILD an InfoTriage-native **interactive SAB canvas / COP** (SP-COP)
  on `globe.gl`/`three-globe` (MIT) + `maplibre-gl` (BSD), presenting InfoTriage data + CCIR/CNR tiers
  from the canonical store.
- **Product framing (operator, 2026-06-26):** SP-COP is the **SAB evolved from a static presentation
  into an interactive canvas** — topics, news, and info explorable on a map + panels, not a generated
  document. Organized by the operator's **CCIR-as-interests** (standing topics I care about) and
  **CNR-as-urgency** (how much it matters), at personal scale — not military doctrine. Sits alongside
  (and is fed by) the canonical SAB.
- **Reuse from WM (concept only, no code):** the AOI → curated-feed → globe/panel information architecture
  (`SOURCE_REGION_MAP`, source-tier priority, per-region overlays). InfoTriage layers its real CCIR/CNR
  doctrine + own data on top of that pattern.
- **SP-COP scope seed:** the `scored_20.json` event shape (id/title/source/lang/lat-lon/ccir/cnr/score/why)
  is a usable feed contract for the canvas. LLM (if any) stays local (oMLX) per ADR-004; no Convex/Clerk/
  cloud-backend dependency.
- **SP-COP feature wishlist (operator, hands-on with WM, 2026-06-26):**
  - ✅ **Floating pickers** — WM's floating picker UI is good; keep it.
  - ➕ **Timeline / time-scrubber** — temporal navigation WM lacks; scrub through time across the corpus.
  - ➕ **Multiple views beyond geo** — the globe/map is one lens, not the only one. Want alternative
    projections of the same CCIR-scored data (e.g. timeline, topic/CCIR-tier, entity/network, list/feed).
  - ➕ **Split canvas: geo half + network half** — primary layout is the world/globe view in one half
    and an **entity network (nodes + relations)** in the other, as **linked views** over the same
    corpus. The network is fed by **R3 entity resolution** (`entities` + `entity_links`, pgvector →
    Phase 8); selecting an entity/region in one half filters the other. (Pairs with graphify/KG theme.)
  - (running list — feeds SP-COP planning; reuse WM only as concept reference, no WM code.)
- **Relationship to Phase 6:** the Brief app / SAB renderer (`write_bluf()`) remains the canonical
  intelligence product; the interactive canvas is a second reading-surface projection of the same data.
- `.spike/r5_worldmonitor/worldmonitor/` (clone + node_modules + Rust target, large) is throwaway —
  removed at 00-07 teardown. The built `World Monitor.app` is a reference artifact only; not adopted.
