# REQUIREMENTS — InfoTriage

> Status legend. **`[LIVE]`** = in working spike today. **`[SPIKE]`** = partial / smoke-test only. **`[TARGET]`** = defined in `docs/ARCHITECTURE.md` or `docs/RESEARCH-REPORT.md`, not yet built. **`[GATED]`** = blocked on an open question.

Grouped by the **intelligence cycle** (ADR-003) so each requirement maps to a stage of `Direction → Collection → Processing → Analysis → Production → Dissemination`.

## Direction (CCIR + CNR)

| ID | Statement | Status | Source |
|---|---|---|---|
| D-1 | The triage brain lives in `ccir.md` (Markdown, human-editable) read verbatim by the scorer prompt | `[LIVE]` | score/triage_score.py |
| D-2 | CCIR taxonomy covers 5 PIRs + 3 FFIRs covering Russia/Ukraine, Nordics/Arktis, NATO, Hybrid/Cyber, Stormakter, Norge forsvar/politikk, egen tech | `[LIVE]` | ccir.md |
| D-3 | CNR has three tiers (CAT I 🚩 / CAT II 📋 / Routine) with explicit notification triggers | `[LIVE]` | ccir.md |
| D-4 | Source reliability scored per Admiralty A–F / 1–6 scale | `[TARGET]` | docs/ARCHITECTURE.md ADR-003 |
| D-5 | Editing `ccir.md` updates triage without code changes | `[SPIKE]` | the script reads `ccir.md` per run — unverified after a hot edit |

## Collection

| ID | Statement | Status | Source |
|---|---|---|---|
| C-1 | RSS feeds via FreshRSS subscription management (OPML import supported) | `[LIVE]` | docker-compose.yml, FreshRSS |
| C-2 | Sites w/o native RSS via rss-bridge at `:3000` (CSS-selector / XPathBridge) | `[LIVE]` | docker-compose.yml |
| C-3 | Gmail newsletters ingested via `bridge/gmail_to_atom.py` (READ-ONLY IMAP, X-GM-RAW query) and served to FreshRSS at `http://feeds/gmail.xml` | `[SPIKE]` | bridge/ + data/feeds/gmail.xml — written but untested |
| C-4 | Below 1 req / 5 s rate-limit compliance on rate-limited feeds (GDELT) | `[LIVE]` | docker-compose.yml CRON_MIN + README guidance |
| C-5 | Custom per-feed TTL on heavy feeds | `[LIVE]` | operator-tunable in FreshRSS UI |
| C-6 | Open GDELT + UCDP GED event-database ingestion | `[TARGET]` | docs/RESEARCH-REPORT.md §6 ("UCDP GED + open GDELT = the free event baseline"); ADR-003 names event DBs but does not endorse the pairing |
| C-7 | BarentsWatch Live AIS + ArcticInfo APIs (PIR-2) | `[TARGET]` | docs/ARCHITECTURE.md ADR-003 |
| C-8 | Telegram via Telethon (account-bound, sanitized path) | `[TARGET]` | docs/RESEARCH-REPORT.md §7 |
| C-9 | YouTube channels via yt-dlp + mlx-whisper transcription | `[SPIKE]` | apps/ingest/yt_to_atom.py (implemented — XML-gen + escaping verified); runtime pending `yt-dlp` + a transcribe backend — docs/RESEARCH-REPORT.md §9 |
| C-10 | Instagram / Facebook ingestion | `[OUT]` | docs/RESEARCH-REPORT.md — hostile to automation |
| C-11 | ACLED event DB | `[GATED]` | EULA §7 bars training/developing AI on content; conflict with ADR-004 |
| C-12 | X / Twitter ingestion | `[GATED]` | "skip for now or self-host Nitter as separate spike — fragile" |
| C-13 | **Multi-mailbox IMAP ingestion** (Outlook / Fastmail / ProtonMail / custom-domain); one runner, per-account provider dispatch (Gmail → `X-GM-RAW`; everything else → standard IMAP SEARCH) | `[SPIKE]` | apps/ingest/imap_to_atom.py (implemented — XML-gen + escaping verified); runtime pending creds per mailbox |
| C-14 | **Sites-via-rss-bridge** operational notes for Norwegian defense / policy sites without native RSS (Forsvarets forum, FFI, NUPI, UTSYN, High North News). Manual workflow via rss-bridge web UI; optional CLI driver deferred >5 sites | `[LIVE]` (notes) | bridge/RSS_BRIDGE_NOTES.md; cross-ref `opml/feeds.opml` no-native-RSS block |

## Processing

| ID | Statement | Status | Source |
|---|---|---|---|
| P-1 | Local qwen3.6 scoring on title + source + 500-char summary, returning `{ccir, cnr, score, why}` JSON | `[LIVE]` | score/triage_score.py |
| P-2 | Bucket derivation: `keep` if ccir≠none AND (cnr=`I` OR score≥7); `maybe` if ccir≠none AND lower; `skip` if ccir=none | `[LIVE]` | score/triage_score.py |
| P-3 | JSON parse extracts `{…}` substring and strips code fences | `[SPIKE]` | brittle to model formatting changes — fall back is `uleselig modell-svar` |
| P-4 | HTML stripping from Fever items (basic regex, loss of structure tolerated) | `[LIVE]` | score/fever_triage.py |
| P-5 | Multilingual embeddings (NO/EN/RU) via local bge-m3 or mE5-large | `[GATED]` | docs/RESEARCH-REPORT.md §8 — model choice (Q5) |
| P-6 | Long-doc chunking for embedding (both mE5 and bge-m3 weaken on long inputs) | `[TARGET]` | docs/RESEARCH-REPORT.md §8 |
| P-7 | Cross-language semantic dedup (replaces keyword-overlap clustering) | `[TARGET]` | docs/ARCHITECTURE.md Phase 2 |
| P-8 | Whisper transcription on MLX (small ~0.3 GB / medium ~0.7 GB) | `[TARGET]` | docs/RESEARCH-REPORT.md §9 |

## Analysis / Fusion

| ID | Statement | Status | Source |
|---|---|---|---|
| A-1 | CCIR pre-filter: cosine article↔CCIR-def embeddings before LLM scoring | `[TARGET]` | docs/ARCHITECTURE.md Phase 3 |
| A-2 | Event clustering: same story across outlets collapses to one cluster | `[SPIKE]` | keyword-overlap cluster() in score/digest.py — fails across languages |
| A-5 | PMESII operational domain tagging per item (Political/Military/Economic/Social/Information/Infrastructure) | `[LIVE]` | apps/triage/ — PMESII/TESSOC enrichment shipped in Phase 1.5 (`.planning/archive/phase-1.5-pmesii-enrichment/`) |
| A-3 | Entity / relationship knowledge graph (STIX2-flavored) | `[TARGET]` | docs/ARCHITECTURE.md ADR-003 — OpenCTI / MISP candidate |
| A-4 | Reliability-weighted scoring (Admiralty reliability × credibility × confidence) | `[TARGET]` | docs/ARCHITECTURE.md ADR-003 |

## Production

| ID | Statement | Status | Source |
|---|---|---|---|
| PR-1 | Tiered digest writer: `brief.md` (SAB), `cluster.md` (skimmable), `list.md` (strict ≥8) | `[LIVE]` | score/digest.py |
| PR-2 | SAB structure: CNR 🚩 first, then one section per CCIR, ~10 min read | `[LIVE]` | score/digest.py write_brief |
| PR-3 | Since-cutoff default = yesterday 16:00 Europe/Oslo; explicit `--since` or `--hours` override | `[LIVE]` | score/digest.py |
| PR-4 | Append-only score history → `data/verdicts.jsonl` | `[LIVE]` | score/digest.py persist |
| PR-5 | SAB writes only to `data/verdicts.jsonl` (no DB) | `[SPIKE]` | score/digest.py — to be replaced by `InfoTriage.enrichment` in Phase 1 |
| PR-6 | RAG-assisted SAB ("what do we know about X since date") | `[TARGET]` | docs/ARCHITECTURE.md Phase 4 |
| PR-7 | Equipment-friendly brief export (PDF / handoff to RAYVN-style downstream) | `[TARGET]` | docs/ARCHITECTURE.md ADR-003 |

## Dissemination

| ID | Statement | Status | Source |
|---|---|---|---|
| DI-1 | FreshRSS reader UI for keepers (without leaving the inbox) | `[LIVE]` | FreshRSS web UI `:8088` |
| DI-2 | Fever auto-mark-read of skip bucket keeps unread list clean | `[SPIKE]` | score/fever_triage.py --max — import surface **fixed 2026-06-23** via `PROFILE = CCIR` alias in `triage_score.py`; runtime smoke against FreshRSS+oMLX still pending before `[LIVE]` |
| DI-3 | `verdicts.jsonl` append-only trail | `[LIVE]` | data/verdicts.jsonl |
| DI-4 | CNR 🚩 elevated at the top of `brief.md` and `cluster.md` | `[LIVE]` | score/digest.py |
| DI-5 | Push notifications on CAT I (Signal / ntfy / similar) | `[TARGET]` | docs/ARCHITECTURE.md open Q |
| DI-6 | CoT markers emitted to TAK / CloudTAK | `[TARGET]` | docs/ARCHITECTURE.md ADR-003 (Phase 3+) |

## Navigation frame (COP)

| ID | Statement | Status | Source |
|---|---|---|---|
| N-1 | Map/globe-fronted COP displaying aggregated events | `[GATED]` | docs/ARCHITECTURE.md ADR-003 — adopt World Monitor IF Open-Q1 passes; else MapLibre fallback |
| N-2 | World Monitor base: globe.gl + deck.gl + 65 providers / 500+ feeds, Ollama-native | `[GATED]` | docs/RESEARCH-REPORT.md §1–2 |
| N-3 | Taranis AI base: collection→analysis→structured report→briefing (Postgres, Python) | `[GATED]` | docs/RESEARCH-REPORT.md §3 — Open-Q2 |
| N-4 | Norwegian Arctic/maritime overlay from BarentsWatch APIs | `[TARGET]` | docs/ARCHITECTURE.md ADR-003 |

## Cross-cutting / non-functional

| ID | Statement | Status | Source |
|---|---|---|---|
| NF-1 | All LLM stages use **local qwen3.6** (DGX Spark vLLM (primary); oMLX :8000/v1 (fallback)) — hard rule, ADR-004 | `[LIVE]` | score/triage_score.py llm() env contract |
| NF-2 | No paid services, no cloud LLM, no SaaS | `[LIVE]` | docker-compose + .env contract |
| NF-3 | One query surface in target state — Postgres with `InfoTriage.*` schema, pgvector | `[TARGET]` | ADR-001 |
| NF-4 | Read-only against all source systems (Gmail IMAP `readonly=True`) | `[LIVE]` | bridge/gmail_to_atom.py |
| NF-5 | Operator-tunable CCIR profile; the Python prompt never re-defines the taxonomy | `[LIVE]` | score/triage_score.py CCIR_PATH |
| NF-6 | `.env` is external / gitignored, never committed | `[LIVE]` | .gitignore |
| NF-7 | Docker stack reachable port-mapping (`:8088`, `:3000`) on localhost | `[LIVE]` | docker-compose.yml |
| NF-8 | Stdlib-first; `feedgen` is the only runtime dep | `[LIVE]` | requirements.txt |
| NF-9 | Reproducibility: pinned deps + a documented re-provision path | `[SPIKE]` | `feedgen>=1.0` is floating; re-provision README is current |
| NF-10 | Phase plans and ADRs preserved through the GSD scaffold — `docs/ARCHITECTURE.md` is the source of truth, `.planning/` mirrors structure | `[LIVE]` | this scaffold |

## Open-question references (don't lose these)

- **Q1** (World Monitor Ollama path = CCIR scoring + SAB?) → gates N-1, N-2
- **Q2** (Taranis AI local-LLM) → gates N-3
- **Q3** (ACLED license) → gates C-11
- **Q4** (FreshRSS migration strategy) → gates Phase 0/1 seam
- **Q5** (Embedding model choice) → gates P-5, P-7, A-1
</content>
