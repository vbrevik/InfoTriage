# STRUCTURE — InfoTriage

Source of truth: project root + `ls -R`.
Generated: 2026-06-23.

## Layout

```
InfoTriage/
├── README.md                  — spike overview, runbook, status table, bridge docs
├── ccir.md                    — Commander's Critical Information Requirements (the triage brain)
├── requirements.txt           — Python deps (one: feedgen)
├── docker-compose.yml         — freshrss + rssbridge + feeds
├── .env / .env.example        — secrets (gitignored)
├── .gitignore                 — .env, data/, __pycache__, .mailboxes.json, .yt_channels.json
│
├── opml/
│   └── feeds.opml             — 61 RSS URLs across 10 top-level outlines (verified 2026-06-23)
│
├── bridge/
│   ├── gmail_to_atom.py       — single-account Gmail IMAP → Atom feed
│   ├── imap_to_atom.py        — multi-mailbox IMAP → per-mailbox Atom feeds
│   └── yt_to_atom.py          — YouTube channel → Atom w/ transcripts (mlx_whisper / whisper)
│
├── score/
│   ├── triage_score.py        — LLM scorer (ccir.md-prompt + score_item/bucket derivation)
│   ├── fever_triage.py        — Fever pull + score + mark skip=read + kept digest
│   └── digest.py              — windowed scoring → 4 writer modes (cluster/brief/list/bluf)
│
├── docs/
│   ├── ARCHITECTURE.md        — ADR-001..004 + target architecture + research findings
│   └── RESEARCH-REPORT.md     — 23-source verification (fact-checked; 1 refuted claim)
│
└── .planning/
    ├── PROJECT.md
    ├── REQUIREMENTS.md
    └── codebase/
        ├── STACK.md           — language, deps, runtime (this map)
        ├── INTEGRATIONS.md    — per-service: endpoint, auth, code anchor, failure mode
        ├── ARCHITECTURE.md    — current vs target pipeline + LLM touch-points
        ├── STRUCTURE.md       — file inventory + per-purpose note (this file)
        ├── CONVENTIONS.md     — naming, OPML/code style, secret hygiene, output paths
        ├── TESTING.md         — current validation surface + gaps
        └── CONCERNS.md        — open gaps + drift risks + ordering + token cost
```

## Per-file purpose

### Top-level

- **README.md** — Operator-facing overview (state table), quickstart, env vars, bridge paths, GDELT/X etiquette, teardown. The first thing to read.
- **ccir.md** — The taxonomy: PIR-1..6, FFIR-1..3, SIR-1..2, CNR (CAT I/CAT II/Routine). Manually synced with `score/digest.py:CCIR_ORDER`. Advertised as "the triage brain"; sourced systemically by the scorer via prompt context.
- **requirements.txt** — Only declared dep is `feedgen>=1.0`. Everything else is Python stdlib.
- **docker-compose.yml** — Three services: FreshRSS (`:8088`), rss-bridge (`:3000`), feeds (static server for `data/feeds/*.xml`).
- **.env** / **.env.example** — `LLM_*` keys, `GMAIL_*`, `FRESHRSS_FEVER_*`, `MAILBOXES`, `YT_CHANNELS`. Gitignored.

### `opml/`

- **feeds.opml** — Hand-curated RSS bundle. Outlines: Norske aviser, Offentlig Norge, Norsk forsvar & sikkerhet, Forsvar & geopolitikk (intl), OSINT & investigations (intl), Verdensnyheter, Datakilder, Medium, **Midtøsten & US-Iran (SIR-1)**, **Sport — VM 2026 (SIR-2)**. ⚠️ suffix for feeds that 403 to bot UAs. Bottom-of-file comment block lists sites without native RSS (use rss-bridge for those).

### `bridge/`

- **gmail_to_atom.py** — Single Gmail account, IMAP `imap.gmail.com`, `X-GM-RAW`, **read-only**. Writes `data/feeds/gmail.xml`. Container-network-served at `http://feeds/gmail.xml`.
- **imap_to_atom.py** — Multi-mailbox: Gmail/Outlook/Fastmail/ProtonMail/custom. Provider-aware SEARCH (X-GM-RAW vs RFC 3501). **`MAILBOXES` env or `.mailboxes.json`**. Per-mailbox output file. Failure-tolerant (exit 0 if some succeed).
- **yt_to_atom.py** — YouTube channels: yt-dlp metadata + audio → mlx_whisper (primary) or whisper (fallback) → per-channel `data/feeds/youtube-<slug>.xml`. **No YouTube credentials.** Operator must install yt-dlp + one of mlx_whisper / whisper on the host.

### `score/`

- **triage_score.py** — Loads ccir.md into `CCIR`. The `llm()` stdlib client (urllib). `score_item(it)` returns `{ccir, cnr, score, why, bucket}`. Bucket logic: cc-ir none ⇒ `skip`; cnr=I or score≥7 ⇒ `read`; else `maybe`. CLI: `--sample`, `--file`, `--json`. Legacy `PROFILE` alias preserved for back-compat with README references.
- **fever_triage.py** — Pulls unread from FreshRSS (Fever API), scores each, marks skip=read (skipping the mark when `--dry-run`). `--max` caps items; `--skip-threshold` (default 3) overrides the bucket-derived skip. Kept list printed as a digest.
- **digest.py** — Four writers, one per `--mode`. All four iterate `CCIR_ORDER` (except for `cluster.md`'s flat layout). Window is `--since` (Oslo TZ) or `--hours` (rolling) or default yesterday-16:00. Hard cap on items scored (`--max`, default 400). BLUF mode adds `--bluf-top N` (per-CCIR cap, default 12).

### `docs/`

- **ARCHITECTURE.md** — Four ADRs (Postgres+pgvector adoption, prior-art review for Taranis AI, OSINT-all-source-frame reframe, hard constraint that all LLM work is local qwen3.6). Target architecture drawing. Three-archetype taxonomy of MAP-COP / intel-workflow / fusion-graph adoptions. Norwegian-context references (BarentsWatch, RAYVN).
- **RESEARCH-REPORT.md** — 23-source verification with adversarial 3-vote review; 1 refuted claim (the "ACLED > UCDP" cite). The single decision-gating open question: does World Monitor's Ollama path drive scoring+briefing, or only classification?

### `.planning/`

Operator and mapper artifacts.

- **PROJECT.md / REQUIREMENTS.md** — pre-existing requirements capture.
- **codebase/** — this map (7 docs).

## What lives in `data/` (gitignored)

Operator-managed runtime artifacts. Not in this map.

```
data/
├── freshrss/             — FreshRSS container data lake (SQLite/Postgres)
├── rssbridge/            — rss-bridge container config
├── feeds/                — Atom files produced by bridges
│   ├── gmail.xml         — produced by gmail_to_atom.py
│   ├── <name>.xml        — one per mailbox (imap_to_atom.py)
│   └── youtube-<slug>.xml — one per channel (yt_to_atom.py)
└── digests/
    ├── cluster.md        — produced by digest.py (default)
    ├── brief.md          — SAB
    ├── list.md           — strict score≥8
    └── bluf.md           — per-CCIR LLM-synthesized BLUF
```

Plus `data/verdicts.jsonl` (append-only scorer output, will be replaced by Postgres in Phase 1) and `data/triage.log` (run logs).
