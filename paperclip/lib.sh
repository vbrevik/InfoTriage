#!/usr/bin/env bash
# Shared config + helpers for the InfoTriage-scoped Paperclip instance.
set -euo pipefail

PC_VERSION="${PC_VERSION:-0.3.1}"
PC="npx -y paperclipai@${PC_VERSION}"

# Repo root = parent of this paperclip/ dir
PC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$PC_DIR/.." && pwd)"

# Scoped, gitignored instance data (db, secrets, logs) lives under the repo.
export DATA_DIR="${DATA_DIR:-$REPO/.paperclip}"
CONFIG="$DATA_DIR/instances/default/config.json"

# Ports (kept in the 8500-8599 range, separate from InfoTriage docker services).
export PORT="${PORT:-8500}"
PG_PORT="${PG_PORT:-8501}"

# Strip npm noise from CLI output.
pc() { $PC "$@" 2>&1 | grep -vE 'EBADENGINE|npm warn|deprecated' || true; }

# JSON field via python (no jq dependency).
jqf() { python3 -c "import sys,json;d=json.load(sys.stdin);print($1)" 2>/dev/null || true; }

company_id() {
  pc company list --json | jqf "next((c['id'] for c in (d if isinstance(d,list) else d.get('items',[]))), '')"
}

health_ok() { curl -s -m 3 "http://127.0.0.1:$PORT/api/health" -o /dev/null 2>/dev/null; }
