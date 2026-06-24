# PLAN — Phase 1.5 · PMESII enrichment

> Phase source: PMESII/JIPOE discussion (2026-06-24).
> Goal: Add PMESII operational domain tagging to every scored item, and visualize domain distribution in the SAB.
> Status: **planned**.

## Rationale

PMESII (Political, Military, Economic, Social, Information, Infrastructure) answers a different question than CCIR. CCIR says *what requirement does this serve?*; PMESII says *through what operational lens does this affect the environment?* Adding PMESII as a lightweight enrichment layer:

- Enables cross-cutting synthesis in the SAB (e.g., "60 % of today's threats target Infrastructure domain")
- Primes JIPOE Step 2 ("Describe Environmental Effects") with structured domain data
- Costs ~5–10 extra tokens per item (one enum field in the existing JSON)

PMESII does **not** replace CCIR. It enriches it.

## Design decisions

1. **LLM-assigned, not static mapping.** CCIR→PMESII is not 1:1. PIR-1 (Russland/Ukraina) could be Military (frontlines) or Economic (sanctions). The LLM decides per item.
2. **Single primary domain.** The scorer picks the ONE best-fitting domain. Multiple domains per item is deferred (premature complexity).
3. **Graceful fallback.** If the LLM omits or misspells `pmesii`, Python defaults to `"none"`. No crash, no broken UI.
4. **No new infrastructure.** This phase requires zero new services, zero new dependencies, zero schema changes. Pure prompt + renderer enhancement.

## PMESII domain definitions (for the scorer prompt)

| Domain | Scope | Example |
|---|---|---|
| Political | Diplomacy, treaties, government policy, elections, sanctions as policy tool | "NATO-toppmøte vedtar 2 %-mål" |
| Military | Warfare, defense posture, troop movements, weapons systems, operations | "Russland flytter Iskander til Kaliningrad" |
| Economic | Sanctions impact, trade wars, budgets, financial markets, energy markets | "EU utvider sanksjoner mot russisk gull" |
| Social | Protests, civil unrest, public opinion, demographics, cultural events | "Massemønstringer ved VM-arenaer" |
| Information | Cyber operations, OSINT investigations, propaganda, hybrid influence, media manipulation | "Bellingcat avdekker desinformasjonsnettverk" |
| Infrastructure | Cables, pipelines, logistics, energy grid, transport networks, maritime routes | "Undersjøisk kabel kuttet i Barentshavet" |

## Done when

- `score_item()` returns `{ccir, cnr, pmesii, score, why}` — the `pmesii` field is always present.
- SAB HTML shows a PMESII domain badge (icon) on each item card.
- SAB HTML shows an aggregate PMESII distribution bar on the stats slide.
- `tests/test_score_parse.py` passes with the updated JSON structure.
- Live smoke: `python3 score/sab_html.py --hours 48 --no-bluf` renders items with PMESII badges.

## Tasks

### T1 · Update scorer prompt with PMESII domain assignment

- **File:** `score/triage_score.py` — `score_item()` prompt
- **Change:** Add PMESII domain definitions to the prompt. Update the JSON schema to include `"pmesii": "<Political | Military | Economic | Social | Information | Infrastructure | none>"`. Add worked examples with PMESII tags. Update the fallback dict to include `"pmesii": "none"`.
- **Prompt additions (insert after the disambiguation guide):**

```
PMESII domain (choose the ONE primary operational domain this item falls under):
- Political: Diplomacy, treaties, government policy, elections, sanctions as policy instrument.
- Military: Warfare, defense posture, troop movements, weapons systems, military operations.
- Economic: Sanctions impact, trade wars, defence budgets, financial markets, energy markets.
- Social: Protests, civil unrest, public opinion, demographics, cultural/sporting events with political dimension.
- Information: Cyber operations, OSINT investigations, propaganda, hybrid influence, media manipulation.
- Infrastructure: Undersea cables, pipelines, logistics networks, energy grid, transport, maritime routes.
- "none" if ccir is "none" (irrelevant items have no operational domain).
```

- **JSON schema update:**
```
{"ccir": "<...>", "cnr": "<I | II | none>", "pmesii": "<Political | Military | Economic | Social | Information | Infrastructure | none>", "score": 0-10, "why": "<=12 words, in Norwegian>"}
```

- **Fallback update:**
```python
v = {"ccir": "none", "cnr": "none", "pmesii": "none", "score": 0, "why": "uleselig modell-svar"}
```

- **Verify:**
  ```bash
  python3 -m py_compile score/triage_score.py
  python3 score/triage_score.py --sample --json | python3 -c "import json,sys; d=json.load(sys.stdin); assert all('pmesii' in x for x in d), 'missing pmesii'; print('OK', len(d), 'items')"
  ```

### T2 · Add PMESII badge to SAB HTML items

- **File:** `score/sab_html.py` — `render_item()`, CSS, and the icon mapping
- **Changes:**
  1. Add `PMESII_ICONS` dict mapping lowercase domain names to emoji icons.
  2. In `render_item(v)`, extract `pmesii` field, look up icon, render as a `<span class="pmesii-badge">` inside the item body.
  3. Add CSS for `.pmesii-badge` (small inline icon, subtle styling).
  4. Update `render_section()` to pass through `pmesii` from items.

- **Icon mapping:**
  ```python
  PMESII_ICONS = {
      "political": "🏛️", "military": "⚔️", "economic": "💰",
      "social": "👥", "information": "📡", "infrastructure": "🌉",
  }
  ```

- **CSS:**
  ```css
  .pmesii-badge {
      font-size: 13px;
      margin-right: 6px;
      vertical-align: middle;
      opacity: 0.8;
  }
  ```

- **Verify:**
  ```bash
  python3 -m py_compile score/sab_html.py
  python3 score/sab_html.py --hours 48 --no-bluf
  grep 'pmesii-badge' data/digests/sab.html | head -3
  ```

### T3 · Add PMESII distribution to stats slide

- **File:** `score/sab_html.py` — `build_html()`, stats slide template
- **Change:** Compute domain distribution from kept verdicts. Render a horizontal bar or grid showing count per PMESII domain. Insert into the stats slide, below the existing stats-slide-grid.
- **Implementation:** In `build_html()`, count items per `pmesii` value. Pass as a formatted HTML fragment (like `{cnr}` and `{fetch_line}`). Render as a styled grid with domain icons + counts.

- **Verify:**
  ```bash
  python3 score/sab_html.py --hours 48 --no-bluf
  grep -c 'pmesii-bar\|pmesii-grid\|pmesii-dist' data/digests/sab.html
  ```

### T4 · Update existing tests for new JSON structure

- **File:** `tests/test_score_parse.py`
- **Change:** Update all 5 test payloads to include `"pmesii"` in the mock LLM response. Add assertion that `pmesii` field is present and correctly extracted. Add one bonus test for missing `pmesii` field (fallback to `"none"`).
- **New test cases:**
  - All existing tests get `"pmesii": "Military"` (or appropriate domain) in their mock payload
  - Bonus F: missing `pmesii` key in LLM response → falls back to `"none"` (graceful degradation)

- **Verify:**
  ```bash
  python3 tests/test_score_parse.py -v
  ```

### T5 · Add PMESII reference to ccir.md (optional, operator-decided)

- **File:** `ccir.md`
- **Change:** Append a short PMESII reference section at the bottom (after the CNR section) to anchor the LLM's domain assignment. This is informational only — the scorer prompt is the actual instruction.
- **Draft:**
  ```markdown
  ## PMESII — operasjonelle domener (analytisk berikelse)
  
  Hvert saker kan tilordnes én primær PMESII-domene:
  - **Political** — diplomati, traktater, regjeringspolitikk, valg
  - **Military** — krig, forsvarsstyrke, tropper, våpensystemer
  - **Economic** — sanksjoner, handel, budsjetter, markeder
  - **Social** — protester, uro, opinion, demografi
  - **Information** — cyber, OSINT, propaganda, påvirkning
  - **Infrastructure** — kabler, rør, nettverk, energi, transport
  ```
- **Note:** This is operator-editable. The scorer prompt (T1) is the binding instruction; this section is reference context.

### T6 · Live smoke test

- **Command:**
  ```bash
  python3 score/sab_html.py --hours 48 --no-bluf
  # Verify: items have pmesii badges, stats slide has domain distribution
  open http://localhost:8888/sab.html
  ```
- **Verify:** Items show PMESII domain icons. Stats slide shows domain distribution. No broken items or missing badges.

## Files touched

| File | Change | Task |
|---|---|---|
| `score/triage_score.py` | Add PMESII domain definitions + update JSON schema in prompt; update fallback dict | T1 |
| `score/sab_html.py` | Add PMESII icon mapping, badge rendering in items, domain distribution in stats slide | T2, T3 |
| `tests/test_score_parse.py` | Update mock payloads + add PMESII assertions + bonus fallback test | T4 |
| `ccir.md` | Optional: append PMESII reference section | T5 |

## Files NOT touched

- `score/digest.py` (no changes to the Markdown digest writers — PMESII is SAB HTML-only for now)
- `score/fever_triage.py` (no changes to the Fever loop)
- `docker-compose.yml` (no infrastructure changes)
- `requirements.txt` (no new dependencies)
- `.env` / `.env.example` (no new env vars)

## Risks / Notes

- **Token cost:** +5–10 tokens per item for the extra JSON field. At 100 items, that's ~500–1000 extra tokens total — negligible.
- **Model compliance:** qwen3.6 might occasionally omit `pmesii` or capitalize it differently. The `.lower()` + `.get("pmesii", "none")` fallback handles this gracefully.
- **PMESII ≠ CCIR replacement.** This is an enrichment layer, not a restructuring. CCIR stays the primary organizational axis. PMESII adds a cross-cutting analytical dimension.
- **JIPOE primer:** This phase directly feeds the planned JIPOE Step 2 restructuring. When that phase happens, PMESII domain tags will already be available for the "Describe Environmental Effects" block.

## Verification at close

```bash
# T1: scorer returns pmesii
python3 score/triage_score.py --sample --json | python3 -c "
import json, sys
d = json.load(sys.stdin)
for x in d:
    assert 'pmesii' in x, f'missing pmesii in {x.get(\"title\",\"?\")}'
print(f'OK — {len(d)} items all have pmesii')
"

# T2+T3: SAB renders badges + distribution
python3 score/sab_html.py --hours 48 --no-bluf
grep -c 'pmesii-badge' data/digests/sab.html

# T4: tests pass
python3 tests/test_score_parse.py -v

# T6: all tests together
python3 tests/test_score_parse.py -v && python3 tests/test_write_bluf.py -v && python3 tests/test_opml_roundtrip.py -v
```

## Cross-phase coordination

- **Phase 1 dependency:** Phase 1 must be complete (scorer tests, PROFILE cleanup, .env.example) before this phase starts. Phase 1 is done.
- **Phase 2+ independence:** This phase does not block or depend on World Monitor, Postgres, or embeddings.
- **JIPOE future phase:** PMESII tags in `verdicts.jsonl` will be the input data for JIPOE Step 2 restructuring. This phase is the data prerequisite.
