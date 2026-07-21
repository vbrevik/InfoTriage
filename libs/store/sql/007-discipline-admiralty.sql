-- 007-discipline-admiralty.sql
-- Phase 11: collection discipline + Admiralty reliability rating.
-- Adds optional columns to infotriage.articles for SOCMINT/Arctic provenance
-- and source-reliability tracking. Idempotent: IF NOT EXISTS/IF NOT NULL.

ALTER TABLE infotriage.articles
    ADD COLUMN IF NOT EXISTS discipline TEXT;

ALTER TABLE infotriage.articles
    ADD COLUMN IF NOT EXISTS admiralty_reliability TEXT;

CREATE INDEX IF NOT EXISTS idx_articles_discipline
    ON infotriage.articles (discipline)
    WHERE discipline IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_articles_admiralty_reliability
    ON infotriage.articles (admiralty_reliability)
    WHERE admiralty_reliability IS NOT NULL;
