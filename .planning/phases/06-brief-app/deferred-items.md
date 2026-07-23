## From 06-05 execution (2026-07-08)

- **tests/integration/test_clustering_integration.py** carries a hardcoded DSN
  `postgresql://infotriage:...@127.0.0.1:5432/infotriage` (container-internal port, NOT prod
  :22000 — guard does not trip) with no reachability skip guard. Errors on hosts with an
  unrelated local Postgres at 5432. Pre-existing; out of 06-05 scope. Consider migrating it
  to the INFOTRIAGE_TEST_DSN pattern in a follow-up.
  status: resolved — folded into ROADMAP backlog Phase 999.5 (2026-07-23 forensic audit)
- **tests/test_bus_consume.py / tests/test_bus_rabbitmq.py** — 4 failures against RabbitMQ
  :22001 (timeout / assertion). Pre-existing, unrelated to DSN safety work.
  status: resolved — folded into ROADMAP backlog Phase 999.5 (2026-07-23 forensic audit)

## From 06-07 execution (2026-07-11)

- **tests/test_bus_consume.py::test_consume_delivers_message** — still fails
  (`asyncio.exceptions.CancelledError`) in the full-suite run after 06-07's vault_writer.py
  fix. RabbitMQ live-consumer contention (q.triage/q.brief consumers eat test messages),
  unrelated to vault_writer.py/06-07 scope. Not fixed — out of scope per plan boundary
  (files_modified: apps/brief/vault_writer.py, tests/test_vault_writer.py only).
  status: resolved — folded into ROADMAP backlog Phase 999.5 (2026-07-23 forensic audit)
