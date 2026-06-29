---
phase: 03-bus-rabbitmq
plan: "01"
type: execute
wave: 1
depends_on: ["02-04"]
files_modified:
  - docker-compose.yml
  - libs/contracts/src/contracts/_bus_rabbitmq.py
  - libs/contracts/src/contracts/__init__.py
  - requirements-dev.txt
  - pyproject.toml
  - tests/test_bus_rabbitmq.py
autonomous: true
requirements: [ADR-007]
user_setup: []

must_haves:
  truths:
    - "RabbitMQ 3.13 container exposes ports 22001 (AMQP) and 22002 (management UI), joins infotriage network (R1)."
    - "aio-pika bus client implements BusClient Protocol with infotriage.events topic exchange, 4 routing keys, durable queues, DLX/DLQ (R2)."
    - "DLX infotriage.dlx declared before primary queues to avoid 406 PRECONDITION_FAILED (R2, context)."
    - "Publisher confirms work via channel.confirm_delivery(), requeue=False dead-lettering routes poison to infotriage.dlq (R2, R2.AC4)."
    - "End-to-end smoke test passes: publish/consume round-trip for all 4 event types (R3)."
  artifacts:
    - docker-compose.yml (added RabbitMQ service)
    - libs/contracts/src/contracts/_bus_rabbitmq.py
    - libs/contracts/src/contracts/__init__.py
    - requirements-dev.txt
    - pyproject.toml
    - tests/test_bus_rabbitmq.py
  key_links:
    - "aio-pika connect_robust() provides auto-reconnect on connection loss (R2, CONTEXT Rationale)."
    - "infotriage.events topic exchange + 4 routing keys (item.ingested, verdict.ready, sab.published, feed.unhealthy) bound to durable queues (R2, SPEC)."
    - "DLX infotriage.dlx declared first, then primary queues with x-dead-letter-exchange=infotriage.dlx (R2, context constraint)."
    - "x-dead-letter-routing-key=dead on primary queues routes nacked messages to infotriage.dlq (R2, SPEC)."
    - "RabbitMQ container healthcheck uses rabbitmq-diagnostics -q ping (RESEARCH Pattern 3)."
    - "pytest fixture uses docker-compose to bring up RabbitMQ container (RESEARCH Pattern 5 analog)."
  prohibitions:
    - statement: "MUST NOT change BusClient Protocol interface — only add new transport implementations."
      status: resolved
      verification: "_bus_rabbitmq.py implements BusClient Protocol via structural subtyping, no Protocol edits."
---

<objective>
Implement RabbitMQ AMQP transport for InfoTriage event bus. This plan builds the AMQP layer that Phase 2 PostgresStore will use to publish events and Phase 5/6 apps will consume. Key outputs: RabbitMQ 3.13 container on :22001/:22002, aio-pika BusClient implementation, end-to-end smoke test for all 4 event types.

Purpose: Phase 3 completes the messaging layer for the microservice architecture (ADR-006). The bus enables decoupled event-driven processing: ingest publishes item.ingested, triage consumes and publishes verdict.ready, brief consumes verdict.ready and publishes sab.published, ops health checks publish feed.unhealthy.

Output: docker-compose.yml with RabbitMQ service, libs/contracts/_bus_rabbitmq.py implementing BusClient via aio-pika, tests/test_bus_rabbitmq.py smoke test, all 4 routing keys and DLX/DLQ topology working.
</objective>

<execution_context>
@$HOME/.claude/gsd-core/workflows/execute-plan.md
@$HOME/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/03-bus-rabbitmq/03-SPEC.md
@.planning/phases/03-bus-rabbitmq/03-CONTEXT.md
@.planning/phases/02-storage-postgres-blobs/02-01-PLAN.md (analog for package scaffold)
@.planning/phases/02-storage-postgres-blobs/02-03-PLAN.md (analog for live integration test)
@.planning/phases/00-concept-spike/findings/R2-VERDICT.md (RabbitMQ topology validation)
@libs/contracts/src/contracts/_bus.py (BusClient Protocol — the contract this transport must satisfy)
</context>

<tasks>

<task type="auto">
  <name>Task 1: Add RabbitMQ 3.13 container to docker-compose.yml on ports 22001/22002</name>
  <read_first>
    - docker-compose.yml (existing services: freshrss, rssbridge, feeds, postgres)
    - 03-CONTEXT.md "Decisions: Container image: rabbitmq:3.13-management"
    - 03-SPEC.md R1 acceptance: management UI at localhost:22002 returns HTTP 200
    - RESEARCH Pattern 3 (healthcheck), Pattern 5 (docker-compose test fixture)
  </read_first>
  <files>docker-compose.yml</files>
  <action>
    Append a new `rabbitmq` service to docker-compose.yml, joining the `infotriage` network:

    ```yaml
    rabbitmq:
      image: rabbitmq:3.13-management
      container_name: infotriage-rabbitmq
      restart: unless-stopped
      ports:
        - "127.0.0.1:22001:5672"    # AMQP (localhost-only)
        - "127.0.0.1:22002:15672"   # management UI
      environment:
        RABBITMQ_DEFAULT_USER: infotriage
        RABBITMQ_DEFAULT_PASS: infotriage_dev
      volumes:
        - ./data/rabbitmq:/var/lib/rabbitmq
      healthcheck:
        test: ["CMD-SHELL", "rabbitmq-diagnostics -q ping"]
        interval: 10s
        timeout: 5s
        retries: 5
      networks: [infotriage]
    ```

    Key decisions:
    - Image: `rabbitmq:3.13-management` (management plugin enabled, per CONTEXT decision)
    - Ports: 22001 (AMQP) and 22002 (management) — localhost-only for security
    - Credentials: dev-only `infotriage/infotriage_dev` (production loads from `.env` via `INFOTRIAGE_AMQP_DSN`)
    - Healthcheck: `rabbitmq-diagnostics -q ping` (RESEARCH Pattern 3)
    - Data persistence: `./data/rabbitmq` volume
  </action>
  <verify>
    <automated>docker compose config >/dev/null 2>&1 && python3 - <<'PY'
import subprocess, json
out = subprocess.check_output(["docker","compose","config","--format","json"]).decode()
cfg = json.loads(out)
svc = cfg["services"]["rabbitmq"]
assert svc["image"] == "rabbitmq:3.13-management", svc.get("image")
ports = svc.get("ports", [])
assert any(str(p.get("published")) == "22001" and str(p.get("target")) == "5672" for p in ports), ports
assert any(str(p.get("published")) == "22002" and str(p.get("target")) == "15672" for p in ports), ports
assert svc.get("healthcheck", {}).get("test"), "healthcheck missing"
print("compose rabbitmq ok")
PY</automated>
  </verify>
  <acceptance_criteria>
    - `docker compose config` validates with no error
    - RabbitMQ service uses `rabbitmq:3.13-management` image
    - Port 22001 maps 5672 (AMQP), 22002 maps 15672 (management)
    - Healthcheck configured via rabbitmq-diagnostics
    - Service joins `infotriage` network
    - No real secrets committed (dev-only credentials documented)
  </acceptance_criteria>
</task>

<task type="auto">
  <name>Task 2: Implement aio-pika BusClient in libs/contracts/src/contracts/_bus_rabbitmq.py</name>
  <read_first>
    - libs/contracts/src/contracts/_bus.py (BusClient Protocol definition — DO NOT MODIFY)
    - 03-CONTEXT.md "Transport library choice: aio-pika over pika"
    - 03-CONTEXT.md "Connection management: connect_robust()"
    - 03-CONTEXT.md "Publisher confirms and dead-lettering"
    - 03-CONTEXT.md "Topology: infotriage.events (topic) + 4 queues + infotriage.dlx + infotriage.dlq"
    - RESEARCH Pattern 4 (aio-pika connection, channel, exchange, queue)
  </read_first>
  <files>libs/contracts/src/contracts/_bus_rabbitmq.py</files>
  <behavior>
    - BusClient Protocol methods: publish(routing_key, item_id, payload) → None, subscribe(routing_key) → list[dict]
    - Connects via aio_pika.connect_robust() for auto-reconnect
    - Declares infotriage.events (topic, durable) + infotriage.dlx (direct, durable) first
    - Declares 4 queues (q.triage, q.brief, q.notify, q.ops) with x-dead-letter-exchange=infotriage.dlx
    - Declares infotriage.dlq bound to DLX with routing key "dead"
    - Publisher confirms enabled via channel.confirm_delivery()
    - Publish uses mandatory=True + requeue=False for dead-lettering
    - Consume uses exclusive=False, auto_ack=False, prefetch_count=10
    - Dedup: keyed on (routing_key, item_id) matching InMemoryBus behavior
    - Reconnect: on connection failure, attempt reconnect with exponential backoff (max 30s)
  </behavior>
  <action>
    Author `libs/contracts/src/contracts/_bus_rabbitmq.py` with class `RabbitMQBus` implementing BusClient Protocol via aio-pika.

    **Key implementation details:**

    1. **__init__(self, dsn="amqp://localhost:22001", exchange_name="infotriage.events", dlx_name="infotriage.dlx")**:
       - Stores DSN, exchange names, preconnect state
       - Connection and channel are lazy-initialized on first publish/subscribe

    2. **connect_robust()** (internal):
       - Uses `aio_pika.connect_robust(self._dsn, on_connection_callback=self._on_connect)`
       - Exponential backoff reconnect: `min(2**attempts * 0.1, 30)` seconds
       - Registers connection callbacks for automatic channel exchange/queue declaration

    3. **_declare_topology()** (internal, run once on connect):
       - Declares `infotriage.events` (topic, durable=True, auto_delete=False)
       - Declares `infotriage.dlx` (direct, durable=True, auto_delete=False)
       - Declares 4 queues with dead-letter config:
         - `q.triage` → routing keys `item.ingested`
         - `q.brief` → routing keys `verdict.ready`
         - `q.notify` → routing keys `sab.published`
         - `q.ops` → routing keys `feed.unhealthy`
       - Declares `infotriage.dlq` bound to DLX with routing key "dead"

    4. **publish(self, routing_key, item_id, payload)**:
       - Compute message key = (routing_key, item_id)
       - Check _seen set, return early if duplicate (dedup)
       - Mark as seen, publish via `channel.publish()` with:
         - routing_key=routing_key
         - body=json.dumps(payload)
         - mandatory=True (triggers return if unroutable)
         - Requeue=False on Nack via callback

    5. **subscribe(self, routing_key)**:
       - Create exclusive queue for consumer (or use existing)
       - Consume with auto_ack=False, prefetch=10
       - Return list of deserialized messages
       - Manual ack after processing (future Phase 5/6 app responsibility)

    6. **__enter__ / __exit__** (context manager):
       - __enter__: connect and declare topology
       - __exit__: close connection gracefully

    **No changes to BusClient Protocol** — use structural subtyping (isinstance check via runtime_checkable).
  </action>
  <verify>
    <automated>python -c "from contracts import BusClient, InMemoryBus, RabbitMQBus; from pathlib import Path; import asyncio; assert isinstance(InMemoryBus(), BusClient); print('Protocol match ok')"</automated>
  </verify>
  <acceptance_criteria>
    - `RabbitMQBus` satisfies `isinstance(bus, BusClient)` via structural subtyping
    - `connect_robust()` auto-reconnects on connection loss with exponential backoff
    - DLX declared before primary queues (prevents 406)
    - 4 routing keys mapped to 4 queues
    - Publisher confirms via channel.confirm_delivery()
    - requeue=False dead-lettering routes poison to infotriage.dlq
    - Dedup keyed on (routing_key, item_id), same as InMemoryBus
  </acceptance_criteria>
</task>

<task type="auto">
  <name>Task 3: Export RabbitMQBus in libs/contracts/src/contracts/__init__.py</name>
  <read_first>
    - libs/contracts/src/contracts/__init__.py (current exports)
    - RESEARCH Pattern 1 (module exports)
  </read_first>
  <files>libs/contracts/src/contracts/__init__.py</files>
  <action>
    Add `RabbitMQBus` to the imports and __all__:

    ```python
    from ._bus_rabbitmq import RabbitMQBus
    __all__ = [
        "Item",
        "ItemIngested",
        "VerdictReady",
        "SabPublished",
        "FeedUnhealthy",
        "to_frontmatter",
        "from_frontmatter",
        "BusClient",
        "InMemoryBus",
        "RabbitMQBus",  # NEW
    ]
    ```

    This makes `RabbitMQBus` available via `from contracts import RabbitMQBus`.
  </action>
  <verify>
    <automated>python -c "from contracts import RabbitMQBus; assert RabbitMQBus is not None"</automated>
  </verify>
  <acceptance_criteria>
    - `from contracts import RabbitMQBus` succeeds
    - `RabbitMQBus` appears in `__all__` exports
    - No changes to existing exports (BusClient, InMemoryBus, events, codec)
  </acceptance_criteria>
</task>

<task type="auto">
  <name>Task 4: Add aio-pika dependency to requirements-dev.txt</name>
  <read_first>
    - requirements-dev.txt (current: -e ./libs/contracts, pytest>=8.0)
    - RESEARCH Environment Availability (aio-pika>=9.0, PyYAML)
  </read_first>
  <files>requirements-dev.txt</files>
  <action>
    Add aio-pika dependency after the existing lines:

    ```
    -e ./libs/contracts
    -e ./libs/store
    aio-pika>=9.0
    pytest>=8.0
    ```

    aio-pika includes PyYAML as a dependency, so no explicit PyYAML line needed.
  </action>
  <verify>
    <automated>pip install -e ./libs/contracts aio-pika>=9.0 >/dev/null 2>&1 && python -c "import aio_pika; assert aio_pika.__version__ >= '9.0'"</automated>
  </verify>
  <acceptance_criteria>
    - `pip install -e ./libs/contracts aio-pika>=9.0` succeeds
    - `import aio_pika` works without errors
    - Version >= 9.0 confirmed
  </acceptance_criteria>
</task>

<task type="auto">
  <name>Task 5: Register rabbitmq pytest marker in pyproject.toml</name>
  <read_first>
    - pyproject.toml (current: [tool.pytest.ini_options] with markers)
    - RESEARCH Pattern 6 (pytest marker for db_live)
  </read_first>
  <files>pyproject.toml</files>
  <action>
    Extend the existing markers array to add the rabbitmq marker:

    ```toml
    [tool.pytest.ini_options]
    testpaths = ["tests"]
    pythonpath = ["apps/triage", "apps/opml", "apps/ingest"]
    markers = [
        "db_live: requires Postgres :22000 to be running",
        "rabbitmq: requires RabbitMQ :22001 to be running",
    ]
    ```

    This allows `@pytest.mark.rabbitmq` to be used on integration tests.
  </action>
  <verify>
    <automated>grep -q 'rabbitmq' pyproject.toml</automated>
  </verify>
  <acceptance_criteria>
    - pyproject.toml markers array includes rabbitmq marker
    - Marker description: "requires RabbitMQ :22001 to be running"
  </acceptance_criteria>
</task>

<task type="auto">
  <name>Task 6: Write end-to-end smoke test tests/test_bus_rabbitmq.py</name>
  <read_first>
    - 03-SPEC.md R3 requirements (publish/consume round-trip for all 4 event types)
    - RESEARCH Pattern 5 (pytest fixture with docker-compose)
    - RESEARCH Pattern 7 (poison message → DLQ verification)
    - libs/contracts/src/contracts/_events.py (ItemIngested, VerdictReady, SabPublished, FeedUnhealthy)
    - libs/contracts/src/contracts/_item.py (Item schema)
  </read_first>
  <files>tests/test_bus_rabbitmq.py</files>
  <behavior>
    - test_publish_consume_roundtrip: Publish all 4 event types via RabbitMQBus, consume from each queue, verify payload matches
    - test_dedup: Same (routing_key, item_id) re-publish is no-op (dedup)
    - test_dlq_poison: NACK message with requeue=False → appears in infotriage.dlq within 5s
    - test_rabbitmq_available: Container healthcheck passes before test runs
    - All tests marked with @pytest.mark.rabbitmq
    - Fixture uses docker-compose up/down for RabbitMQ container (same pattern as Phase 2)
  </behavior>
  <action>
    Author `tests/test_bus_rabbitmq.py` with four test functions:

    **test_rabbitmq_available(pytestconfig)**:
    - Check if :22001 is reachable (socket pre-check, skip if unreachable)
    - `docker compose up -d rabbitmq` if not running
    - Wait for healthcheck via `docker compose ps rabbitmq | grep healthy`
    - Mark test as passed if reachable

    **test_publish_consume_roundtrip** (main R3 verification):
    - Fixture starts RabbitMQ container if not running
    - Create `RabbitMQBus(dsn="amqp://localhost:22001")` as context manager
    - For each of 4 event types (item.ingested, verdict.ready, sab.published, feed.unhealthy):
      - Build test payload from event schema
      - Publish with `bus.publish(routing_key, item_id, payload)`
      - Consume from the corresponding queue (q.triage, q.brief, q.notify, q.ops)
      - Assert payload matches original
    - Verify no exceptions or UnroutableError/NackError

    **test_dedup**:
    - Publish same (routing_key, item_id) twice
    - Consume should return only 1 message (dedup)
    - Verify via `bus.subscribe(routing_key)` returns single item

    **test_dlq_poison** (dead-lettering verification):
    - Publish a message to infotriage.events
    - Consume via RabbitMQBus, NACK with requeue=False
    - Wait up to 5 seconds for message to appear in infotriage.dlq
    - Verify DLQ contains the expected payload (routing_key=dead)

    **Consume strategy**:
    - Use exclusive queue for each test to avoid cross-test contamination
    - Set auto_ack=False, manual ack only after assertions
    - Use short timeout (3s) on consume to fail fast
  </action>
  <verify>
    <automated>pytest tests/test_bus_rabbitmq.py -v -m rabbitmq --tb=short 2>&1 | head -100</automated>
  </verify>
  <acceptance_criteria>
    - All 4 event types publish/consume successfully (roundtrip test passes)
    - Dedup works: re-publish of same (routing_key, item_id) yields single message
    - Dead-lettering works: NACK with requeue=False routes to infotriage.dlq within 5s
    - All tests marked with @pytest.mark.rabbitmq
    - Tests skip gracefully when :22001 is unreachable (no False positives)
  </acceptance_criteria>
</task>

<task type="auto">
  <name>Task 7: Verify full test suite passes with RabbitMQ (no regressions)</name>
  <read_first>
    - 03-SPEC.md Boundaries (Port 22000-22099 band, no conflict with Phase 2 Postgres on 22000)
    - RESEARCH Pattern 8 (full suite green)
  </read_first>
  <files>tests/</files>
  <action>
    Run full pytest suite twice:
    - `pytest tests/ -q -k "not db_live and not rabbitmq"` — existing tests, no DB/RabbitMQ
    - `pytest tests/ -q -m rabbitmq` — RabbitMQ integration tests

    Verify:
    - All existing 87 tests still pass (no regressions)
    - New RabbitMQ tests pass (8 new tests: 4 main + 4 infrastructure)
    - Integration tests auto-skip when :22001 is unreachable (no false failures)
  </action>
  <verify>
    <automated>pytest tests/ -q -k "not db_live and not rabbitmq" && pytest tests/ -q -m rabbitmq</automated>
  </verify>
  <acceptance_criteria>
    - Full suite with no services: 87 tests pass (no regressions)
    - RabbitMQ suite: 8 tests pass (roundtrip, dedup, DLQ, availability)
    - Tests auto-skip when :22001 unreachable (no False failures)
    - No new warnings or deprecation notices introduced
  </acceptance_criteria>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| caller → RabbitMQ | DSN from INFOTRIAGE_AMQP_DSN (not .env in code) |
| app → RabbitMQ | Event payloads cross into AMQP messages (json-serialized dict) |
| RabbitMQ → app | Consumed messages decoded from JSON, validated against event schemas |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-03-01 | Tampering | DSN handling in RabbitMQBus | high | mitigate | DSN read from caller env (INFOTRIAGE_AMQP_DSN), never hard-coded; never logged |
| T-03-02 | Tampering | AMQP message injection | medium | accept | JSON serialization; event schemas validated in Phase 5/6 consumers |
| T-03-03 | Denial of Service | RabbitMQ connection flood | low | mitigate | connect_robust() backoff limits reconnect rate (max 30s); caller can implement circuit breaker |
| T-03-SC | Tampering | aio-pika binary wheels | high | mitigate | Pinned official package (aio-pika>=9.0) via RESEARCH Package Legitimacy Audit (disposition Approved) |
</threat_model>

<verification>
- `docker compose config` validates with RabbitMQ service defined
- `docker compose up -d rabbitmq` starts container on :22001/:22002
- `python -c "from contracts import RabbitMQBus; assert isinstance(RabbitMQBus(), BusClient)"` passes
- `pytest tests/test_bus_rabbitmq.py -v` passes (all 4 event types roundtrip)
- `pytest tests/ -q` green: 87 existing + 8 new = 95 total
</verification>

<success_criteria>
- RabbitMQ 3.13 container exposes ports 22001 (AMQP) and 22002 (management UI)
- aio-pika BusClient implements BusClient Protocol with infotriage.events topic exchange, 4 routing keys, durable queues, DLX/DLQ
- Publisher confirms work: publish to any routing key returns without error (no NackError/UnroutableError)
- Dead-lettering works: nacking with requeue=False routes message to infotriage.dlq within 5 seconds
- End-to-end smoke test passes: publish/consume round-trip succeeds for all 4 event types
- Full suite green: 87 existing + 8 new tests
</success_criteria>

<output>
Create `.planning/phases/03-bus-rabbitmq/03-01-SUMMARY.md` when done.
</output>
