# ARCHITECTURE — trimail

Source of truth: `docs/ARCHITECTURE.md` ADRs + code-level data flow.
Generated: 2026-06-23.

## Current pipeline (spike — running today)

```
  opml/feeds.opml  ─────┐
   (61 RSS URLs, 10     │
    top-level outlines) │
                        ├──▶  FreshRSS (Docker :8088)  ──▶  Fever API
  bridge/gmail_to_atom.py──▶  data/feeds/gmail.xml  ──▶ (unread_item_ids
  bridge/imap_to_atom.py ──▶  data/feeds/<name>.xml ─▶  + items)
  bridge/yt_to_atom.py  ──▶  data/feeds/youtube-<slug>.xml ─▶
                          │                                          │
  (no native RSS)─────────▶  rss-bridge :3000  ──▶  FreshRSS         │
                          │                                          ▼
                          │                           score/fever_triage.py
                          │                             │
                          │                             ├─ score (LLM)
                          │                             ├─ bucket logic
                          │                             ├─ mark skip=read
                          │                             └─ print digest.md
                          │                             ▼
                          │                           ccir.md (PIR/FFIR/SIR)
                          │                             │
                          │                             ▼
                          │                           score/digest.py
                          │                             │
                          │                             ├─ cluster.md
                          │                             ├─ brief.md   (SAB)
                          │                             └─ bluf.md    (LLM-synth)
                          │
                          └─ Container-compose network "trimail"
```

## Target pipeline (ADR-001, Phase 0..4)

```
  feeds / email / rss-bridge ─▶ FreshRSS (ingest + reader) ─┐
                                                              │ Fever API (read new)
                                                              ▼
   qwen36  (score + tag CCIR/CNR) ──┐                     ┌───  PostgreSQL  ───────┐
   bge-m3  (embed multilingual)  ──┘                     │ trimail.articles      │
                                                          │ trimail.enrichment    │
                                                          │ trimail.embeddings    │── pgvector
                                                          │ trimail.ccir          │
                                                          │ freshrss.*            │
                                                          └───────────────────────┘
                                                                  │
                       SAB generator ◀──── semantic dedup · CCIR pre-filter · RAG recall
                       (CCIR sections, CNR 🚩, since-cutoff window)
```

## Phased build plan (from docs/ARCHITECTURE.md)

- **Phase 0** — Postgres + pgvector foundation. FreshRSS re-pointed.
- **Phase 1** — Enrichment in DB. Scorer writes to Postgres (`verdicts.jsonl` deprecated).
- **Phase 2** — Embeddings (bge-m3 / mE5-large). Replace keyword clustering with cosine — handles NRK/BBC/TASS dedup.
- **Phase 3** — CCIR pre-filter via embedding similarity.
- **Phase 4** — RAG / themed recall ("what do we know about X since date").

## Storage today vs tomorrow

| Layer | Today | Tomorrow (Phase 0+) |
|---|---|---|
| Article store | FreshRSS SQLite (or Postgres) | FreshRSS Postgres |
| trimail copy of bodies | none | `trimail.articles` |
| Scoring history | `data/verdicts.jsonl` (append-only) | `trimail.enrichment` |
| Embeddings | none | `trimail.embeddings` (pgvector) |
| CCIR taxonomy source | `ccir.md` (file) | `ccir.md` + `trimail.ccir` (embedded) |
| Reader UI | FreshRSS | FreshRSS (unchanged) |

## LLM touch-points (all local qwen3.6 — ADR-004)

| Stage | Role | File |
|---|---|---|
| Collection pre-filter | cheap relevance gate | (planned) |
| Scoring + CCIR/CNR tag | runtime scorer | `score/triage_score.py:score_item` |
| Cluster/fusion aid | (planned) summarize event clusters | — |
| Production (SAB) | writes the brief | `score/digest.py:write_brief`, `write_cluster`, `write_list`, `write_bluf` |
| RAG / NL query | "what do we know about X" | (Phase 4) |

## CCIR routing (the brain — `ccir.md`)

Four levels, in render-order:

- **PIR** — Priority Intelligence Requirements (external: threats, environment). 1..6.
- **FFIR** — Friendly Force Information Requirements (home: Norway). 1..3.
- **SIR** — Specific Intelligence Requirements (time-bounded, event-driven). 1..2 (Midtøsten/US-Iran, Sport/VM 2026).
- **CNR** — Commander's Notification Requirements (CAT I 🚩, CAT II 📋, Routine).

`score/digest.py`'s `CCIR_ORDER` is the **render-engine** contract — it determines the section order in `brief.md`, `cluster.md`, `bluf.md`. ccir.md is the **document** of record. They must stay synchronized manually (see CONCERNS.md).

## Mapping code → architecture

| Code | Lives in | Job |
|---|---|---|
| `bridge/gmail_to_atom.py` | bridge/ | Gmail IMAP → Atom (single-account bridge) |
| `bridge/imap_to_atom.py` | bridge/ | Multi-IMAP → per-mailbox Atom feeds |
| `bridge/yt_to_atom.py` | bridge/ | YouTube channel → Atom w/ transcripts |
| `score/triage_score.py` | score/ | LLM scoring against ccir.md (item → ccir + cnr + score) |
| `score/fever_triage.py` | score/ | Fever pull + score + mark-skip-read + digest |
| `score/digest.py` | score/ | Windowed scoring (since-cutoff) → 4 writer modes |

## Notable design decisions (in code, not just docs)

- **Stdlib over deps.** Only one shipped dep (`feedgen`). Bridges hand-write Atom XML. Reason: lower supply-chain surface + easier audit.
- **Read-only posture by default.** Bridges use `IMAP4_SSL(login) + SELECT(readonly=True)`. No STORE / no EXPUNGE anywhere.
- **Secrets hygiene.** Plaintext in `.env` is gitignored. `.mailboxes.json` / `.yt_channels.json` are also gitignored. No credentials printed in error messages — length-only diagnostics in the probe scripts.
- **Norwegian + English hybrid.** Code identifiers in English; user-facing prose (prompts, CNR/SAB text, why-rationales) in Norwegian. Bilingual headings (`## PIR — Priority Intelligence Requirements`).
- **Contradiction reporting.** `write_bluf` instructs the LLM to disclose, not silently pick, when sources disagree.
- **Failure → stingy markdown.** LLM failures produce Norwegian placeholders in the digest; full detail goes to stderr. Allows LLM to fail without leaking env-var values from urllib error text.
