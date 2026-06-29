---
phase: "03"
slug: bus-rabbitmq
status: verified
nyquist_compliant: true
wave_0_complete: true
created: 2026-06-29
---

# Phase 03 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.3 |
| **Config file** | `pyproject.toml` (`testpaths=["tests"]`, markers: `db_live`, `rabbitmq`) |
| **Quick run command** | `pytest tests/ -q -k "not db_live and not rabbitmq"` |
| **Full suite command** | `pytest tests/ -q` |
| **RabbitMQ suite** | `pytest tests/ -q -m rabbitmq` |
| **Estimated runtime** | ~2s (quick), ~30s (rabbitmq) |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/ -q -k "not db_live and not rabbitmq"`
- **After every plan wave:** Run `pytest tests/ -q -m rabbitmq` (requires broker)
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~2 seconds (quick), ~30 seconds (rabbitmq integration)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 03-01-01 | 01 | 1 | R1 — RabbitMQ container on :22001/:22002 | — | Ports localhost-only, no external exposure | integration | `pytest tests/test_bus_rabbitmq.py::test_rabbitmq_available -v -m rabbitmq` | ✅ | ✅ green |
| 03-01-02 | 01 | 1 | R2 — aio-pika BusClient, 4 routing keys, DLX/DLQ | T-03-01, T-03-03 | DSN never logged; reconnect rate-capped | integration | `pytest tests/test_bus_rabbitmq.py::test_rabbitmq_available -v -m rabbitmq` | ✅ | ✅ green |
| 03-01-03 | 01 | 1 | R2.AC3 — Publisher confirms enabled | — | N/A | integration | `pytest tests/test_bus_rabbitmq.py::test_publisher_confirms_enabled -v -m rabbitmq` | ✅ | ✅ green |
| 03-01-04 | 01 | 1 | R2.AC4 — requeue=False routes to DLQ | — | Poison messages quarantined | integration | `pytest tests/test_bus_rabbitmq.py::test_dlq_poison -v -m rabbitmq` | ✅ | ✅ green |
| 03-01-05 | 01 | 1 | R3 — all 4 event types roundtrip | T-03-02 | JSON serialization only; schema deferred | integration | `pytest tests/test_bus_rabbitmq.py::test_publish_consume_roundtrip -v -m rabbitmq` | ✅ | ✅ green |
| 03-01-06 | 01 | 1 | Dedup — same (routing_key, item_id) no-op | — | N/A | integration | `pytest tests/test_bus_rabbitmq.py::test_dedup -v -m rabbitmq` | ✅ | ✅ green |
| 03-01-07 | 01 | 1 | ADR-007 — RabbitMQBus satisfies BusClient Protocol | T-03-SC | N/A | unit | `pytest tests/test_contracts.py::test_rabbitmq_bus_protocol -v` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements. Framework (pytest 8.3) was already installed. All test files were created or augmented during phase execution.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `connect_robust()` auto-reconnect on broker restart | R2.AC2 | Requires network-kill harness (stop/start broker mid-session); no safe way to simulate TCP drop in pytest without `toxiproxy` or similar | 1. `docker compose up -d rabbitmq` 2. Start consumer process on `:22001` 3. `docker compose stop rabbitmq` (kills TCP) 4. `docker compose start rabbitmq` 5. Verify consumer reconnects automatically within ~30s, no exception raised |

---

## Validation Audit 2026-06-29

| Metric | Count |
|--------|-------|
| Gaps found | 3 |
| Resolved (automated) | 2 |
| Manual-only | 1 |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or documented manual-only rationale
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (no missing infra)
- [x] No watch-mode flags
- [x] Feedback latency < 2s (quick), < 30s (rabbitmq)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-06-29
