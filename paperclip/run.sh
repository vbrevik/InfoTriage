#!/usr/bin/env bash
# Start the InfoTriage-scoped Paperclip server (assumes seed.sh already ran).
set -euo pipefail
source "$(dirname "$0")/lib.sh"

if [ ! -f "$CONFIG" ]; then
  echo "No config at $CONFIG — run ./paperclip/seed.sh first." >&2
  exit 1
fi

echo "Starting Paperclip (data-dir=$DATA_DIR, port=$PORT)..."
exec $PC run --data-dir "$DATA_DIR"
