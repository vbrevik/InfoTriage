# ADR-016 — Airgap & Safety Doctrine: Local LLMs and Read-Only Ingest (supersedes ADR-004)

**Status.** Accepted (2026-07-23). Codifies the operative stance that has been
referenced across the InfoTriage codebase as "ADR-004" but for which no ADR-004
file was ever committed to `docs/adr/`. The original ADR-004 stand-in lifetime
covered Phases 0–11 (per ROADMAP/STATE.md/ARCHITECTURE.md/ADR-014 cross-references);
ADR-016 is its formal codification as of Phase 12 dispatch. **Historian's note:**
neither `ADR-004-*.md` nor any deletion log hit is recoverable; the stand-in was
operative cross-referenced but never committed.

All future references to "ADR-004" should be read as "ADR-016".

**This document formally resolves the missing-file blocker for ADR-015**, which
depends on local-only server definitions for the ntfy + qwen36 + ntfy-local-server
topology. ADR-015 can now progress from *Proposed* to *Accepted*.

---

## Context

Two architectural invariants have been operative since Phase 0 of the project
without a dedicated ADR file on disk:

1. **LLM/AI workloads must run on local hardware, never on cloud-mediated APIs.**
2. **Source ingestion must be strictly read-only across all sources.**

Both invariants are referenced extensively (ROADMAP overview, ARCHITECTURE.md
§188, ADR-014 Cross-Cutting §5, Gmail MCP `readonly` OAuth2 scope, IMAP/POP3
no-EXPUNGE enforcement, `llm-router.py` route-config whitelist of local models
only, docker-compose local-only qwen36 service) but have no canonical ADR file.
This is a documentation gap, not a behavior gap — the invariants are enforced
by code and reference. ADR-016 closes the documentation gap.

---

## Decision 1 — Local-first LLM (no cloud-mediated inference ever)

All LLM/AI workloads execute on local hardware. Specifically:

- **Triage scoring** (`apps/triage/triage_score.py`): qwen36-ud-4bit on Mac
  (MLX/Ollama) or NVIDIA DGX Spark (vLLM).
- **NER + entity linking** (`apps/triage/entities.py`): local qwen36 only.
- **Wiki-LLM synthesis** (`apps/wiki/generator.py`): local qwen36; DGX Spark
  optional for heavy synthesis per ADR-006.
- **BLUF generation** (`apps/brief/renderer.py::render_bluf`): local qwen36
  via `from triage_score import llm`.
- **On-demand translation** (`apps/brief/_i18n.py`): local qwen36 (per
  ADR-014 §4).
- **Recall / thematic synthesis** (`apps/triage/recall.py`): local qwen36;
  DGX optional.
- **YouTube transcription** (`apps/ingest-youtube`): local faster-whisper
  on Mac (per Wave 5 ship).
- **OCR / image transcription** (in-scope for future phases): local-only.

### Cloud-LLM exclusion list (always-disqualifying, even when not used)

OpenAI Chat Completions API, OpenAI Assistants, Anthropic Messages API,
Google Gemini API, Cohere, Mistral SaaS, OpenRouter proxied inference,
AWS Bedrock InvokeModel, Azure OpenAI endpoints, any cloud LLM service
mediated by vendor API key.

### Hardware platforms

- **Mac**: Ollama, MLX, llama.cpp, vLLM-on-Mac when available.
- **NVIDIA-stack**: DGX Spark (GB10 Grace Blackwell), CUDA 12.x → 13.x matrix
  documented in `ccir.md` §FFIR-3.
- **No server-class**: no GPU rentals, no spot-instance inference, no
  third-party hosted inference endpoints.
- **No telemetry.** Host tools (Ollama, vLLM, MLX) MUST have telemetry
  **disabled** (e.g., `OLLAMA_NOHISTORY=1`, vLLM telemetry off; no
  home-phone update checks). Otherwise the GDPR-friendly consequence
  breaks — the operator's prompts are still doing a round-trip
  regardless of whether the response is cloud-served.

### Routing enforcement

`apps/llm-router.py` is the operational chokepoint:

- Whitelist of allowed base URLs: `127.0.0.1:8000`, `127.0.0.1:11434` (Ollama),
  `host.docker.internal:8000` (compose→host), `DGX_ENDPOINT` (per `.env`).
- Default base URL: `http://127.0.0.1:8000/v1` (qwen36-ud-4bit).
- Pre-flight check rejects blocks trying to call `*.openai.com`,
  `api.anthropic.com`, `generativelanguage.googleapis.com`, etc. — emits
  structured-log warning + raises before any token spends.
- Test `tests/test_llm_router_offline_only.py` asserts the rejection.

### R4 citation trust model

LLM outputs that surface to the operator (BLUF, wiki synthesis, recall
summaries) must be auditable locally. Per the spike (Phase 00 R4), citation
grounding + verification happens on operator's local machine reading the
synthesized article against the underlying Postgres citations array.
Cloud-LLM makes this trust model impossible to audit (vendor-side chain).

---

## Decision 2 — Read-only ingest across all sources

All source ingestion MUST be strictly read-only:

- **IMAP** (`apps/ingest-imap`): no `DELE`, no `EXPUNGE`, no flag mutations.
  All read operations via UID-style commands.
- **POP3** (`apps/ingest-imap`): no `DELE`, no `QUIT`-with-delete payload.
  Read-only mailbox polling only.
- **Gmail via MCP** (`apps/ingest-gmail`): OAuth2 scope is `readonly` (NOT
  `readwrite`); `list_messages()` and `get_message()` calls only; no label
  mutations, no send, no trash.
- **Telegram** (`apps/ingest-telegram`): per ADR-014, public channels only, no
  user-automation, no sponsored-message interference, no LLM training on
  ingested text.
- **YouTube** (`apps/ingest-youtube`): yt-dlp read-only fetches; no comment
  posting, no like/dislike.
- **RSS / FreshRSS**: feed-pull is by definition read-only.
- **Obsidian vault** (`apps/ingest-obsidian`): reads `Vault/articles-inbox/`
  clip files; never writes to user vault (vault_writer is the operator-facing
  writer, not ingest).
- **BarentsWatch AIS** (`apps/ingest-barentswatch`): per ADR-014, NLOD-licensed
  pull; no upstream writes.
- **ACLED** (`apps/ingest-acled`): per ADR-014, license-gated; ingest only, no
  upstream.

### If read-only is impossible, the source is rejected

**If a source API makes read-only ingestion impossible** (e.g., requires
state-mutating sync endpoints or mandatory write-scopes to read the
operator's data), the source MUST be rejected. We do NOT compromise the
read-only rule for source acquisition.

*First operative firing of this rule.* Gmail App Passwords were hard-blocked
by 2SV (2026-06-29, `ROADMAP.md` Phase 4 §Success Criteria 3): the conventional
IMAP bridge required write-scope OAuth to read the operator's mailbox,
which violated the read-only rule. The survivable read-only shape was
self-hosted Gmail MCP (`apps/ingest-gmail`, ADR-014 §1 + §3) + dedicated
readonly OAuth2. This validates the rule's bite — not theoretical, but
forced-architectural at the project inflection point.

### Why read-only

- **Read-write to source systems is operationally dangerous.** A bug or
  misalignment could mark items read, delete items, or post on behalf of the
  operator.
- **Read-only is trivially auditable.** Operator can re-derive the operator's
  retrieved state at any time.
- **Read-only bridges legal/ToS concerns.** Most platforms (Gmail, Twitter,
  Archive.org) explicitly allow monitoring via read-only API; few allow
  automation even with permission.
- **Read-only satisfies MVP scope.** InfoTriage is a read-side tool; no
  operator action reverse-path exists in M1/M2/M3.

---

## Cross-cutting

- **The all-local-LLM rule is HARD.** No phase may revisit it. Operator-facing
  feature toggles do not exist. There is no "cloud fallback".
- **Read-only ingest is HARD.** Same rule. No exception per source. If
  impossible, source is rejected (Decision 2 §If read-only is impossible).
- **Both invariants are operational, not aspirational.** Code enforces;
  tests assert; cross-references assume the stance.

## Consequences

### Positive

- **Predictable runtime footprint.** No vendor lock-in; no rate limits
  imposed by cloud API providers; no surprise pricing.
- **Operator trust model sustainable.** Citation-grounding on a local
  machine against a Postgres citations array remains auditable.
- **Offline-capable deployment.** The stack can run on a plane, submarine,
  or field tent given local hardware + Postgres capability.
- **GDPR-friendly.** No telemetry, no prompts, no outputs transit through
  cloud boundaries.

### Negative

- **Throughput ceiling.** Inference speed bound to operator's local
  hardware. Mitigation already in-scope: DGX Spark upgrades for heavy
  synthesis (per Phase 6 + 10).
- **Operator-managed lifecycle.** qwen weights must be downloaded + updated
  independently; DGX stocks local weights; ntfy local-server is a separate
  Docker container (per ADR-015 §Decision 2). Operators must know to update.

## References

- `ROADMAP.md` overview — *«all-local-LLM rule (ADR-004) is never revisited by a phase»*
- `docs/ARCHITECTURE.md` §188 — local-first doctrine
- `docs/adr/ADR-014-socmint-legal-and-tos.md` Cross-Cutting §5 — local-only LLM + transcription enforcement
- `apps/llm-router.py` — operational chokepoint + route whitelist
- `docker-compose.yml` — local-only qwen36 + ntfy service definitions
- `apps/ingest-gmail/mcp_client.py` — readonly OAuth2 scope
- `apps/ingest-imap/imap_ingest.py` — no-EXPUNGE enforcement
- `tests/test_llm_router_offline_only.py` — router rejection assertion
- `docs/adr/ADR-015-cnr-alerting-channels-and-payload.md` §Open Items 1 — supersede invitation
