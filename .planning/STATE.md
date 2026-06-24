# STATE — InfoTriage

> **Ephemeral.** This file is pick-up-next-session memory. Move durable context into `docs/`, `.planning/PROJECT.md`, `.planning/REQUIREMENTS.md`, `.planning/ROADMAP.md`, or `.planning/codebase/`. Trim aggressively at end-of-session.

## Session: 2026-06-23 (init)

### Just-completed
- Built the `.planning/` scaffold for InfoTriage: `PROJECT.md`, `REQUIREMENTS.md`, `ROADMAP.md`, `STATE.md`, `config.json`, plus a `codebase/` map (`index`, `architecture`, `structure`, `concerns`).
- Re-read every repo file to ground the docs (README, ccir.md, docker-compose.yml, requirements.txt, opml/feeds.opml, docs/ARCHITECTURE.md, docs/RESEARCH-REPORT.md, score/{digest,triage_score,fever_triage}.py, bridge/gmail_to_atom.py, .gitignore).
- Reconciled the **"personal info-triage hub" (README) vs "Palantir-grade OSINT** (ARCHITECTURE ADR-003)"** framing tension via the thinker-with-files-gemini → landed on **"OSINT pipeline in transition"** with `ccir.md` as the brain and ADR-004 as a hard load-bearing constraint.
- Established ROADMAP phasing that interleaves **spike stabilization** + **World Monitor Open-Q1 gate** *before* the Postgres foundation.
- Ran code-reviewer-minimax-m3 over the new `.planning/` files; surfaced **one BLOCKING issue propagated from README into the docs**: `score/fever_triage.py` imports `PROFILE` from `score/triage_score.py`, but `PROFILE` is not defined there. README says the loop is "✅ wired + tested live"—that claim is unverified until the import is fixed. Folded into `ROADMAP.md` Phase 1 as the first action and reflected in `PROJECT.md` / `REQUIREMENTS.md DI-2` / `STATE.md`.

### Spike state (no work done in this session, just observed)

| Piece | State |
|---|---|
| FreshRSS + rss-bridge + feeds | ✅ up (:8088, :3000) |
| `data/verdicts.jsonl` being written by `digest.py` | ✅ |
| Fever auto-mark-read | ⚠️ imports clean — PROFILE alias added 2026-06-23 (`PROFILE = CCIR`). Runtime smoke against FreshRSS+oMLX still pending; original README “✅ wired + tested live” claim un-re-verified this session |
| qwen36 vs oMLX | ✅ buckets correct, ~3 s/item |
| Gmail→Atom bridge | ⚠️ untested |
| `.env.example` | ❌ missing |

### Open questions (gating decisions)

1. **Q1** — World Monitor Ollama path covers CCIR scoring + SAB briefing? → gates Phase 2 go.
2. **Q2** — Taranis AI local-LLM endpoint? → gates Phase 6 alt path.
3. **Q3** — ACLED license? → gates Phase 6 C-11.
4. **Q4** — FreshRSS migration: re-provision fresh vs SQLite data? → gates Phase 3 seam.
5. **Q5** — Embedding model: bge-m3 (1024-d) vs mE5-large? → gates Phase 4 P-5.

### Next session — first actions (in order)

1. **Phase 1 — Stabilize the spike.** Plan moved to `.planning/phases/phase-1-stabilize-spike/PLAN.md`. PROFILE alias applied; remaining first actions:
   - Add `.env.example` mirror of all env reads.
   - Run `bridge/gmail_to_atom.py` end-to-end against a real Gmail app password (operator-supplied creds).
   - Pin `feedgen` in `requirements.txt`.
   - Add `tests/test_score_parse.py` covering JSON extraction (good / code-fence / garbage).
   - Smoke `python3 score/fever_triage.py --dry-run --max 5` against live FreshRSS+oMLX.
   - Decide Q4 (re-provision fresh vs SQLite→Postgres).

2. **Phase 2 — World Monitor Open-Q1 spike.** Can run in parallel with Phase 1; should *not* run after Phase 3 (the empirical test is meaningless on already-cocooned infrastructure; do it on the live spike).

### Don't lose these

- **CCIR is the brain.** Editing `ccir.md` retunes everything. Do not retune via Python.
- **ADR-004 is a hard rule.** If a future change appears to need a cloud LLM, stop. New ADR.
- **`data/` is gitignored.** Never commit `data/`. Never commit `.env`.
- **Scorer parse is brittle.** `score_item()` returns `uleselig modell-svar` if model output drifts. Detect, don't paper over.
- **GDELT = 1 req / 5 s.** Twice-hourly `CRON_MIN: "23,53"` + per-feed TTL is the safe posture; manual "Refresh all" is not.

### Files touched this session (no commits)

Created:
- `.planning/PROJECT.md`
- `.planning/REQUIREMENTS.md`
- `.planning/ROADMAP.md`
- `.planning/STATE.md`
- `.planning/config.json`
- `.planning/codebase/index.md`
- `.planning/codebase/architecture.md`
- `.planning/codebase/structure.md`
- `.planning/codebase/concerns.md`

Modified:
- `score/triage_score.py` — added `PROFILE = CCIR` alias with provenance comment.

Created (this continuation):
- `.planning/phases/phase-1-stabilize-spike/PLAN.md` — executable plan-phase artifact.

Not touched: `docs/ARCHITECTURE.md`, `docs/RESEARCH-REPORT.md`, `ccir.md`, `README.md`, compose, OPML.

### Decisions logged this session

- PMC-001: InfoTriage's `.planning/` framing = "OSINT pipeline in transition," not LARP-nor-narrow.
- PMC-002: ROADMAP sequencing = Phase 1 (stabilize) → Phase 2 (WM gate) → Phase 3 (Postgres). Embeds the open question as a load-bearing gate, not a side note.
- PMC-003: REQUIREMENTS grouping = intelligence cycle (Direction / Collection / Processing / Analysis / Production / Dissemination / Navigation), with status tags `[LIVE/SPIKE/TARGET/GATED/OUT]`.
- PMC-004: STATE.md is ephemeral; durable context goes into the other docs. Trim each session.
- PMC-005: Bug-fix approach = alias (`PROFILE = CCIR` in `score/triage_score.py`), not import-drop, to preserve README's two PROFILE references with zero behavioural change. Trade-off documented inline in `score/triage_score.py`.

(Decision log will be replaced each session. Long-term decision memory belongs in `./docs/` or in the roadmap.)
</content>
