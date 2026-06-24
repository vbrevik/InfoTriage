---
phase: 0
slug: concept-spike
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-24
---

# Phase 0 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source: `00-RESEARCH.md` § Validation Architecture. This is a THROWAWAY spike — validation
> proves each unknown's go/no-go bar, not production correctness.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x available (Python 3.13.5); spike scripts use ad-hoc `assert` + `print` |
| **Config file** | none — existing `tests/` cover the production pipeline, not the spike |
| **Quick run command** | `python3 .spike/<unknown>/<script>.py --smoke` (exits after first success) |
| **Full suite command** | `python3 -m pytest .spike/` (only if spike scripts are written as pytest) |
| **Estimated runtime** | ~30–120 s per unknown (R5 is manual/GUI) |

---

## Sampling Rate

- **Per spike task:** Run the corresponding smoke command below before recording a go/no-go.
- **Per wave:** N/A — the spike is not wave-organized; each unknown is a standalone task.
- **Phase gate:** All 5 unknowns must have a recorded go/no-go/**partial** in `SPIKE-FINDINGS.md` before Phase 0 closes.
- **Max feedback latency:** ~120 s.

---

## Per-Task Verification Map

| Req | Behavior | Test Type | Automated Command | File Exists | Status |
|-----|----------|-----------|-------------------|-------------|--------|
| R1 | `item.ingested` published by A consumed by B via designed routing | integration | `python3 .spike/r1_rabbit/r1_publisher.py && python3 .spike/r1_rabbit/r1_consumer.py --smoke` | ❌ W0 | ⬜ pending |
| R1 | Poison message routes to DLQ | integration | `python3 .spike/r1_rabbit/r1_consumer.py --poison-test` | ❌ W0 | ⬜ pending |
| R2 | ≥80% triple collapse at one chosen threshold | measurement | `python3 .spike/r2_dedup/r2_threshold.py` (reports collapse_rate) | ❌ W0 | ⬜ pending |
| R2 | 0 control over-merges | measurement | same script — assert `control_overmerge == 0` | ❌ W0 | ⬜ pending |
| R3 | One entity linked across ≥3 items / 2 languages | integration | `python3 .spike/r3_entities/r3_link.py --verify-test` | ❌ W0 | ⬜ pending |
| R3 | Distinct control entity NOT over-merged | integration | same script — assert distinct entity IDs | ❌ W0 | ⬜ pending |
| R4 | Standing wiki page carries ≥3 source-ID citations from ≥5 items | smoke | `python3 .spike/r4_wiki/r4_wiki.py | grep -cE '\[[0-9]+\]'` | ❌ W0 | ⬜ pending |
| R4 | On-demand article produced | smoke | `python3 .spike/r4_wiki/r4_wiki.py --on-demand --topic "NATO"` | ❌ W0 | ⬜ pending |
| R5 | World Monitor launches against local LLM (oMLX/Ollama) | smoke | `cd .spike/r5_worldmonitor && npm run tauri dev` (manual observe) | ❌ W0 | ⬜ pending |
| R5 | 20 items scored + CCIR-structured brief produced; compared to `write_bluf()` | integration | manual — R5 is a GUI app | manual only | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Scratch scaffolding to create before any go/no-go can be recorded (all under deletable `.spike/`, D-06):

- [ ] `.spike/docker-compose.yml` — ephemeral pgvector + RabbitMQ on distinct ports (22060/22061/22062), separate volumes (D-04)
- [ ] `.spike/r1_rabbit/r1_topology.py` — `infotriage.events` topic exchange + `infotriage.dlx` DLX/DLQ (DLX declared first)
- [ ] `.spike/r1_rabbit/r1_publisher.py` — dummy service A (publisher confirms)
- [ ] `.spike/r1_rabbit/r1_consumer.py` — dummy service B (ack/nack, `--poison-test`)
- [ ] `.spike/r2_dedup/r2_fetch.py` — fresh NRK/BBC/TASS fetch (`defusedxml`, read-only)
- [ ] `.spike/r2_dedup/same_story_triples.csv` — ≥10 hand-labeled triples + ≥5 control pairs (human step after fetch)
- [ ] `.spike/r2_dedup/r2_embed.py` — bge-m3 / mE5-large batch embed + cosine matrix
- [ ] `.spike/r2_dedup/r2_threshold.py` — threshold sweep → collapse rate + control-overmerge count
- [ ] `.spike/r3_entities/r3_schema.sql` — entities + entity_links + HNSW (`vector_cosine_ops`)
- [ ] `.spike/r3_entities/r3_ner.py` — qwen36 NER via `llm()` (ADR-004)
- [ ] `.spike/r3_entities/r3_link.py` — `<=>` cosine link + merge
- [ ] `.spike/r4_wiki/r4_wiki.py` — wiki synthesis + citation check (extends `write_bluf()`)
- [ ] `.spike/r5_worldmonitor/r5_prep.py` — export 20 InfoTriage-scored items for WM

---

## Manual-Only Verifications

| Behavior | Req | Why Manual | Test Instructions |
|----------|-----|------------|-------------------|
| World Monitor launch + COP globe render | R5 | GUI / Tauri desktop app | Build via `npm run tauri dev`; observe globe + AI brief; confirm no cloud LLM calls in network tab |
| 20-item CCIR brief comparison | R5 | Subjective adopt/build/drop judgment | Feed 20 pre-scored items; compare WM brief vs InfoTriage `write_bluf()`; record verdict in ADR-005 |
| Wiki-page coherence judgment | R4 | Coherence is a human judgment | Read the standing page; confirm it reads coherently and citations resolve to real source IDs |
| Same-story triple labeling | R2 | Ground-truth requires a human | Label ≥10 NRK/BBC/TASS triples + control pairs in the CSV before threshold sweep |

---

## Validation Sign-Off

- [ ] Each unknown has an automated smoke/measurement command OR a documented manual procedure
- [ ] R5 manual GUI steps are written down (no automated path exists)
- [ ] `.spike/` is gitignored; no spike credentials or fetched data committed
- [ ] All LLM/embedding endpoints verified local before each run (ADR-004; `LLM_BASE_URL` not cloud)
- [ ] Every unknown ends with go/no-go/**partial** recorded in `SPIKE-FINDINGS.md`
- [ ] `nyquist_compliant: true` set in frontmatter once the above hold

**Approval:** pending
