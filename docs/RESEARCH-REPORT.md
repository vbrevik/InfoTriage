# InfoTriage — Deep Research Report (2026-06-23)

Free, self-hosted, fully-local OSINT/all-source intelligence platform on a Mac with
local qwen3.6. Fact-checked: 23 sources → 100 claims → 25 verified (24 confirmed, 1
refuted, 3-vote adversarial). Builds on `ARCHITECTURE.md` (ADR-001..004).

## Bottom line
Adopt **World Monitor** as the map-fronted aggregation + COP core and keep the proven
**InfoTriage FreshRSS+qwen3.6** spike as the CCIR/CNR triage + SAB layer. Add event DBs and
SOCMINT as **modular collection plugins**, incrementally. TAK is a later doctrinal phase,
not the first step. **One load-bearing unknown must be tested before betting on World
Monitor** (below).

## Verified findings (confidence · citation)

1. **World Monitor — real local path.** AGPL-3.0-only (+ commercial dual-license),
   verbatim *"Local AI — run everything with Ollama, no API keys required"*, globe.gl/
   deck.gl map COP, 4-tier fallback (Ollama→Groq→OpenRouter→browser T5), air-gapped via
   Tauri (auto-discovers any OpenAI-compatible local server → points at qwen3.6/oMLX).
   *high* — github.com/koala73/worldmonitor.
2. **⚠️ World Monitor — the open risk.** README does **not** specify whether Ollama covers
   **CCIR scoring + SAB briefing** or only classification/summarization; provider choice is
   an availability fallback, not per-task. Local coverage is *inferable* (DeepWiki: "AI
   summarization entirely on local hardware") but **unconfirmed**. Whether a custom CCIR
   taxonomy + Norwegian sources inject into the local path is **the empirical test**. *high*.
3. **Taranis AI — full-cycle, local-LLM undocumented.** EUPL-1.2, collection→NLP→structured
   report→PDF, Docker/k8s self-host, ~657★, 16GB/4CPU/50GB GPU-free. No Ollama path in
   README → needs config-level verification. *high* — github.com/taranis-ai/taranis-ai.
4. **TAK/CloudTAK — doctrinal COP, but gated.** CloudTAK = AGPL-3.0 browser COP, self-host
   via Docker Compose (MinIO for S3) **but requires a separate running TAK Server + admin
   creds** — not standalone. `@tak-ps/node-cot` bidirectionally converts CoT XML/Protobuf ↔
   GeoJSON (the integration layer); reference ETLs (etl-adsbx ADS-B→CoT) prove the pattern.
   Full ETL assumes AWS Lambda → a local Mac COP needs custom local glue via node-cot.
   *high* — dfpc-coe/CloudTAK, node-cot.cloudtak.io. **→ Phase 3, not first step.**
5. **ACLED — legally encumbered, NOT free.** EULA (Jul 2025): scraping prohibited (API/
   platform only); commercial **and** government/multilateral need a **paid license** (free
   tier non-commercial only); §7 **bars training/developing AI/LLM on content** and mandates
   extraction-prevention controls — directly conflicts with a local-LLM pipeline. ACLED is
   the *only* source covering non-violent/sub-threshold events (protests, troop movements).
   *high* — acleddata.com/eula.
6. **UCDP GED + open GDELT = the free event baseline.** UCDP GED is free but only records
   events with ≥1 fatality. Open **GDELT Project** data (gdeltproject.org / BigQuery / AWS)
   is free — **not** gdeltcloud.com, which is a commercial metered service. *high/med*.
7. **Telegram via Telethon — feasible, account-bound.** `telegram_osint` (Telethon, Py3.10+)
   needs a **real account** (free API ID/hash from my.telegram.org); reads only what that
   account sees (no anonymous scrape); aggressive automation risks an account ban. Sanctioned
   path. *high* — DarkWebInformer/telegram_osint.
8. **Embeddings — bge-m3 or mE5-large for NO/EN/RU.** Both beat BM25 on most Russian datasets
   (avg **+15.9pp**, RusBEIR); Scandinavian Embedding Benchmark validates Norwegian (Bokmål+
   Nynorsk). Caveat: both weaken on long docs → **chunk**. *high* — arXiv:2504.12879, 2406.02396.
9. **Transcription — solved locally on Apple Silicon.** mlx-whisper / lightning-whisper-mlx
   (MLX, 4-bit; Small ~0.3GB, Medium ~0.7GB), ~10× faster than whisper.cpp; pairs with
   yt-dlp for YouTube. Fully on-device. *high*.
10. **Storage — Postgres+pgvector confirmed** as the single store, incl. hybrid vector +
    full-text (RRF). *high*.

## Refuted (do not rely on)
- "UCDP materially beats ACLED on sub-national quality (Eck Algeria audit, >50% ACLED
  miscoded)" — **did not survive verification** (1-2). Don't cite it.

## Not covered / caveats
- **Liveuamap, instagram_monitor (Instagram), Facebook** — no verified claims surfaced.
  Facebook is widely hostile to automated collection (no source to cite). Treat IG/FB as
  high-friction, low-priority.
- World Monitor star count + the AGPL "-only" (package.json) vs "or later" (LICENSE) nuance
  move fast — confirm before any commercial framing.
- ACLED clauses trend **more** restrictive; a defense deployment likely needs a paid
  public-sector license and still can't feed it to an LLM. Treat as out-of-scope unless licensed.

## Open questions (decision-gating)
1. **Does World Monitor's Ollama path do CCIR scoring + SAB briefing, or only
   classification?** Resolve by running it against the existing qwen3.6/oMLX endpoint. ← test first.
2. Can Taranis AI's bots/presenters be pointed at a local OpenAI-compatible endpoint via config?
3. Cheapest legally-clean event baseline: **open GDELT + UCDP GED only**, or budget an ACLED
   public-sector license for sub-threshold events?
4. Is a lighter self-contained map (World Monitor globe.gl/deck.gl, or MapLibre) enough as the
   primary COP, reserving TAK/CloudTAK for a later doctrinal-interoperability phase?

## Recommended sequencing (revises ADR-003 roadmap)
- **Step 0 (cheapest, highest-leverage):** spike World Monitor on the Mac, point it at
  qwen3.6/oMLX, and **answer Open-Q1** — does local Ollama drive scoring+briefing, and can
  CCIR + Norwegian sources inject? This one test decides adopt-WM vs extend-InfoTriage.
- **Keep** the InfoTriage FreshRSS+qwen3.6 spike as the working daily driver throughout.
- **Collection plugins, incremental:** open GDELT + UCDP GED (free, legal) → BarentsWatch AIS
  (Arctic) → Telegram (Telethon) → YouTube (yt-dlp + mlx-whisper). Defer IG/FB; ACLED only if licensed.
- **Storage:** Postgres + pgvector + bge-m3/mE5-large (chunked) — per ADR-001.
- **COP:** start with WM's globe/deck.gl (or MapLibre); **TAK/CloudTAK = Phase 3** doctrinal layer.
- **All LLM = local qwen3.6** (ADR-004), and it's a hard adopt-criterion for any tool.
