# Technology Stack

**Analysis Date:** 2026-06-24

## Languages

**Primary:**
- Python 3.x - All bridge, score, and utility scripts

**Secondary:**
- Bash - Docker Compose orchestration and cron scheduling
- YAML - Docker Compose configuration
- Markdown - Configuration and documentation (ccir.md, README.md, opml feed definitions)

## Runtime

**Environment:**
- macOS (Apple Silicon primary, POSIX systems supported)
- Python 3.x (via `#!/usr/bin/env python3`)

**Package Manager:**
- pip with requirements.txt
- Lockfile: No (single-file requirements.txt)

## Frameworks & Libraries

**Core:**
- `feedgen` 1.0.0 - Atom XML feed generation (bridge output format)

**Standard Library (Python):**
- `imaplib` - IMAP email protocol (Gmail, multi-account)
- `email` - Email message parsing and header decoding
- `urllib` - HTTP client for API requests (LLM, Fever API)
- `json` - JSON parsing for configuration and API data
- `argparse` - CLI argument parsing
- `datetime`, `zoneinfo` - Timezone-aware scheduling and digest windows
- `hashlib` - MD5 for Fever API authentication
- `subprocess` - Child process execution (YouTube whisper transcription)
- `tempfile`, `shutil` - Temporary file handling
- `html` - XML/HTML escaping for feed safety
- `re`, `sys`, `os` - Text, system, and file operations

**Testing:**
- unittest / pytest (framework not explicitly configured, tests are present in `tests/`)

**Build/Dev:**
- Docker - Container runtime
- Docker Compose - Service orchestration

## External Services (Container-Based)

**Infrastructure:**
- FreshRSS (Docker image: `freshrss/freshrss:latest`) - RSS aggregator, stores feeds in SQLite, port 8088
- rss-bridge (Docker image: `rssbridge/rss-bridge:latest`) - Dynamic RSS generation from websites, port 3000
- Static File Server (Docker image: `halverneus/static-file-server:latest`) - Serves locally-generated feed files (e.g., Gmail Atom output), port 80 (internal network)

**Network:**
- Docker Compose network: `infotriage` - Local bridge network connecting containers

## Configuration

**Environment Variables:**
Located in `.env` (copy from `.env.example`):
- `LLM_BASE_URL` - LLM endpoint (default: `http://127.0.0.1:8000/v1` (oMLX fallback) or `192.168.10.2:8000/v1` (Spark primary))
- `LLM_API_KEY` - LLM authentication (default: `omlx` (oMLX) or `EMPTY` (Spark vLLM))
- `LLM_MODEL` - Model identifier (default: `qwen36-ud-4bit`)
- `GMAIL_APP_PASSWORD` - Google app password for IMAP (read-only)
- `GMAIL_QUERY` - Gmail search syntax (default: newsletters, 7 days)
- `GMAIL_USER` - Gmail address (for imap_to_atom.py)
- `MAILBOXES` - JSON array of IMAP mailbox configs (or `.mailboxes.json` file)
- `YT_CHANNELS` - JSON array of YouTube channels (or `.yt_channels.json` file)
- `FRESHRSS_FEVER_URL` - FreshRSS Fever API endpoint (e.g., `http://localhost:8088/api/fever.php`)
- `FRESHRSS_FEVER_USER` - Fever API username
- `FRESHRSS_FEVER_API_PASSWORD` - Fever API password

**Build Configuration:**
- `docker-compose.yml` - Service definitions (FreshRSS, rss-bridge, feeds server)
  - Location: `docker-compose.yml`
  - Services: freshrss, rssbridge, feeds
  - Networks: infotriage (internal bridge)
  - Volumes: `./data/freshrss`, `./data/rssbridge`, `./data/feeds` (persistent, host-mounted)

**Triage Configuration:**
- `ccir.md` - CCIR (Commander's Critical Information Requirements) - the triage interest profile loaded by `score/triage_score.py`
  - Defines scoring criteria and buckets (🔥 read / 🤔 maybe / 🗑️ skip)
  - Categories: tech, defense/geopolitics, Norway focus, world news
  - Used by `score/triage_score.py` and `score/digest.py` to bucket items

**OPML Feed Subscriptions:**
- `opml/feeds.opml` - ~45 curated RSS/Atom feeds (Norwegian + world + defense/geopolitics)
  - Includes GDELT, major news outlets, defense/security sources
  - Some feeds require rss-bridge workaround (no native RSS)

## Platform Requirements

**Development:**
- macOS with Python 3.x installed
- Docker & Docker Compose installed
- Optional: `mlx_whisper` (for YouTube audio transcription, Apple Silicon) or `whisper` (OpenAI, cross-platform)

**Production:**
- Docker runtime (local macOS machine)
- Python 3.x on host (for bridge scripts, not containerized)
- Local LLM server running (oMLX on `127.0.0.1:8000/v1` (fallback) or Spark vLLM on `192.168.10.2:8000/v1` (primary))
- Network access to:
  - Gmail IMAP (`imap.gmail.com`)
  - YouTube (for yt_to_atom.py)
  - External RSS sources (feed URLs)
  - GDELT, news outlets, etc.

## Key Design Decisions

**No Cloud:**
- All processing local (on-machine LLM scoring via oMLX/Ollama)
- No external SaaS dependencies
- Data stored locally in `./data/` (Docker volumes)

**Local-First Email:**
- IMAP bridges (not API-dependent on Gmail API keys, only app password)
- READ-ONLY operations to email sources (never sends/deletes)

**Container Isolation:**
- FreshRSS, rss-bridge, feeds server in Docker
- Bridge scripts (gmail_to_atom.py, imap_to_atom.py, yt_to_atom.py) run on host to access Gmail/YouTube directly
- Internal Docker network (`infotriage`) for service-to-service communication

**Feed Ingestion:**
- Three ingestion patterns:
  1. Native RSS/Atom (FreshRSS subscribes directly)
  2. Bridges (rss-bridge transforms websites to RSS)
  3. Email/YouTube (custom bridge scripts to Atom, served via static file server)

---

*Stack analysis: 2026-06-24*
