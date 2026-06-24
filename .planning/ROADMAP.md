# ROADMAP — InfoTriage

> Sequenced to **stabilize what's running first**, then **gate the architecture on the empirical World Monitor test**, then **build the durable foundation (Postgres)**, then **layer enrichment, dedup, RAG**. Source-of-truth for the phase target lives in `docs/ARCHITECTURE.md` Phase 0–4; this roadmap is the executable cut of that, with the open questions kept load-bearing.

## Phase index

> **Ingester-first refactor (operator pivot, 2026-06-23).** The operator's imminent need is to **read Gmail + new sources**; the architecture ambitions (WM gate → Postgres → embeddings → RAG → SOCMINT → COP → push) are **icing on the cake**. Phases 2–7 are **deferred until the ingest loop proves operational value**. Active plan: Phase 0 (spike, done) + Phase 1 (stabilize + new ingest bridges). New ingester bridges are scaffolded: `bridge/imap_to_atom.py` (multi-mailbox IMAP), `bridge/yt_to_atom.py` (YouTube + audio transcription), `bridge/RSS_BRIDGE_NOTES.md` (sites-via-rssbridge ops notes). Cross-ref: `.planning/phases/phase-1-stabilize-spike/PLAN.md` (T8/T9/T10 added for the new bridges).

| Phase | Title | ADR anchors | Status |
|---|---|---|---|
| **0** | Spike (FreshRSS + rss-bridge + qwen36 + Fever + Digest) | ADR-004 | ✅ done — runs today |
| **1** | Stabilize the spike + ingester expansion | ADR-004 | ✅ mostly done |
| **1.5** | PMESII enrichment (operational domain tagging) | JIPOE Step 2 | planned |
| **2** | World Monitor Open-Q1 spike (gate) | ADR-003 | ⏸ deferred — concept validation pending |
| **3** | Postgres + pgvector foundation | ADR-001 | ⏸ deferred — concept validation pending |
| **4** | Embeddings + semantic dedup | ADR-001 (P2), RESEARCH §8 | ⏸ deferred — concept validation pending |
| **5** | CCIR pre-filter + RAG SAB | ADR-001 (P3, P4) | ⏸ deferred — concept validation pending |
| **6** | SOCMINT + Arctic collection plugins | ADR-003 | ⏸ deferred — concept validation pending |
| **7** | Notification & dissemination | ADR-003 | ⏸ deferred — concept validation pending |

---

## Phase 1 — Stabilize the spike

**Why.** The spike already runs end-to-end (Fever + score + SAB + Gmail-bridge path). Before any architecture work, lock it in: prove the Gmail bridge, document the `.env`, and make layer changes safe by adding tests around the scorer parser.

**Done when.** `bridge/gmail_to_atom.py` produces a valid `data/feeds/gmail.xml` for a real Gmail app password; `.env.example` lands; tests around `score_item()` JSON extraction exist.

**Scope (small, surgical):**
- ✅ **PROFILE alias added 2026-06-23** in `score/triage_score.py`: `PROFILE = CCIR` with provenance comment. README's two PROFILE references keep working; `from triage_score import PROFILE` resolves; runtime smoke against FreshRSS+oMLX is the next required check before the README "✅ wired + tested live" claim can be re-asserted.
- Add `.env.example` with `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`, `GMAIL_USER`, `GMAIL_APP_PASSWORD`, `GMAIL_QUERY`, `FRESHRSS_FEVER_URL`, `FRESHRSS_FEVER_USER`, `FRESHRSS_FEVER_API_PASSWORD`.
- Run the Gmail bridge end-to-end on a real account; confirm `data/feeds/gmail.xml` is valid and FreshRSS subscribes to `http://feeds/gmail.xml`. Document the X-GM-RAW query syntax and the read-only posture.
- Pin `feedgen` in `requirements.txt`.
- Smoke tests for the scorer prompt's JSON extraction (good, bad, code-fence cases).
- Decide Q4 (FreshRSS migration strategy) by pick: re-provision fresh on Postgres in Phase 3 is the simple path; migrate SQLite data is the lossy path.

**Out of scope.** Any architectural change.

---

## Phase 2 — World Monitor Open-Q1 spike (gate)

**Why.** `docs/RESEARCH-REPORT.md` identified World Monitor as the map-fronted aggregation + COP core, but the open question is whether its local Ollama path covers **CCIR scoring + SAB briefing** (not just classification/summarization). Until that's answered, do not commit to UI choices. This phase *is* the gate.

**Done when.** World Monitor runs against `http://127.0.0.1:8000/v1` (oMLX) with `LLM_MODEL=qwen36-ud-4bit`, scores a sample of InfoTriage's own items, and writes a brief that mirrors InfoTriage's `brief.md` structure. Pass = adopt WM as the COP layer. Fail = fall back to MapLibre self-built or Taranis (Open-Q2).

**Scope:**
- Stand up World Monitor on the Mac (Tauri or Docker; Tauri is the air-gapped profile).
- Wire `LLM_BASE_URL=http://127.0.0.1:8000/v1`, `LLM_API_KEY=omlx`.
- Inject the `ccir.md` taxonomy + a curated Norwegian-source subset.
- Score 20 InfoTriage items; write a structured output covering CCIR sections.
- Decision: go (adopt), no-go (fall back), or partial (use WM for COP only, keep custom scorer + SAB).

**Side-effects regardless of gate outcome:**
- The InfoTriage FreshRSS+qwen3.6 spike stays the daily driver. No work blocked by this.
- The decision lands in `docs/RESEARCH-REPORT.md` as an update + a new ADR (proposed: ADR-005).

**Out of scope.** Adopting World Monitor in production. Configuring TAK/CloudTAK. Taranis evaluation (separate spike, Open-Q2).

---

## Phase 3 — Postgres + pgvector foundation (ADR-001)

**Why.** Today the de-facto store is `data/verdicts.jsonl` and dedup is keyword overlap. Both fail in the ways `docs/ARCHITECTURE.md` describes. Postgres+pgvector is the single store, the durability story for our article copies, and the substrate for embeddings (Phase 4).

**Done when.** FreshRSS runs on Postgres (its own schema) and `InfoTriage.*` schema exists with `articles`, `enrichment`, `ccir` tables. The SAB builds from SQL. `verdicts.jsonl` is no longer the source of truth.

**Scope (corresponds to ARCHITECTURE Phase 0–1):**
- Add Postgres+pgvector container to `docker-compose.yml`. ARCHITECTURE specifies "PostgreSQL 16 + pgvector" only — verify the latest stable pgvector image tag at the time of the spike (provisional: `postgres:16` and `pgvector/pgvector:pg16`).
- Re-provision FreshRSS on Postgres (per Phase 1 Q4 decision).
- Create `InfoTriage` schema + `articles`, `enrichment`, `ccir` tables matching `docs/ARCHITECTURE.md` data model.
- Replace `score/digest.py`'s `data/verdicts.jsonl` write with `InfoTriage.enrichment` upsert; keep `verdicts.jsonl` as a debug aid for one cycle.
- Read path (Fever → score → upsert) writes to Postgres; SAB reads from Postgres.
- Schema validation via `psycopg` constraints; small migration script tracked in `score/migrations/`.

**Side-effects.** Decorates the spike with a real store; paves the way for embeddings and semantic dedup.

---

## Phase 4 — Embeddings + semantic dedup

**Why.** Today's keyword-overlap clustering quietly fails across languages (NRK "Nato-toppmøte" ≠ BBC "NATO summit" ≠ TASS "Саммит НАТО"). Semantic dedup collapses them. This phase also resolves Q5 (embedding model).

**Done when.** Same story from three languages collapses to one cluster in `InfoTriage.cluster` view. Embedding model + dim recorded in `docs/RESEARCH-REPORT.md` update.

**Scope:**
- Stand up Ollama (if not already) on `:11434`; pull `bge-m3` (1024-d) or `mE5-large`, decided by Q5.
- Embed each `InfoTriage.articles` row (chunked per P-6) into `InfoTriage.embeddings(vector vector(1024))`.
- ivfflat index over `InfoTriage.embeddings.vector`.
- Replace keyword-overlap `cluster()` in score/digest.py with cosine clustering against embeddings.
- Update `InfoTriage.ccir` to include `ccir_def.vector` so that Phase 5 pre-filtering can rank.

**Out of scope.** Replacing the LLM. Adding SOCMINT collectors. Phase-5 pre-filter and RAG build on this.

---

## Phase 5 — CCIR pre-filter + RAG SAB

**Why.** Right now every unread item goes to the LLM. Phase 5 cuts caller volume and sharpens tagging using the embedded CCIR definitions, then enables the **RAG SAB** — "what do we know about X since date" — over the durable corpus.

**Done when.** Clearly-off-topic items skip the LLM (logged in `InfoTriage.audit`) AND a themed recall brief cites stored articles with stable IDs.

**Scope:**
- Pre-filter: `cosine(article.embedding, ccir.vector) < τ` → skip LLM, mark as `pruned`.
- RAG SAB: vector retrieve top-k by filter, feed to qwen3.6 to write the brief; cite `articles.id` / `articles.url` per claim.
- Add `InfoTriage.audit` table for the pre-filter decisions (which CCIR it dropped against, model used, latency).
- Expose thematic recall as a CLI (`python3 score/recall.py --topic "PIR-2 Nordområdene" --since 14d`).

**Out of scope.** Map/autocomplete UI. Push notifications (Phase 7).

---

## Phase 6 — SOCMINT + Arctic collection plugins

**Why.** Map of the world is incomplete with only RSS + email. SOCMINT (Telegram, YouTube transcription) and authoritative Arctic data (BarentsWatch AIS) round out the picture per ADR-003.

**Done when.** Telethon Telegram collector, yt-dlp+mlx-whisper YouTube collector, and BarentsWatch AIS poller write to `InfoTriage.articles` with explicit `source.discipline` tags. SOCMINT legal/ToS posture documented.

**Scope:**
- `collectors/telegram.py` — Telethon, account from environment, writes to `InfoTriage.articles` with `discipline=socmint`.
- `collectors/yt_dlp_whisper.py` — yt-dlp + mlx-whisper per docs/RESEARCH-REPORT.md §9.
- `collectors/barentswatch.py` — Live AIS + ArcticInfo with rate-limit posture.
- Add reliability ratings (Admiralty) per source in `InfoTriage.sources`.
- Defer Instagram / Facebook (Open).
- ACLED only if Q3 resolved (paid license); do not feed ACLED to local LLM without one.

**Out of scope.** Cross-source entity resolution (deferred until A-3 lands).

---

## Phase 7 — Notification & dissemination

**Why.** A CNR CAT I 🚩 should not require someone to refresh the SAB at 23:00. The InfoTriage-with-RAYVN-style handoff pattern needs an alerting path.

**Done when.** A CAT I event post-write triggers a push (Signal / ntfy) with the SAB excerpt + dedupe ID, AND the SAB remains the canonical artifact.

**Scope:**
- Pick a push channel (ntfy.sh local-server preferred; free + on-Mac; ADR-004-friendly).
- `score/fever_triage.py` and `score/digest.py` write a CNR-I event to a tiny in-process queue.
- A small relay process emits ntfy messages with title + bullet + URL.

**Out of scope.** TAK / CloudTAK CoT markers (deferred — Phase 3+ doctrinal interop, not first step).

---

## Sequencing notes

- **Phases 1 and 2 are parallel-safe.** Both run against the live spike; neither depends on Postgres. Do them concurrently or in either order; both emit a clear go/no-go.
- **Phases 3 onward are sequential.** Phase 3 is the foundation; everything else assumes the schema. Phases 4 → 5 are tightly coupled.
- **Phases 6 and 7 are independent** after Phase 5.
- **No phase ever revisits ADR-004.** If a future requirement seems to require a cloud LLM, that's a new ADR, not a phase edit.

## Anti-roadmap (deliberately excluded)

- X / Twitter (constrained; revisit only as separate Nitter spike).
- Cloud LLM (ADR-004 reject).
- Multi-user / tenancy.
- TAK/CloudTAK in early phases.
- ACLED via local LLM without a paid public-sector license (Q3).
</content>
