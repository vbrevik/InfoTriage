# InfoTriage ops — quick commands for the containerized stack.
# Usage: make help | up | down | logs | status | restart | shell-<service> | seed | backfill | replay | test-full | clean

COMPOSE := docker compose
# Directory of this Makefile (ops/), used to locate compose files regardless of
# where make is invoked from.
OPS_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
ROOT_DIR := $(abspath $(OPS_DIR)/..)
SERVICES := freshrss rssbridge feeds postgres rabbitmq ingest-imap ingest-youtube ingest-gmail ingest-obsidian triage brief scheduler opml-health dlq-consumer

.PHONY: help up down logs status restart shell seed backfill replay test-full clean

help: ## Show this help message
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

up: ## Start all services (detached)
	$(COMPOSE) up -d --build

down: ## Stop all services (keeps data volumes)
	$(COMPOSE) down

logs: ## Follow logs from all services
	$(COMPOSE) logs -f --tail=100

status: ## Show container status and health
	@echo "=== docker compose ps ==="
	$(COMPOSE) ps
	@echo ""
	@echo "=== health checks ==="
	@printf "%-20s %s\n" "freshrss:" "$$(curl -sf http://127.0.0.1:8088/ >/dev/null 2>&1 && echo "up" || echo "down")"
	@printf "%-20s %s\n" "rssbridge:" "$$(curl -sf http://127.0.0.1:3000/ >/dev/null 2>&1 && echo "up" || echo "down")"
	@printf "%-20s %s\n" "feeds:" "$$(curl -sf http://127.0.0.1:22041/ >/dev/null 2>&1 && echo "up" || echo "down")"
	@for svc in $(SERVICES); do \
		if [ "$$svc" = "rssbridge" ] || [ "$$svc" = "feeds" ] || [ "$$svc" = "freshrss" ]; then \
			continue; \
		fi; \
		printf "%-20s" "$$svc:"; \
		case $$svc in \
			ingest-imap) port=22010 ;; \
			ingest-youtube) port=22011 ;; \
			ingest-gmail) port=22012 ;; \
			ingest-obsidian) port=22013 ;; \
			triage) port=22030 ;; \
			brief) port=22040 ;; \
			opml-health) port=22032 ;; \
			dlq-consumer) echo " n/a"; continue ;; \
			*) echo " unknown"; continue ;; \
		esac; \
		curl -sf http://127.0.0.1:$$port/health >/dev/null 2>&1 && echo " up" || echo " down"; \
	done

restart: ## Restart all services
	$(COMPOSE) restart

shell-%: ## Open a shell in the named container (e.g. make shell-triage)
	$(COMPOSE) exec $* /bin/sh

seed: ## Seed the database with sample articles
	@echo "Seeding pipeline with sample data..."
	python3 $(ROOT_DIR)/scripts/seed_sample_data.py

backfill: ## Re-run all ingest adapters
	@echo "Triggering all ingest adapters..."
	@for port in 22010 22011 22012 22013; do \
		name=$$(case $$port in \
			22010) echo "ingest-imap" ;; \
			22011) echo "ingest-youtube" ;; \
			22012) echo "ingest-gmail" ;; \
			22013) echo "ingest-obsidian" ;; \
		esac); \
		code=$$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:$$port/run 2>/dev/null || echo "000"); \
		case $$code in \
			200) echo "$$name triggered (200)" ;; \
			409) echo "$$name skipped — already running (409)" ;; \
			*) echo "$$name failed (HTTP $$code)" ;; \
		esac; \
	done

replay: ## Replay dead-letter queue messages back to original queues
	$(COMPOSE) exec dlq-consumer python worker.py --replay

test-full: ## Run the full pytest suite against a throwaway test Postgres container
	$(COMPOSE) -f $(OPS_DIR)/../docker-compose.test.yml up -d --wait
	@trap '$(COMPOSE) -f $(OPS_DIR)/../docker-compose.test.yml down' EXIT; \
	cd $(OPS_DIR)/.. && \
	INFOTRIAGE_TEST_DSN=postgresql://test:test@localhost:22062/infotriage_test \
		python -m pytest tests/ -q

clean: ## Stop and wipe all data (dangerous)
	$(COMPOSE) down -v
	@echo "All data volumes wiped."
