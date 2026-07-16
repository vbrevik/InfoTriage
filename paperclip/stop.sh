#!/usr/bin/env bash
# Stop the scoped Paperclip server + embedded Postgres for this instance.
set -euo pipefail
source "$(dirname "$0")/lib.sh"

for p in "$PORT" "$PG_PORT"; do
  pid=$(lsof -nP -iTCP:"$p" -sTCP:LISTEN 2>/dev/null | awk 'NR>1{print $2}' | head -1)
  [ -n "${pid:-}" ] && kill "$pid" 2>/dev/null && echo "stopped listener on :$p (pid $pid)"
done
echo "done"
