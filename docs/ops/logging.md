# InfoTriage — Structured Logging Ops

All containerized services emit structured JSON logs to **stdout** (captured by
Docker) and to a rotating file under `./data/logs/<service>.log`.

## Configuration

- `LOG_LEVEL` — `DEBUG`, `INFO` (default), `WARNING`, `ERROR`, `CRITICAL`.
  Set globally in `.env` or per-service via `docker-compose.yml`.
- `INFOTRIAGE_LOG_DIR` — override the log directory (default `/data/logs` inside
  containers, mapped to `./data/logs` on the host).

## Log locations

| Service | File on host |
|---|---|
| ingest-imap | `data/logs/ingest-imap.log` |
| ingest-youtube | `data/logs/ingest-youtube.log` |
| ingest-gmail | `data/logs/ingest-gmail.log` |
| ingest-obsidian | `data/logs/ingest-obsidian.log` |
| triage | `data/logs/triage.log` |
| brief | `data/logs/brief.log` |
| opml-health | `data/logs/opml-health.log` |
| scheduler | `data/logs/scheduler.log` |
| dlq-consumer | `data/logs/dlq-consumer.log` |

## Rotation

- Daily rotation at midnight UTC.
- 7 days of backups kept (`<service>.log.1`, `<service>.log.2`, ...).

## Querying logs with `jq`

```bash
# Tail JSON logs from a specific service
jq -R 'fromjson?' data/logs/brief.log

# Filter by log level
jq -R 'fromjson? | select(.level == "ERROR")' data/logs/triage.log

# Filter by logger name
jq -R 'fromjson? | select(.logger == "brief.main")' data/logs/brief.log

# Follow live container logs as JSON
docker compose logs -f brief | jq -R 'fromjson?'
```

## Per-service debug

Set `LOG_LEVEL=DEBUG` for a single service without affecting the rest:

```bash
# In .env or on the command line
LOG_LEVEL=DEBUG docker compose up -d triage
```

## Uvicorn access logs

FastAPI/uvicorn access logs remain plain text on stdout. Application logs
produced via the shared `setup_logging()` helper are JSON. This is a known
gap: a future iteration can supply a uvicorn logging config to make access
logs JSON as well.
