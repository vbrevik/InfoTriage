#!/usr/bin/env bash
# One-time (idempotent) setup of the InfoTriage-scoped Paperclip instance:
# onboard -> pin ports -> create company -> create worker agents from agents/*.json.
# Local-only: no external LLM provider, Spark primary + oMLX fallback.
set -euo pipefail
source "$(dirname "$0")/lib.sh"

WORKER="$PC_DIR/workers/paperclip-worker.sh"
chmod +x "$WORKER"

# 1. Onboard the scoped instance if it doesn't exist yet.
if [ ! -f "$CONFIG" ]; then
  echo "==> Onboarding scoped instance at $DATA_DIR (port $PORT)"
  PORT="$PORT" SERVE_UI=true $PC onboard -y --data-dir "$DATA_DIR" >/tmp/pc-seed-onboard.log 2>&1 &
  until health_ok || [ -f "$CONFIG" ]; do sleep 2; done
  sleep 3
  # stop the auto-started server so we can pin the Postgres port
  for p in "$PORT" 54329; do
    pid=$(lsof -nP -iTCP:"$p" -sTCP:LISTEN 2>/dev/null | awk 'NR>1{print $2}' | head -1)
    [ -n "${pid:-}" ] && kill "$pid" 2>/dev/null || true
  done
  sleep 2
  # pin embedded Postgres port into the 8500-8599 range
  python3 - "$CONFIG" "$PG_PORT" <<'PY'
import json,sys
cfg,port=sys.argv[1],int(sys.argv[2])
d=json.load(open(cfg)); d.setdefault("database",{})["embeddedPostgresPort"]=port
json.dump(d,open(cfg,"w"),indent=2)
print("  pinned embeddedPostgresPort ->",port)
PY
else
  echo "==> Instance already onboarded ($CONFIG)"
fi

# 2. Start the server (background) for API calls.
if ! health_ok; then
  echo "==> Starting server"
  $PC run --data-dir "$DATA_DIR" >/tmp/pc-seed-run.log 2>&1 &
  until health_ok; do sleep 2; done
fi
echo "==> Server healthy on http://127.0.0.1:$PORT"

# 3. Ensure a company exists.
CID="$(company_id)"
if [ -z "$CID" ]; then
  echo "==> Creating company 'InfoTriage'"
  CID="$(pc company create --name "InfoTriage" --json | jqf "d.get('id','')")"
fi
echo "==> Company: $CID"

# 4. Create worker agents from agents/*.json (skip if an agent of that name exists).
existing="$(pc agent list --company-id "$CID" --json | jqf "','.join(a.get('name','') for a in (d if isinstance(d,list) else d.get('items',[])))")"
for f in "$PC_DIR"/agents/*.json; do
  python3 - "$f" "$CID" "$WORKER" "$PC_DIR" "$existing" <<'PY' > /tmp/pc-agent-payload.json
import json,sys,os
f,cid,worker,pcdir,existing=sys.argv[1:6]
spec=json.load(open(f)); w=spec["worker"]
if spec["name"] in existing.split(","):
    print(""); sys.exit(0)
task=open(os.path.join(pcdir,w["task_file"])).read().strip()
cwd=os.path.join(pcdir,w["workspace"]); os.makedirs(cwd,exist_ok=True)
payload={
  "name":spec["name"],"role":spec.get("role","general"),"title":spec.get("title"),
  "adapterType":"process",
  "adapterConfig":{
    "command":worker,"cwd":cwd,"timeoutSec":int(w.get("timeout_sec",600)),
    "env":{"LLM_BASE":w["base"],"LLM_MODEL":w["model"],"LLM_KEY":w.get("key","omlx"),
           "OUT_FILE":w["out_file"],"NO_THINK":str(w.get("no_think","1")),
           "MAX_TOKENS":str(w.get("max_tokens","4000")),"TASK_PROMPT":task},
  },
}
print(json.dumps(payload))
PY
  payload="$(cat /tmp/pc-agent-payload.json)"
  if [ -z "$payload" ]; then echo "   - $(basename "$f"): already exists, skipped"; continue; fi
  name="$(printf '%s' "$payload" | jqf "d['name']")"
  id="$(pc agent create --company-id "$CID" --payload-json "$payload" --json | jqf "d.get('id','')")"
  echo "   + created agent '$name' ($id)"
done

echo
echo "Seed complete. UI: http://127.0.0.1:$PORT"
echo "Trigger a worker:  $PC agent heartbeat:invoke <agentId>"
