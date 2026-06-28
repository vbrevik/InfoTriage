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
