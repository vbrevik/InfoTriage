-- 005-stubs.sql
-- Forward-declared stub tables for future phases (DD-3).
-- These tables are intentionally bare — later phases own the real columns.

-- Phase 4/5 owns enrichment columns (ccir, cnr, score, bucket, why, ...)
CREATE TABLE IF NOT EXISTS infotriage.enrichment (
    id          SERIAL      PRIMARY KEY,
    item_id     TEXT        NOT NULL REFERENCES infotriage.articles(id),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Phase 4/5 defines ccir-specific scoring columns
CREATE TABLE IF NOT EXISTS infotriage.ccir (
    id          SERIAL      PRIMARY KEY,
    item_id     TEXT        NOT NULL REFERENCES infotriage.articles(id),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
