# STACK — trimail

Source of truth: `requirements.txt`, `docker-compose.yml`, `README.md`, code-level imports.
Generated: 2026-06-23.

## Language & runtime

- **Python 3**, stdlib-first. All scripts `#!/usr/bin/env python3`.
- Cross-platform: any host that runs Docker + Python 3.
- Apple Silicon is the *primary* target (mlx_whisper for transcription; qwen36 via oMLX).
- No compiled modules. No TypeScript / JS / Go.

## Declared Python deps

`requirements.txt` declares one shipped dep:

| Package | Why |
|---|---|
| `feedgen>=1.0` | Cleaner Atom XML for bridges. The bridges can hand-write Atom without it (and currently do), but feedgen is available for future authoring. |

Everything else is **Python stdlib**:

- HTTP / API: `urllib.request`, `urllib.parse`, `urllib.error`
- Email / IMAP: `imaplib`, `email`, `email.header.decode_header`
- XML parsing: `xml.etree.ElementTree` (used for OPML smoke-tests)
- Timezones: `zoneinfo.ZoneInfo("Europe/Oslo")`
- Serialization: `json`, `re`, `csv` (not currently used), `hashlib` (Fever key)

## External processes the host must install

| Tool | Used by | Notes |
|---|---|---|
| `yt-dlp` | `bridge/yt_to_atom.py` | Channel metadata + audio fetch. Operator-side install (`brew install yt-dlp` or `pipx install yt-dlp`). Not auto-installed. |
| `mlx_whisper` | YT transcript | Apple Silicon primary runner. |
| `whisper` (openai-whisper CLI) | YT transcript | Cross-platform fallback. |
| Docker + Compose | FreshRSS / rss-bridge / feeds | Must be running for any end-to-end flow. |

The bridges **do not** auto-install any of these — they fail loudly and tell the operator what's missing.

## Local LLM (runtime hot path)

- **qwen3.6**, currently `qwen36-ud-4bit`, exposed as an OpenAI-compatible `/v1/chat/completions` endpoint.
- Default endpoint: `http://127.0.0.1:8000/v1` (oMLX on Mac). Fallback: `http://127.0.0.1:11434/v1` (Ollama).
- Auth: bearer token (`omlx` for oMLX, `ollama` for Ollama).
- Client: stdlib `urllib`, no `openai` SDK dependency — see `score/triage_score.py:50`.
- **Hard architectural constraint (ADR-004)**: every LLM stage (collection pre-filter, scoring, SAB production, RAG recall) uses local qwen3.6. Cloud LLMs are not permitted in the runtime.

## Container services (docker-compose.yml)

| Service | Image | Port | Purpose |
|---|---|---|---|
| `freshrss` | `freshrss/freshrss:latest` | `:8088` | Aggregator + reader. Stores SQLite (legacy) or Postgres (future). Fever API for triage. |
| `rssbridge` | `rssbridge/rss-bridge:latest` | `:3000` | Sites without native RSS → RSS bridge (CSS-selector / XPathBridge). |
| `feeds` | `halverneus/static-file-server:latest` | (internal) | Serves `data/feeds/*.xml` to FreshRSS at `http://feeds/<name>.xml`. Read-only mount. |

All on user-defined compose network `trimail`. FreshRSS cron is `23,53` (twice-an-hour, off the :00 stampede — gentler on rate-limited sources like GDELT).

## Container services (planned, ADR-001 phase 0)

- **PostgreSQL 16 + pgvector** — single store replacing SQLite + `verdicts.jsonl`. FreshRSS re-pointed to it.
- **bge-m3** (multilingual embed) and possibly **mE5-large** — local embeddings via Ollama for semantic dedup (Phase 2).
- No separate vector service (Qdrant / Weaviate / Milvus) **unless** scale forces it.

## Secrets surface

| Var | Where loaded | Lifetime |
|---|---|---|
| `.env` | `load_dotenv()` in every bridge + digest/scorer. Gitignored. | Per-run; never persisted by trimail. |
| `.mailboxes.json` | `bridge/imap_to_atom.py`. Gitignored. | File-based; plaintext IMAP creds. |
| `.yt_channels.json` | `bridge/yt_to_atom.py`. Gitignored. | File-based; channel URLs only (no creds). |

YouTube needs **no** credentials — public-channel metadata via yt-dlp. **Do not add a YouTube account.**

## What we deliberately do NOT use

- Cloud LLMs (no OpenAI API key, no Anthropic key in `.env`).
- Twitter/X API (paid + no free RSS — see README "X / Twitter" status).
- A second database engine (Postgres absorbs vector + full-text + relational).
- A vector-DB product (pgvector handles our scale — see ARCHITECTURE.md).
- The `openai` Python SDK (we use `urllib` against any OpenAI-compatible endpoint; keeps deps at one).
- ACLED (EULA bars LLM training/dev on ACLED data — incompatible with our pipeline; see RESEARCH-REPORT.md finding 5).
