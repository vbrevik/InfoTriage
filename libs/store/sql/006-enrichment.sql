-- 006-enrichment.sql
-- Idempotent enrichment schema migration (D-10, R1).
-- Extends the bare stub table from 005-stubs.sql with:
--   (1) UNIQUE index on infotriage.enrichment.item_id  → backs ON CONFLICT upsert in put_enrichment
--   (2) 7 enrichment scoring columns: ccir, cnr, score (CHECK 0..10), bucket, why, pmesii, tessoc
--   (3) UNIQUE index on infotriage.embeddings.item_id  → backs ON CONFLICT upsert in put_embedding
-- All statements use IF NOT EXISTS — re-applying via init_schema() is a no-op (idempotent, R1).
--
-- NOTE: Postgres has no "ALTER TABLE ... ADD CONSTRAINT IF NOT EXISTS" form.
-- CREATE UNIQUE INDEX IF NOT EXISTS is the correct idempotent pattern; ON CONFLICT (item_id)
-- honours a UNIQUE INDEX on the column, not only a named constraint.
--
-- The HNSW cosine index idx_embeddings_embedding_hnsw from 003-vectors.sql is preserved;
-- this file adds no competing index on the embedding column.

-- (1) Unique index on enrichment.item_id — required for ON CONFLICT (item_id) DO UPDATE upsert
CREATE UNIQUE INDEX IF NOT EXISTS enrichment_item_id_unique
    ON infotriage.enrichment (item_id);

-- (2) Add 7 enrichment scoring columns
ALTER TABLE infotriage.enrichment ADD COLUMN IF NOT EXISTS ccir   TEXT;
ALTER TABLE infotriage.enrichment ADD COLUMN IF NOT EXISTS cnr    TEXT;
ALTER TABLE infotriage.enrichment ADD COLUMN IF NOT EXISTS score  INT CHECK (score BETWEEN 0 AND 10);
ALTER TABLE infotriage.enrichment ADD COLUMN IF NOT EXISTS bucket TEXT;
ALTER TABLE infotriage.enrichment ADD COLUMN IF NOT EXISTS why    TEXT;
ALTER TABLE infotriage.enrichment ADD COLUMN IF NOT EXISTS pmesii TEXT;
ALTER TABLE infotriage.enrichment ADD COLUMN IF NOT EXISTS tessoc TEXT;

-- (3) Unique index on embeddings.item_id — required for ON CONFLICT (item_id) DO UPDATE upsert
CREATE UNIQUE INDEX IF NOT EXISTS embeddings_item_id_unique
    ON infotriage.embeddings (item_id);
