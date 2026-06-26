# SP-COP Canvas — Headlines / SAB mode

Validated design decisions from sketch 001 (winner: **Variant B · HEADLINES**). LOOK and FOCUS
modes were explored but parked for later; only HEADLINES was iterated to a confident direction.

## Design Decisions

### The product is multi-mode, no limits — LOOK / HEADLINES / FOCUS
One canvas, a spectrum of engagement the user moves between freely (Shneiderman's "overview → zoom →
details" as explicit modes). A persistent mode-switch (pill, top-center) is present in every view so it
reads as one fluid surface, not three apps. **HEADLINES is the validated centerpiece**; LOOK (ambient
geo+network discovery) and FOCUS (deep-dive + action launchpad) are designed but deferred.

### HEADLINES = BLUF-first, per CCIR topic
- Each CCIR topic leads with a **synthesized BLUF** (bottom-line-up-front analyst paragraph) with inline
  `[N]` citations, then the numbered cited evidence beneath. Mirrors the real `write_bluf()` output.
- BLUF block: left accent bar (cyan), small uppercase mono tag, body at 13px/1.55 line-height.
- The AI/own-tech topic (FFIR-3) uses a green accent + a **POC** launch action — "intel → doing."

### Default view = "Since last read" (delta), not the whole brief
- On return, show only **topics that changed**, and within them only the **new items** (older collapse to
  a "+N earlier — already read" line). Embrace sparseness — when little changed, show little (calm-tech).
- `✓ mark all read` clears deltas → "All caught up" empty state.

### Time-aware BLUF (three view modes via a segmented control)
- **Since last read** (default) · **Latest / current** · **⟲ Back in time** (day slider).
- In Back-in-time, the **BLUF re-states to the selected moment** — versioned snapshots `{d:day, t:text}`,
  pick the latest snapshot ≤ selected day; before a topic's first assessment show "ingen vurdering ennå."
- CNR urgency drives color: CAT I red, CAT II amber, routine slate. New items get an amber "new-dot."

### Topic-as-launchpad + park-leads
- Per-topic hover actions: **↻ re-synthesize** (Wiki-LLM), **⊟ park** (to a leads tray), **⚙ POC** (AI topics).
- A floating **Parked leads** tray collects items/topics shelved for later (information-foraging "patches").

## CSS Patterns

```css
/* Dark intel-console theme (sources/themes/default.css) — key tokens */
--bg:#0a0e14; --surface:#121826; --border:#233044; --text:#c8d3e3;
--accent:#46c6ff;      /* known / CCIR (cyan)     */
--accent-2:#ffb347;    /* unknown / new (amber)   */
--discovery:#ff8adf;   /* serendipity (magenta)   */
--cnr1:#ff4d5e; --cnr2:#ffb347;  /* CNR urgency */
--mono: ui-monospace,"SF Mono",Menlo,monospace;

/* BLUF block — analyst summary up front */
.bluf { background:linear-gradient(var(--surface),var(--bg-2));
  border:1px solid var(--border); border-left:3px solid var(--accent);
  border-radius:6px; padding:11px 13px; line-height:1.55; }
.bluf.poc { border-left-color:var(--ok); }           /* AI/POC topic */
.bluf sup { color:var(--accent); font:9px var(--mono); cursor:pointer; }

/* segmented view-mode control */
.seg { display:flex; gap:3px; background:var(--surface); border:1px solid var(--border);
  border-radius:7px; padding:3px; }
.seg button.on { background:var(--surface-2); color:var(--accent);
  box-shadow:inset 0 0 0 1px var(--accent); }
.seg .badge { background:var(--accent-2); color:#1a1205; border-radius:99px; }  /* N new */
```

## HTML / JS Structures

- **Per-topic block:** `<h3>tier + count + NEW badge + CNR flag + latest-stamp + hover actions</h3>` →
  `.bluf` → `.cited` list of `.hl` rows (`[N]` num · CNR chip · text · source·day · focus/park actions).
- **Time-versioned BLUF:** `const BLUF = {tier:[{d:day,t:'…<sup>[1]</sup>'}]}`; `blufAsOf(tier,day,latest)`
  picks the latest snapshot ≤ day (or the last when `latest`).
- **Delta logic:** items carry `n:1` when new-since-last-read; fresh mode filters tiers to `freshN>0` and
  items to `i.n`; `markRead()` zeroes `n`.
- **Variant switching:** fixed top tab-bar + in-view mode pills both call `showVariant(id)`.

## What to Avoid
- **Don't make the modes feel like separate apps** — the always-present mode-switch is what makes it one canvas.
- **Don't default to the full brief** — default to deltas; the full SAB is one click away ("Latest").
- **Don't build an ambient *feed*** — calm-tech research warns rotating news headlines become an anxiety
  trigger; LOOK/ambient must be glanceable + quiet, not a doomscroll.
- **Don't adopt World Monitor's stack** (R5: cloud-coupled, own feeds, no CCIR). Reuse only the open globe
  libs (globe.gl/three-globe MIT, maplibre BSD) for the eventual geo half.

## Origin
Synthesized from sketch: 001-sp-cop-canvas (winner: Variant B · HEADLINES).
Full vision + prior-art research: `.planning/phases/00-concept-spike/findings/R5-VERDICT.md`.
Source files: `sources/001-sp-cop-canvas/index.html`, `sources/themes/default.css`.
