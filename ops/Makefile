# InfoTriage ops — quick commands for the containerized stack.
# Usage: make up | logs | replay | backfill

COMPOSE := docker compose
# Directory of this Makefile (ops/), used to locate compose files regardless of
# where make is invoked from.
OPS_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
SERVICES := freshrss rssbridge feeds postgres rabbitmq ingest-imap ingest-youtube ingest-gmail ingest-obsidian triage brief scheduler opml-health

.PHONY: up logs replay backfill down test-full

# Start all services (detached)
up:
	$(COMPOSE) up -d --build

# Follow logs from all services
logs:
	$(COMPOSE) logs -f --tail=100

# Replay dead-letter queue messages back to original queues
# Usage: make replay  (replays all DLQ items)
#        make replay queue=<q.brief.dlx>  (replay specific queue)
replay:
	@rabbitmqadmin -u $${RABBITMQ_DEFAULT_USER:-infotriage} \
	  -p $${RABBITMQ_DEFAULT_PASS:-infotriage_rmq} \
	  -H 127.0.0.1 -P 22002 get queue=q.ops.dlx requeue=true exclusive=false count=1000 || \
	  echo "No DLQ messages to replay (or rabbitmqadmin not installed)"

# Backfill: re-run the full pipeline from ingest → triage → brief → SAB
# Usage: make backfill  (replays all ingest adapters)
backfill:
	@echo "Running full pipeline backfill..."
	$(COMPOSE) stop ingest-imap ingest-youtube ingest-gmail ingest-obsidian
	$(COMPOSE) up -d postgres rabbitmq
	@sleep 5
	$(COMPOSE) up -d ingest-imap ingest-youtube ingest-gmail ingest-obsidian
	@echo "Ingesters restarted. Monitor with: make logs"

# Stop all services (keeps data volumes)
down:
	$(COMPOSE) down

# Run the full pytest suite against a throwaway test Postgres container.
# Starts the container, waits for it to be healthy, runs tests, then tears it down.
test-full:
	$(COMPOSE) -f $(OPS_DIR)/../docker-compose.test.yml up -d --wait
	@trap '$(COMPOSE) -f $(OPS_DIR)/../docker-compose.test.yml down' EXIT; \
	cd $(OPS_DIR)/.. && \
	INFOTRIAGE_TEST_DSN=postgresql://test:test@localhost:22062/infotriage_test \
		python -m pytest tests/ -q

# Stop and wipe all data (dangerous)
clean:
	$(COMPOSE) down -v
	@echo "All data volumes wiped."
