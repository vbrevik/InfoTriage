# Phase 3: Bus — RabbitMQ — Implementation Context

**Status:** Ready to plan
**Reference:** SPEC.md — 3 locked requirements

## Decisions

### Transport library choice: aio-pika over pika

**Decision:** Use `aio-pika` (asyncio-based) instead of `pika` (blocking) for production.

**Rationale:** Phase 0 R1 used `pika==1.4.1` with `BlockingConnection` for proof-of-concept, but this is unsuitable for a long-running service. Production needs async with `connect_robust()` auto-reconnect capabilities. `aio-pika` provides:
- Async/await pattern for non-blocking I/O
- Automatic reconnection on connection loss
- Consumer callbacks for event-driven processing
- Better integration with Python asyncio ecosystem

**Constraint:** BusClient Protocol interface must not change; only transport implementation differs.

### Exchange and queue topology (from ADR-007)

**Decision:** Implement the topology proven in Phase 0 R1:
- Main exchange: `infotriage.events` (topic, durable)
- Routing keys:
  - `item.ingested` → `q.triage`
  - `verdict.ready` → `q.brief`
  - `sab.published` → `q.notify`
  - `feed.unhealthy` → `q.ops`
- DLX: `infotriage.dlx` (direct, durable)
- DLQ: `infotriage.dlq` (durable, bound to DLX with routing key `dead`)
- Primary queues declared with `x-dead-letter-exchange=infotriage.dlx`

**Constraint:** DLX must be declared before primary queues to avoid `406 PRECONDITION_FAILED`.

### Connection management: `connect_robust()`

**Decision:** Use `aio_pika.connect_robust()` for persistent connections with auto-reconnect.

**Rationale:** Long-running services must handle connection loss (RabbitMQ restarts, network issues). `connect_robust()` maintains connection state and automatically reconnects on failure, unlike `connect()` which is a one-shot connection.

### Publisher confirms and dead-lettering

**Decision:** Enable publisher confirms and implement `requeue=False` dead-lettering:
- Publisher confirms via `channel.confirm_delivery()`
- Poison messages nacked with `requeue=False` route to DLQ atomically

**Constraint:** Must match the existing `InMemoryBus` dedup behavior keyed on `(routing_key, item_id)`.

### Testing strategy

**Decision:** Create end-to-end smoke test in `tests/test_bus_rabbitmq.py`:
1. Start RabbitMQ container (Docker via pytest fixture)
2. Publish test messages to all 4 routing keys
3. Consume from all 4 queues
4. Verify poison message dead-lettering

**Constraint:** Test must use real RabbitMQ, not mock; Phase 2Postgres already has docker-compose testing pattern.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  RabbitMQ (Docker, port 22001)                                      │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  infotriage.events (topic exchange, durable)                │   │
│  │  ├─ item.ingested → q.triage (durable)                     │   │
│  │  ├─ verdict.ready → q.brief (durable)                      │   │
│  │  ├─ sab.published → q.notify (durable)                     │   │
│  │  └─ feed.unhealthy → q.ops (durable)                       │   │
│  └─────────────────────────────────────────────────────────────┘   │
│  infotriage.dlx (DLX, durable) ──→ infotriage.dlq (DLQ, durable)   │
└─────────────────────────────────────────────────────────────────────┘
                            ▲
                            │ aio-pika (BusClient implementation)
                            │
                     ┌────┴────┐
                     │  Apps   │
                     └─────────┘
```

## Implementation tasks

1. **docker-compose.yml**: Add RabbitMQ 3.13 container with ports 22001/22002
2. **libs/contracts/_bus_rabbitmq.py**: Implement BusClient with aio-pika
3. **tests/test_bus_rabbitmq.py**: Smoke test for all 4 event types
4. **apps/*/Dockerfile**: Add RabbitMQ client dependency (aio-pika)

## Open decisions

- Container image: `rabbitmq:3.13-management` or `rabbitmq:3.13` + management plugin?
- Docker restart policy: `always` or `unless-stopped`?
- Connection pool size for concurrent producers/consumers?
- Message TTL on DLQ (to prevent unbounded growth)?

## Blockers

None — ADR-007 already accepted, Phase 0 R1 topology proven.
