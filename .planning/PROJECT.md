# PROJECT — trimail

> **Status:** OSINT pipeline in transition. Current implementation is a local spike on FreshRSS + Gmail + rss-bridge. Target is a Postgres-backed, CCIR-driven, COP-fronted intelligence fusion system, all-local, all-free, all-LLM = local qwen3.6.

## What trimail is

A **local, free, COP-ready OSINT/all-source intelligence platform** for one operator — a Norwegian-context information triage hub that fuses RSS, email, websites, and (eventually) SOCMINT + event databases against a Commander's Critical Information Requirements (`ccir.md`) taxonomy, scores each item with a local LLM, and produces a daily Situational Awareness Brief (SAB) with a CNR (Commander's Notification Requirements) alerting lane.

The point is the **noise killer**: most items answer no CCIR and should disappear from the unread list. The model decides on the Mac; nothing leaves the machine.

The north star is **Palantir Gotham-grade fusion at personal scale** — a single fused map (Common Operating Picture, COP) with reliable entities tracked across modalities, LLM-assisted analytics, CCIR-style tasking, NL/RAG recall over the corpus, and real-time CNR alerting. Free, local, on a Mac.

## What trimail is *not*

- Not a reader. FreshRSS is the reader; trimail sits behind it.
- Not a cloud service. ADR-004 forbids cloud LLMs anywhere in the runtime.
- Not multi-user. Single operator. No auth, no tenancy.
- Not complete. FreshRSS+Gmail+rss-bridge is the **current** scope. The PQ+vector + COP + SOCMINT layers are **target**.

## How it works (current spike)

```
 RSS / YouTube / Reddit ─▶ FreshRSS :8088 ─┐
 websites ─ rss-bridge :3000 ─▶            ├─ Fever API ─▶ fever_triage.py ─▶ triage_score.py
 Gmail ─ gmail_to_atom.py ─▶ feeds: ───────┘              │                  │
                                                          │ mark score≤3 read │
                                                          └─▶ digest.py ──▶ brief.md / cluster.md / list.md
                                                                                ▲
                                                                       ccir.md (the taxonomy)
                                                                                ▲
                                                                  qwen3.6 via oMLX :8000/v1
                                                                            (Ollama :11434/v1 fallback)
```

## How it works (target — ARCHITECTURE Phase 0–4 + ADR-003)

```
 feeds/email/rss-bridge ─▶ FreshRSS ─┐
                                     │ Fever
                                     ▼
                       ┌─── PostgreSQL + pgvector ───┐
                       │ trimail.articles            │  ← our copy, durable
                       │ trimail.enrichment          │  ← ccir, cnr, score, why
                       │ trimail.embeddings          │  ← bge-m3 multilingual
                       │ trimail.ccir                │  ← defs + embeddings
                       │ freshrss.*                  │  ← FreshRSS own schema
                       └─────────────────────────────┘
                                       │
              SAB ◀ semantic dedup · CCIR pre-filter · RAG recall
              COP ◀ (gated) World Monitor / Taranis UI (Phase 3+)
```

## Hard constraints (load-bearing)

These are not defaults — they are rules. If a future change appears to violate one, stop and re-decide.

1. **ADR-004 — All LLM is local.** Every stage runs against the local qwen3.6 (`qwen36-ud-4bit` via oMLX `:8000/v1`, API key `omlx`; Ollama `:11434/v1` fallback). **No cloud LLM in the runtime pipeline, ever.** Cloud models are only used for *this* assistant during design.
2. **No paid services.** Free + self-hosted. RSS, IMAP, FreshRSS, Postgres, oMLX, Ollama. The OPML is curated accordingly.
3. **Read-only against sources.** Gmail IMAP is `readonly=True`. No markup, no deletes, no replies.
4. **One query surface in target state.** One Postgres instance; FreshRSS owns its schema; `trimail.*` owns ours. No fan-out.
5. **The CCIR is the brain.** `ccir.md` is the taxonomy. Editing it changes triage. Editing code to change triage is wrong.
6. **Polite polling.** GDELT ≤1 req / 5 s. Compose cadence is twice an hour at `:23,:53`. Per-feed TTLs are operator-tunable in the UI. Manual "Refresh all" is discouraged in the README.

## Current verified state (per README, 2026-06-23)

| Piece | State |
|---|---|
| FreshRSS + rss-bridge + feeds in Docker | ✅ reachable (`:8088`, `:3000`) |
| qwen36 triage vs oMLX endpoint | ✅ correct buckets, ~3 s/item |
| Internal `http://feeds/gmail.xml` | ✅ reachable |
| Scorer → Fever auto-mark-read | ⚠️ Imports clean (PROFILE alias added 2026-06-23; CCIR mirrored). **Runtime smoke against live FreshRSS still pending** — the original "✅ wired + tested live" claim from README is unverified-in-our-session, only the import surface has been re-validated. |
| FreshRSS provisioned headless (admin/trimailLocal23, 44 feeds, 1642 articles) | ✅ done |
| Gmail→Atom bridge | ⚠️ written, **untested** — needs GMAIL_APP_PASSWORD |
| `.env.example` | ❌ referenced by README, missing in tree |

## North-star benchmark (ADR-003)

| Capability | North star | trimail's personal-scale shadow |
|---|---|---|
| Fused map / globe | Palantir Maven Smart System | World Monitor (globe.gl+deck.gl, Ollama, 500+ feeds) — gated on Open-Q1 |
| Entity / relationship graph | Semantica Pro + Cortex EIP | OpenCTI / MISP (deferred — STIX2 cyber-CTI flavoured) |
| NL/RAG investigation | Babel Street Investigator | trimail Phase 4 RAG SAB / recall |
| Real-time alerting | Dataminr | trimail CNR 🚩 surfaced in SAB (push TBD) |
| Crisis handoff | RAYVN (DSB 2023 Norway) | out of scope (trigger-throws-handoff only) |

## References

- `docs/ARCHITECTURE.md` — ADRs and Phase 0–4 plan
- `docs/RESEARCH-REPORT.md` — 2026-06-23 prior art (23 sources → 25 verified claims)
- `ccir.md` — the triage taxonomy
- `.planning/codebase/` — current code map
- `.planning/REQUIREMENTS.md` — live vs target vs gated requirements
- `.planning/ROADMAP.md` — phases
- `.planning/STATE.md` — pick-up-next-session memory
</content>
