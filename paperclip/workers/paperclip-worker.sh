#!/usr/bin/env bash
# Paperclip `process` adapter worker.
# Calls a local OpenAI-compatible model and writes the deliverable into cwd.
# Task/model/output are supplied via adapterConfig.env (LLM_BASE, LLM_MODEL, OUT_FILE, TASK_PROMPT).
# Reports back to Paperclip (comment + done) best-effort using injected PAPERCLIP_* env.
set -euo pipefail

: "${LLM_BASE:?LLM_BASE required}"
: "${LLM_MODEL:?LLM_MODEL required}"
: "${OUT_FILE:?OUT_FILE required}"
: "${TASK_PROMPT:?TASK_PROMPT required}"
LLM_KEY="${LLM_KEY:-omlx}"
MAX_TOKENS="${MAX_TOKENS:-8000}"

WORKDIR="$(pwd)"
OUT_PATH="$WORKDIR/$OUT_FILE"

prompt="$TASK_PROMPT"
# Qwen3.6 models default to <think>; /no_think gives a clean, deterministic answer.
[ "${NO_THINK:-1}" = "1" ] && prompt="$prompt /no_think"

echo "[worker] model=$LLM_MODEL base=$LLM_BASE cwd=$WORKDIR out=$OUT_PATH"

payload=$(LLM_MODEL="$LLM_MODEL" PROMPT="$prompt" MAX_TOKENS="$MAX_TOKENS" python3 - <<'PY'
import json, os
print(json.dumps({
    "model": os.environ["LLM_MODEL"],
    "messages": [{"role": "user", "content": os.environ["PROMPT"]}],
    "max_tokens": int(os.environ["MAX_TOKENS"]),
    "temperature": 0.4,
}))
PY
)

resp=$(curl -s -m 600 "$LLM_BASE/chat/completions" \
  -H "Authorization: Bearer $LLM_KEY" -H "Content-Type: application/json" \
  -d "$payload")

content=$(printf '%s' "$resp" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(d['choices'][0]['message'].get('content') or '')
")

if [ -z "$content" ]; then
  echo "[worker] ERROR: empty model response: $resp" >&2
  exit 1
fi

printf '%s\n' "$content" > "$OUT_PATH"
echo "[worker] wrote $OUT_PATH ($(wc -c < "$OUT_PATH") bytes)"

# ---- best-effort report to Paperclip (never fail the run on reporting errors) ----
report() {
  [ -n "${PAPERCLIP_API_URL:-}" ] && [ -n "${PAPERCLIP_API_KEY:-}" ] && [ -n "${PAPERCLIP_COMPANY_ID:-}" ] && [ -n "${PAPERCLIP_AGENT_ID:-}" ] || return 0
  local base="${PAPERCLIP_API_URL%/}"
  # find this agent's actionable issue
  local issue
  issue=$(curl -s -m 20 "$base/api/companies/$PAPERCLIP_COMPANY_ID/issues?assigneeAgentId=$PAPERCLIP_AGENT_ID" \
    -H "Authorization: Bearer $PAPERCLIP_API_KEY" 2>/dev/null | python3 -c "
import sys, json
try: d = json.load(sys.stdin)
except Exception: sys.exit(0)
its = d if isinstance(d, list) else d.get('items', d.get('issues', []))
act = [i for i in its if i.get('status') in ('todo','in_progress')]
print(act[0]['id'] if act else '')
" 2>/dev/null) || return 0
  [ -n "$issue" ] || return 0
  local body; body=$(printf 'Wrote deliverable to %s (%s bytes) using local model %s.' "$OUT_PATH" "$(wc -c < "$OUT_PATH" | tr -d ' ')" "$LLM_MODEL")
  curl -s -m 20 -X POST "$base/api/companies/$PAPERCLIP_COMPANY_ID/issues/$issue/comments" \
    -H "Authorization: Bearer $PAPERCLIP_API_KEY" -H "Content-Type: application/json" \
    -H "x-paperclip-run-id: $PAPERCLIP_RUN_ID" \
    -d "$(python3 -c "import json,os;print(json.dumps({'body':os.environ['B']}))" B="$body")" >/dev/null 2>&1 || true
  curl -s -m 20 -X PATCH "$base/api/companies/$PAPERCLIP_COMPANY_ID/issues/$issue" \
    -H "Authorization: Bearer $PAPERCLIP_API_KEY" -H "Content-Type: application/json" \
    -H "x-paperclip-run-id: $PAPERCLIP_RUN_ID" \
    -d '{"status":"done"}' >/dev/null 2>&1 || true
  echo "[worker] reported to issue $issue"
}
report || true
echo "[worker] done"
