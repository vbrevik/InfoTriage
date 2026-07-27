---
phase: 260726-jpe-fix-rabbitmqbus-topology
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - libs/contracts/src/contracts/_bus_rabbitmq.py
  - tests/test_bus_rabbitmq.py
  - tests/test_bus_consume.py
  - apps/wiki/wiki_worker.py
autonomous: false
requirements: [BUS-FANOUT-01]

must_haves:
  truths:
    - "Publishing ONE verdict.ready event delivers an independent copy to BOTH q.brief and q.wiki."
    - "apps/brief/consumer.py's consume(\"verdict.ready\", ...) still resolves to q.brief with zero source changes."
    - "apps/triage/worker.py's consume(\"item.ingested\", ...) still resolves to q.triage with zero source changes."
    - "apps/wiki/wiki_worker.py --mode events consumes from q.wiki and never competes with brief for a message."
    - "consume() raises ValueError for an unknown routing key AND for a queue name not bound to the given routing key."
    - "The live infotriage-brief container keeps receiving every verdict.ready event while wiki events mode is running."
  artifacts:
    - "libs/contracts/src/contracts/_bus_rabbitmq.py — ROUTING_KEY_TO_QUEUE maps each routing key to a list of queue names; consume() takes an optional queue_name."
    - "tests/test_bus_consume.py::test_verdict_ready_fans_out_to_both_queues — the bug-fix regression proof."
    - "tests/test_bus_consume.py::test_consume_rejects_queue_not_bound_to_routing_key"
    - "tests/test_bus_rabbitmq.py — fixtures in list shape, all 5 existing tests green (single-queue zero-regression guard)."
    - "apps/wiki/wiki_worker.py — run_consumer() passes queue_name=\"q.wiki\"."
  key_links:
    - "The constant NAME ROUTING_KEY_TO_QUEUE must survive verbatim — both test files patch it via patch.multiple(\"contracts._bus_rabbitmq\", ROUTING_KEY_TO_QUEUE=...). A rename leaves the real constant unpatched underneath and silently sends tests at production queues."
    - "self._queues is re-keyed from routing_key to queue name. tests/test_bus_rabbitmq.py:190 (set(bus._queues.keys()) == set(ROUTING_KEYS)) and tests/test_bus_consume.py:158 (bus._queues[rk].cancel(...)) both index it and BREAK unless updated in the same commit."
    - "consume()'s queue_name default resolving to q_names[0] is the single mechanism preserving brief and triage behavior — if it resolves to anything else, both production consumers silently move queues."
    - "publish() is untouched: a topic exchange already fans one message out to every bound queue, and mandatory=True only errors when ZERO queues are bound."
    - "_rebuild_topology()'s deletion loop iterates ROUTING_KEY_TO_QUEUE.values(); with list values an un-flattened loop passes a list to queue_delete() instead of a name."
---

<objective>
Fix the competing-consumer bug in `RabbitMQBus`: `verdict.ready` currently resolves to exactly
one queue (`q.brief`), so `apps/wiki/wiki_worker.py --mode events` and `apps/brief/consumer.py`
become competing consumers on a single RabbitMQ queue — each event goes to exactly ONE of them.
Live-confirmed: wiki's handler never fired, and in production `brief` (a working, deployed
service) would silently lose a fraction of its events to wiki.

Fix: give each routing key a LIST of independently-bound queues, add `q.wiki` alongside
`q.brief` on `verdict.ready`, and let `consume()` take an optional `queue_name` override.
The topic exchange then fans one published message into both queues as separate copies.

Purpose: unblock wiki events mode AND remove a real regression risk to the deployed brief service.
Output: a fan-out-capable bus topology, a regression test that proves both queues receive
their own copy, and a live-stack confirmation that brief is unaffected.
</objective>

<execution_context>
@$HOME/.claude/gsd-core/workflows/execute-plan.md
@$HOME/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@CLAUDE.md

@libs/contracts/src/contracts/_bus_rabbitmq.py
@tests/test_bus_rabbitmq.py
@tests/test_bus_consume.py
@apps/wiki/wiki_worker.py
</context>

<constraints>
- The fix design is LOCKED: list-of-queue-names per routing key + optional `queue_name` override
  in `consume()`. Do not redesign, do not introduce per-consumer exclusive queues, do not switch
  exchange types, do not touch `publish()`.
- ZERO regression tolerance for `apps/triage/worker.py` (`item.ingested`) and
  `apps/brief/consumer.py` (`verdict.ready`). Both files stay untouched by this work and must
  keep resolving to `q.triage` / `q.brief` respectively.
- Do NOT touch `libs/contracts/src/contracts/_bus.py` (InMemoryBus / BusClient Protocol —
  `consume()` is a RabbitMQBus-only extension and is not on that Protocol).
- Do NOT touch `apps/dlq_consumer/worker.py` (consumes via raw aio-pika `self._dlq.consume(...)`,
  unaffected either way).
- `apps/triage/worker.py` and `apps/brief/vault_writer.py` already carry UNRELATED uncommitted
  working-tree changes. Do not stage them into this fix's commit and do not revert them.
</constraints>

<blast_radius>
Full grep of `ROUTING_KEY_TO_QUEUE` / `_queues` / `.consume(` across the repo — this is the
complete set, no further discovery needed:

| Site | Line(s) | Disposition |
|------|---------|-------------|
| `libs/contracts/src/contracts/_bus_rabbitmq.py` | 42, 74, 120, 162-174, 210, 232-260 | CHANGED (Task 1) |
| `tests/test_bus_rabbitmq.py` | 45-55, 84, 129, 190-192, 319 | CHANGED (Task 1) |
| `tests/test_bus_consume.py` | 39-44, 95, 119, 151, 158 | CHANGED (Tasks 1-2) |
| `apps/wiki/wiki_worker.py` | 166 | CHANGED (Task 3) |
| `apps/triage/worker.py` | 379 | UNTOUCHED — must keep resolving to `q.triage` |
| `apps/brief/consumer.py` | 317 | UNTOUCHED — must keep resolving to `q.brief` |
| `apps/dlq_consumer/worker.py` | 129 | UNTOUCHED — raw aio-pika, out of scope |
| `libs/contracts/src/contracts/_bus.py` | 55, 63, 66 | UNTOUCHED — InMemoryBus's own unrelated `_queues` |
| `tests/test_contracts.py`, `test_ingest_*.py` | various `bus.subscribe(...)` | UNTOUCHED — InMemoryBus only |
</blast_radius>

<tasks>

<task type="tracer" tdd="true">
  <name>Task 1: Fan-out topology end-to-end — list-valued queue map, queue-name-keyed _queues, consume(queue_name=)</name>
  <precondition>RabbitMQ is reachable on 127.0.0.1:22001 (`docker compose up -d rabbitmq` if the port refuses a TCP connect).</precondition>
  <reversibility rating="reversible">Pure additive topology change plus a defaulted keyword arg; revertible with `git revert` and a broker-side `queue_delete q.wiki`.</reversibility>
  <files>libs/contracts/src/contracts/_bus_rabbitmq.py, tests/test_bus_rabbitmq.py, tests/test_bus_consume.py</files>

  <behavior>
    After this task, against the test-isolated topology:
    - Every routing key with a single queue behaves EXACTLY as before (`test_bus_rabbitmq.py` keeps
      one queue per key — it is the zero-regression guard).
    - `consume(rk, handler)` with no queue override resolves to the FIRST queue in that key's list.
    - `consume(rk, handler, queue_name=<a queue bound to rk>)` resolves to that specific queue.
    - `consume(<unknown key>, handler)` still raises ValueError.
    - `bus._queues` is keyed by queue name, and its key set equals the flattened set of all
      declared queue names.
  </behavior>

  <action>
    FIRST, record the pre-change baseline so Task 4 has something to compare against. Run the full
    suite with `INFOTRIAGE_PG_DSN=postgresql://infotriage:infotriage_dev@127.0.0.1:22000/infotriage`
    plus `mypy` and `black --check`, and save the pass/skip/fail counts and any pre-existing mypy
    errors for `apps/wiki/wiki_worker.py` into the session scratchpad as `bus-fanout-baseline.txt`.

    THEN edit `libs/contracts/src/contracts/_bus_rabbitmq.py`:

    1. Widen `ROUTING_KEY_TO_QUEUE` (line 42) so each routing key maps to a LIST of queue names,
       KEEPING THE CONSTANT NAME EXACTLY AS IT IS — both test files reach it by that name through
       `patch.multiple`, and renaming it would leave the real constant live and unpatched
       underneath (a silent, test-invisible breakage). Annotate it `dict[str, list[str]]`. Every
       existing key keeps its current single queue as a one-element list; `verdict.ready` becomes
       `["q.brief", "q.wiki"]` with `q.brief` FIRST (first entry = the default/primary queue).

    2. Re-key `self._queues` (line 74) from routing key to QUEUE NAME. Queue names are already
       globally unique across routing keys, so this is a lossless re-keying. Update the trailing
       comment on that line to say the key is the queue name.

    3. `_declare_topology()` (lines 162-174): iterate the outer routing-key/queue-list pairs, then
       the inner queue names; declare each queue with the identical durable + dead-letter arguments
       it has today (do not change any queue argument — changed args on an existing queue would
       trip a 406 and drag the whole broker through `_rebuild_topology()`), bind each to its
       routing key on the events exchange, and store it under its own name.

    4. `_rebuild_topology()` (line 120): flatten the list-of-lists when building the deletion list,
       so `queue_delete` receives queue names and not list objects.

    5. `consume()` (lines 232-260): add a trailing keyword-only-style optional parameter defaulting
       to `None` that lets a caller pick which of the routing key's queues to attach to. Resolve
       the key to its queue list; raise ValueError (unchanged message shape) if the key is unknown;
       default to the FIRST list entry when no override is given — this default is the ONLY thing
       preserving triage's and brief's current behavior, so it must not be reordered or made
       arbitrary; raise ValueError if an override names a queue not bound to that routing key; then
       look up `self._queues` by the resolved queue name. Rewrite the docstring paragraph that
       currently claims `self._queues` is keyed by routing key — that statement becomes false here.

    6. `subscribe()` (line 210): it resolves a single queue name today. Change it to take the FIRST
       entry of the routing key's list so its behavior against a key's primary queue is unchanged.
       Do NOT give `subscribe()` an override parameter — it is out of scope for this fix.

    7. Module docstring topology block (line 11): note that a routing key MAY have several
       independently-bound queues so one published message fans out to all of them, citing
       `q.wiki` alongside `q.brief` on `verdict.ready` as the live example.

    THEN sync the two test files to the new shape — mechanical only, no new tests here:

    8. `tests/test_bus_rabbitmq.py`: make `TEST_ROUTING_KEY_TO_QUEUE` (lines 45-50) one-element
       lists for ALL FOUR keys — this file is deliberately the single-queue regression guard and
       must NOT gain a wiki queue. Add a module-level flattened list of every test queue name and
       use it at line 84 (cleanup) and at lines 190-192, where the assertion currently compares
       `bus._queues.keys()` against the ROUTING KEYS and will now fail — it must compare against
       the flattened queue-name set. At line 319, `TEST_ROUTING_KEY_TO_QUEUE["item.ingested"]` is
       handed straight to `get_queue()` and now needs the first list element. Rename the loop
       variable in `_fresh_bus()` (line 129) from `rk` to a queue-name name, since that is what it
       now holds.

    9. `tests/test_bus_consume.py`: same one-element-list conversion at lines 39-44 (the wiki queue
       arrives in Task 2, not here), flatten the cleanup list at line 95, rename the `_fresh_bus()`
       loop variable at line 119, and fix line 158 — it cancels via `bus._queues[rk]` with a
       ROUTING KEY and must now index by the resolved queue name for that key.
  </action>

  <verify>
    <automated>docker compose up -d rabbitmq && pytest tests/test_bus_rabbitmq.py tests/test_bus_consume.py -v -m rabbitmq</automated>
    <automated>PYTHONPATH=libs/contracts/src python -c "from contracts._bus_rabbitmq import ROUTING_KEY_TO_QUEUE as M; assert all(isinstance(v, list) and v for v in M.values()), M; assert M['verdict.ready'][0] == 'q.brief', M; assert 'q.wiki' in M['verdict.ready'], M; assert M['item.ingested'] == ['q.triage'] and M['sab.published'] == ['q.notify'] and M['feed.unhealthy'] == ['q.ops'], M; print('SHAPE-OK')"</automated>
    <automated>PYTHONPATH=libs/contracts/src python -c "import inspect; from contracts._bus_rabbitmq import RabbitMQBus as B; p = inspect.signature(B.consume).parameters; assert 'queue_name' in p, list(p); assert p['queue_name'].default is None; assert list(p)[:4] == ['self', 'routing_key', 'handler', 'prefetch_count'], list(p); print('SIG-OK')"</automated>
    <automated>mypy libs/contracts/src/contracts/_bus_rabbitmq.py tests/test_bus_rabbitmq.py tests/test_bus_consume.py && black --check libs/contracts/src/contracts/_bus_rabbitmq.py tests/test_bus_rabbitmq.py tests/test_bus_consume.py</automated>
  </verify>

  <done>
    All 5 tests in `tests/test_bus_rabbitmq.py` and both existing tests in `tests/test_bus_consume.py`
    pass under `-m rabbitmq`. SHAPE-OK and SIG-OK both print. mypy and black are clean on all three
    files. The pre-change baseline file exists in the scratchpad. `q.brief` is the first entry for
    `verdict.ready`, and the constant is still reachable as `contracts._bus_rabbitmq.ROUTING_KEY_TO_QUEUE`.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Regression test — one verdict.ready event lands in BOTH queues as independent copies</name>
  <precondition>RabbitMQ is reachable on 127.0.0.1:22001.</precondition>
  <files>tests/test_bus_consume.py</files>

  <behavior>
    - Test A (`test_verdict_ready_fans_out_to_both_queues`): with the test topology binding TWO
      queues to `verdict.ready`, ONE published message is received by a consumer registered with no
      queue override AND by a consumer registered against the wiki-equivalent queue. Both handlers
      fire, both see the identical payload, and neither steals the other's message. This is the
      direct inverse of the live-observed bug.
    - Test B (`test_consume_rejects_queue_not_bound_to_routing_key`): asking to consume
      `verdict.ready` from the triage-equivalent queue raises ValueError.
    - Existing `test_consume_delivers_message` and `test_consume_unknown_routing_key_raises` keep
      passing unchanged.
  </behavior>

  <action>
    In `tests/test_bus_consume.py`, extend `TEST_ROUTING_KEY_TO_QUEUE`'s `verdict.ready` entry to
    bind a SECOND test-prefixed queue (the wiki equivalent) after the brief equivalent, keeping the
    brief equivalent first so the no-override default still resolves to it. The module cleanup
    fixture already flattens after Task 1, so the new queue is torn down automatically — confirm
    that rather than adding a second cleanup path.

    Add Test A following this file's existing conventions exactly: the `@pytest.mark.rabbitmq`
    decorator, the `_skip_if_unavailable()` guard, an inner `async def _run()` driven by
    `asyncio.run()` inside the `_patched_topology()` context manager, and `_fresh_bus()` for a
    purged bus. Register two handlers, each setting its own `asyncio.Event` and recording its own
    decoded payload dict inside `async with msg.process()`. Register the first consumer with NO
    queue override (proving the production brief call signature is untouched) and the second with
    an explicit override naming the wiki-equivalent queue. Publish ONE message with a unique
    `item_id` (per-instance publish dedup keys on `(routing_key, item_id)`, so reuse across tests
    would silently no-op). Await both events together under a single `asyncio.wait_for` with the
    5-second timeout this file already uses, then assert both recorded payloads equal the published
    payload. In `finally`, cancel both consumer tags via the queue objects looked up by their
    resolved queue names, then close the bus.

    Add Test B in the same style: assert ValueError when consuming `verdict.ready` with an override
    naming the triage-equivalent queue, which is bound to a different routing key.
  </action>

  <verify>
    <automated>pytest tests/test_bus_consume.py -v -m rabbitmq</automated>
    <automated>pytest tests/test_bus_consume.py -m rabbitmq -q --collect-only | grep -c "test_verdict_ready_fans_out_to_both_queues\|test_consume_rejects_queue_not_bound_to_routing_key"</automated>
    <automated>mypy tests/test_bus_consume.py && black --check tests/test_bus_consume.py</automated>
  </verify>

  <done>
    Four tests pass in `tests/test_bus_consume.py` under `-m rabbitmq` (two pre-existing, two new);
    the collect-only grep count is 2. Negative control confirmed ONCE by hand: temporarily remove
    the wiki-equivalent queue from that file's `verdict.ready` list, re-run — the fan-out test must
    FAIL (the second consumer either raises on the unbound queue name or times out) — then restore
    the entry and re-run green. Record both outcomes in the summary. mypy and black clean.
  </done>
</task>

<task type="auto">
  <name>Task 3: Point wiki's events-mode consumer at its own queue</name>
  <files>apps/wiki/wiki_worker.py</files>
  <action>
    In `run_consumer()` (line 166), the `verdict.ready` consumer registration currently uses the
    default queue resolution, which is byte-identical to what `apps/brief/consumer.py` line 317
    does — that identity IS the bug. Add the explicit queue override so wiki attaches to its own
    `q.wiki` instead of contending for brief's queue. Change nothing else in the function: the
    routing key, the handler, the prefetch value, and the `await asyncio.Future()` run-forever tail
    all stay as they are. Do not open `apps/brief/consumer.py` or `apps/triage/worker.py`.
  </action>
  <verify>
    <automated>grep -v '^[[:space:]]*#' apps/wiki/wiki_worker.py | grep -c 'queue_name="q.wiki"'</automated>
    <automated>git diff -- apps/brief/consumer.py | grep -c '^[+-].*consume' | grep -qx 0 && echo BRIEF-UNTOUCHED</automated>
    <automated>git diff -- apps/triage/worker.py | grep -c '^[+-].*bus\.consume' | grep -qx 0 && echo TRIAGE-UNTOUCHED</automated>
    <automated>mypy apps/wiki/wiki_worker.py; black --check apps/wiki/wiki_worker.py</automated>
  </verify>
  <done>
    The grep count is exactly 1. Both diff guards fire: BRIEF-UNTOUCHED and TRIAGE-UNTOUCHED echo,
    proving neither production consumer's `consume(...)` line was added to or removed from.
    `black --check` is clean and `mypy apps/wiki/wiki_worker.py` shows no NEW errors versus the
    Task 1 baseline file.
  </done>
</task>

<task type="auto">
  <name>Task 4: Full-suite zero-regression gate, then commit</name>
  <precondition>`INFOTRIAGE_PG_DSN=postgresql://infotriage:infotriage_dev@127.0.0.1:22000/infotriage` is exported (this repo's standing test convention) and RabbitMQ :22001 is up.</precondition>
  <files>(no source edits — verification + commit only)</files>
  <action>
    Run the full suite twice: once normally and once with `-m rabbitmq`, both with the Postgres DSN
    exported. Diff the pass/skip/fail counts against the baseline captured in Task 1. Any test that
    passed before and fails now is a BLOCKING regression — stop and fix rather than rationalise it,
    especially anything under `tests/test_brief_*.py`, `tests/test_triage_*.py`, or
    `tests/test_dlq_consumer.py`, since those cover the two consumers this fix must not disturb.

    Then run `mypy` and `black --check` across all four changed files and confirm clean.

    Commit ONLY the four files this plan touches, staged by explicit path — never `git add .`. The
    working tree carries unrelated uncommitted changes in `apps/brief/vault_writer.py` and
    `apps/triage/worker.py`; leave both alone and out of the commit. Use this repo's conventional
    imperative style, subject line `fix(bus): fan verdict.ready out to q.brief and q.wiki`, with a
    body naming the competing-consumer root cause, the fact that brief and triage call sites are
    unchanged by design, and the regression test that proves the fan-out. Keep the plan/summary
    documents out of this commit so the fix lands as its own reviewable change.
  </action>
  <verify>
    <automated>INFOTRIAGE_PG_DSN=postgresql://infotriage:infotriage_dev@127.0.0.1:22000/infotriage pytest tests/ -q</automated>
    <automated>INFOTRIAGE_PG_DSN=postgresql://infotriage:infotriage_dev@127.0.0.1:22000/infotriage pytest tests/ -q -m rabbitmq</automated>
    <automated>mypy libs/contracts/src/contracts/_bus_rabbitmq.py tests/test_bus_rabbitmq.py tests/test_bus_consume.py apps/wiki/wiki_worker.py; black --check libs/contracts/src/contracts/_bus_rabbitmq.py tests/test_bus_rabbitmq.py tests/test_bus_consume.py apps/wiki/wiki_worker.py</automated>
    <automated>git show --stat --name-only HEAD | grep -c 'vault_writer.py\|apps/triage/worker.py' | grep -qx 0 && echo NO-UNRELATED-FILES-COMMITTED</automated>
  </verify>
  <done>
    Both full-suite runs report 0 failures, with a pass count greater than or equal to the Task 1
    baseline plus the two new tests. mypy and black clean on all four files. One commit exists whose
    file list is exactly the four planned files; NO-UNRELATED-FILES-COMMITTED echoes.
  </done>
</task>

<task type="auto">
  <name>Task 5: Live-stack confidence check — wiki events mode alongside the running brief service</name>
  <precondition>Containers `infotriage-rabbitmq`, `infotriage-brief`, and `infotriage-wiki` are all running (`docker ps`), and the RabbitMQ management API answers on 127.0.0.1:22002.</precondition>
  <reversibility rating="costly">Exercises a live production consumer path; the wiki container is deliberately restored to its deployed periodic mode at the end of this task, but a mishandled step leaves a stray events-mode consumer attached to the broker.</reversibility>
  <files>(no source edits — live verification only)</files>
  <action>
    This mirrors the manual test that originally exposed the bug and is the definitive proof it is
    fixed. Do NOT stop or restart the `brief` container at any point — an unaffected, still-running
    brief is precisely what is under test.

    The wiki container ships `libs/contracts` baked into its image, so the running container still
    holds the OLD bus code. Rebuild and restart ONLY wiki first (`docker compose build wiki` then
    `docker compose up -d wiki`); it comes back in its normal periodic mode with the new code.

    Capture a "before" reading of the delivery counters for both `q.brief` and `q.wiki` from the
    management API (basic auth `infotriage:infotriage_rmq`), recording each queue's cumulative
    delivered/get count and current depth. A 404 on `q.wiki` at this point is expected only if
    nothing has connected with the new code yet; wiki's own startup should have declared it.

    Start a SECOND, temporary wiki process inside the already-running container in events mode with
    a health port distinct from the deployed instance's (use 22099) so the two do not collide —
    derive the exact interpreter path, working directory, and argument form from the wiki service's
    configured command (`docker compose config wiki` / the app Dockerfile) rather than assuming.
    Run it detached and give it a few seconds to attach its consumer.

    Publish ONE real `verdict.ready` event from the host through `RabbitMQBus` with a fresh, unique
    item_id, using the working-tree code on PYTHONPATH.

    Read the "after" counters for both queues. BOTH must show one more delivery than the "before"
    reading — that is the fan-out working, with brief entirely unaffected. Also confirm from the
    temporary process's logs that wiki's handler actually fired for that item_id, and grep the
    wiki and brief logs for any topology-mismatch or rebuild warning: a broker-side rebuild would
    mean an argument mismatch was introduced and would have deleted production queues, which is a
    BLOCKING finding.

    Finally, restore the deployed state: `docker compose restart wiki`, which kills the temporary
    events-mode consumer and returns the container to periodic mode. Confirm with `docker ps` that
    wiki is healthy and that no process is still bound to port 22099. Leaving the container in
    events mode is a failure of this task.
  </action>
  <verify>
    <automated>curl -s -u infotriage:infotriage_rmq 'http://127.0.0.1:22002/api/queues/%2f/q.brief' | python -c "import sys,json; d=json.load(sys.stdin); print('q.brief', d['messages'], d.get('message_stats',{}).get('deliver_get'), d['consumers'])"</automated>
    <automated>curl -s -u infotriage:infotriage_rmq 'http://127.0.0.1:22002/api/queues/%2f/q.wiki' | python -c "import sys,json; d=json.load(sys.stdin); print('q.wiki', d['messages'], d.get('message_stats',{}).get('deliver_get'), d['consumers'])"</automated>
    <automated>docker ps --filter name=infotriage-wiki --format '{{.Names}} {{.Status}}'</automated>
    <automated>docker logs --since 10m infotriage-wiki 2>&1 | grep -ci 'topology mismatch' | grep -qx 0 && echo NO-TOPOLOGY-REBUILD</automated>
  </verify>
  <done>
    The q.brief and q.wiki delivery counters each incremented by exactly one for the single published
    event; brief's consumer count is unchanged from before the test. Wiki's temporary events-mode
    logs show its handler processing that item_id. NO-TOPOLOGY-REBUILD echoes. `docker ps` shows
    infotriage-wiki running and healthy after the restart, back in periodic mode, with nothing
    listening on 22099. Before/after counter readings are recorded verbatim in the summary.
  </done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <what-built>
    `verdict.ready` now fans out to two independently-bound queues. `apps/wiki/wiki_worker.py`
    consumes from `q.wiki`; `apps/brief/consumer.py` and `apps/triage/worker.py` are untouched and
    still resolve to `q.brief` and `q.triage`. A new regression test proves one published event
    reaches both queues, and a live check against the running stack was performed with the
    production brief container left running throughout.
  </what-built>
  <how-to-verify>
    1. Read the before/after RabbitMQ counters recorded in the summary — both `q.brief` and
       `q.wiki` must show +1 delivery for the single test event.
    2. `docker ps` — `infotriage-brief` uptime must show it was never restarted, and
       `infotriage-wiki` must be back in its deployed periodic mode.
    3. Confirm the SAB / digest pipeline still looks correct after a normal brief cycle, i.e. brief
       lost nothing while wiki's events-mode consumer was attached.
    4. Confirm `git log -1 --stat` shows exactly the four intended files and none of the unrelated
       working-tree changes to `apps/brief/vault_writer.py` or `apps/triage/worker.py`.
  </how-to-verify>
  <resume-signal>Type "approved" or describe issues</resume-signal>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| host/test process → live RabbitMQ broker | Task 5 publishes a real event into the production vhost and attaches a temporary consumer next to a deployed service. |
| bus module → all consuming services | A single shared constant determines which queue every service attaches to; a wrong resolution silently reroutes production traffic. |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-BUSFAN-01 | Denial of Service | `_rebuild_topology()` on 406 | high | mitigate | Queue arguments are held identical to today's (Task 1 action step 3) so no 406 can fire; Task 5 greps container logs for a topology-mismatch warning and treats any hit as BLOCKING, since a rebuild deletes production queues and their queued messages. |
| T-BUSFAN-02 | Denial of Service | `consume()` default queue resolution | critical | mitigate | The no-override default is pinned to the first list entry with `q.brief` / `q.triage` first; asserted by the SHAPE-OK check in Task 1 and by the no-override consumer in the Task 2 fan-out test; brief and triage source files are diff-gated untouched in Task 3. |
| T-BUSFAN-03 | Tampering | test topology patching via `ROUTING_KEY_TO_QUEUE` | medium | mitigate | The constant name is preserved verbatim so `patch.multiple` keeps redirecting tests to `test.`-prefixed queues; a rename would let the integration suite publish into and purge PRODUCTION queues. Called out as a key_link and enforced by the Task 1 import assertion. |
| T-BUSFAN-04 | Information Disclosure | AMQP DSN and management-API credentials | low | accept | Existing dev-only credentials, already present in the repo's test files and compose config; this change introduces no new secret and no new logging of the DSN (T-03-01 unchanged). |
| T-BUSFAN-SC | Tampering | package installs | low | accept | No package-manager installs in this plan — no new dependencies are added; supply-chain surface is unchanged. |
</threat_model>

<verification>
- `pytest tests/test_bus_rabbitmq.py tests/test_bus_consume.py -v -m rabbitmq` — all green, including
  the two new fan-out/rejection tests.
- `INFOTRIAGE_PG_DSN=... pytest tests/ -q` and `... -q -m rabbitmq` — 0 failures, pass count at or
  above the Task 1 baseline + 2.
- `mypy` and `black --check` clean on all four changed files.
- Live: one `verdict.ready` event increments the delivery counter on BOTH `q.brief` and `q.wiki`;
  `infotriage-brief` never restarted; `infotriage-wiki` returned to periodic mode.
</verification>

<success_criteria>
- One published `verdict.ready` message produces two independent deliveries (brief + wiki), proven
  by an automated test AND by live management-API counters.
- `apps/brief/consumer.py` and `apps/triage/worker.py` have zero diff lines touching their
  `consume(...)` calls, and every pre-existing test still passes.
- `consume()` rejects both an unknown routing key and a queue not bound to the given routing key.
- The fix lands as a single commit containing exactly the four planned files.
</success_criteria>

<output>
Create `.planning/quick/260726-jpe-fix-rabbitmqbus-topology-so-verdict-read/260726-jpe-SUMMARY.md` when done,
recording: the before/after RabbitMQ delivery counters for both queues, the Task 2 negative-control
result, the baseline-vs-final full-suite counts, and the commit SHA.
</output>
