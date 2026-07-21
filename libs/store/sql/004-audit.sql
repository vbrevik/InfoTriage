-- 004-audit.sql
-- Audit trail for store write events (DD-5).
-- Records every put_item / put_blob call with op, table, item id, and timestamp.
CREATE TABLE IF NOT EXISTS infotriage.audit (
    id          BIGSERIAL   PRIMARY KEY,
    op          TEXT        NOT NULL,               -- 'put_item', 'put_blob'
    table_name  TEXT,                               -- 'articles', 'blobs', etc.
    item_id     TEXT,                               -- Item.id or blob sha256 hash
    ts          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Phase 9: structured details for pre-filter skip events (D-11, D-12)
ALTER TABLE infotriage.audit ADD COLUMN IF NOT EXISTS details JSONB;
