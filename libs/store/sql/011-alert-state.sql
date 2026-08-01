-- 011-alert-state.sql
-- Dedupe/throttle state substrate for the alerting service (D-02, Phase 12 plan 12-02).
--
-- ## Why
-- apps/alerting/{dedupe,throttle}.py (plans 12-04/12-05) need a single row per fired
-- alert to (a) atomically dedupe repeat fires of the same (item_id, cnr_tier) inside a
-- 24h TTL and (b) count alerts fired in a sliding window for throttling. D-02 pins this
-- as a new Postgres table accessed through the existing Store protocol — no new
-- infrastructure, no message-bus state.
--
-- ## Idempotency
-- CREATE TABLE IF NOT EXISTS + CREATE UNIQUE INDEX IF NOT EXISTS / CREATE INDEX IF NOT
-- EXISTS throughout (006-enrichment.sql idiom) — re-applying this file via init_schema()
-- is a no-op.
--
-- ## Load-bearing unique index — DO NOT DROP
-- alert_state_dedupe_id_unique is what makes `INSERT ... ON CONFLICT (dedupe_id) DO
-- UPDATE ... RETURNING` in claim_alert() legal. Without this index the atomic
-- check-and-set degrades to a race-prone read-then-write (T-12-07). dedupe_id is the
-- sha256-truncated identity from SPEC R2, not the row's surrogate primary key.
--
-- ## Clock source
-- fired_at is the single timestamp both the 24h dedupe TTL and both sliding-window
-- throttle counts are computed against (SPEC R2, SPEC R3). No other timestamp column
-- backs a time-window query.
--
-- ## Suppressed rows are never deleted
-- A suppressed=true row stays in the table until enumerated by a digest (digested_at
-- set) — SPEC R3 forbids silently dropping a throttled alert (T-12-09). Retention/GC of
-- old rows is explicitly not minted by this migration (T-12-08, accepted at current
-- volume of <=5 CAT I alerts/day).

CREATE TABLE IF NOT EXISTS infotriage.alert_state (
    id           SERIAL      PRIMARY KEY,
    dedupe_id    TEXT        NOT NULL,
    item_id      TEXT        NOT NULL,
    cnr_tier     TEXT        NOT NULL,
    alert_id     TEXT        NOT NULL,
    fired_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    suppressed   BOOLEAN     NOT NULL DEFAULT FALSE,
    pmesii       TEXT,
    title        TEXT,
    digested_at  TIMESTAMPTZ,
    delivered_at TIMESTAMPTZ,
    dlx_at       TIMESTAMPTZ
);

-- Load-bearing: backs the ON CONFLICT (dedupe_id) atomic claim in claim_alert().
CREATE UNIQUE INDEX IF NOT EXISTS alert_state_dedupe_id_unique
    ON infotriage.alert_state (dedupe_id);

-- Sliding-window throttle scans read recent rows by fired_at.
CREATE INDEX IF NOT EXISTS alert_state_fired_at_idx
    ON infotriage.alert_state (fired_at DESC);

-- Digest-pending lookup: suppressed rows awaiting enumeration in the next digest.
CREATE INDEX IF NOT EXISTS alert_state_digest_pending_idx
    ON infotriage.alert_state (suppressed, digested_at);
