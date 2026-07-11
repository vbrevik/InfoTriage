# InfoTriage ops — quick commands for the containerized stack.
# Usage: make help | up | down | logs | status | restart | shell-<service> | seed | backfill | replay | test-safe | test-full | clean

COMPOSE := docker compose
# Directory of this Makefile (ops/), used to locate compose files regardless of
# where make is invoked from.
OPS_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
# Capture the absolute path of THIS Makefile at parse time so `$(MAKE) -f ...`
# sub-invocations can forward the -f flag explicitly. Make does NOT propagate
# -f via MAKEFLAGS by design, so recursive make without this would search for a
# top-level Makefile in the current directory and fail with
# `No rule to make target `test-full''. (Phase 7 07-03 bug-fix follow-up.)
OPS_MAKEFILE := $(abspath $(lastword $(MAKEFILE_LIST)))
ROOT_DIR := $(abspath $(OPS_DIR)/..)
SCRIPTS_DIR := $(ROOT_DIR)/scripts
SERVICES := freshrss rssbridge feeds postgres rabbitmq ingest-imap ingest-youtube ingest-gmail ingest-obsidian triage brief scheduler opml-health dlq-consumer

.PHONY: help up down logs status restart shell seed backfill replay test-safe test-full clean

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

# Phase 7 07-02 gap closure: shell-layer safety check before pytest runs that
# resolve db_live fixtures. Refuses to allow a DSN pointing at the prod host
# port (22000) or the default Postgres port (5432). Pairs with the in-Python
# tests/test_dsn_safety.py guard — belt-and-suspenders against an ambient
# prod-port DSN TRUNCATEing the live DB on a test run.
test-safe: ## Run scripts/check_test_dsn.sh first, then make test-full
	@bash $(SCRIPTS_DIR)/check_test_dsn.sh
	@echo "DSN smoke check passed; running full pytest..."
	$(MAKE) -f $(OPS_MAKEFILE) test-full

test-full: ## Run the full pytest suite against a throwaway test Postgres container
	$(COMPOSE) -f $(OPS_DIR)/../docker-compose.test.yml up -d --wait
	@trap '$(COMPOSE) -f $(OPS_DIR)/../docker-compose.test.yml down' EXIT; \
	cd $(OPS_DIR)/.. && \
	INFOTRIAGE_TEST_DSN=postgresql://test:test@localhost:22062/infotriage_test \
		python -m pytest tests/ -q

# Convenience targets for the three new gap-closure tests (operator-facing).
test-uvicorn-log: ## Run only the uvicorn log-config regression test
	cd $(OPS_DIR)/.. && python -m pytest tests/test_uvicorn_log_config.py -q

test-dlq-depth: ## Run only the DLQ depth-probe regression test
	cd $(OPS_DIR)/.. && python -m pytest tests/test_dlq_depth_probe.py -q

test-dsn-smoke: ## Run only the INFOTRIAGE_TEST_DSN shell-smoke regression test
	cd $(OPS_DIR)/.. && python -m pytest tests/test_check_test_dsn.py -q

clean: ## Stop and wipe all data (dangerous)
	$(COMPOSE) down -v
	@echo "All data volumes wiped."
