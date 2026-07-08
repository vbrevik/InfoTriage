## From 06-05 execution (2026-07-08)

- **tests/integration/test_clustering_integration.py** carries a hardcoded DSN
  `postgresql://infotriage:...@127.0.0.1:5432/infotriage` (container-internal port, NOT prod
  :22000 — guard does not trip) with no reachability skip guard. Errors on hosts with an
  unrelated local Postgres at 5432. Pre-existing; out of 06-05 scope. Consider migrating it
  to the INFOTRIAGE_TEST_DSN pattern in a follow-up.
- **tests/test_bus_consume.py / tests/test_bus_rabbitmq.py** — 4 failures against RabbitMQ
  :22001 (timeout / assertion). Pre-existing, unrelated to DSN safety work.
