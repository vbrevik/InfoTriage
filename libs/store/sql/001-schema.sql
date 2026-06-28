-- 001-schema.sql
-- Namespace and extension foundation.
-- Must sort first so infotriage.* references in later files resolve correctly.
-- Idempotent: both statements use IF NOT EXISTS.
CREATE SCHEMA IF NOT EXISTS infotriage;
SET search_path = infotriage, public;
CREATE EXTENSION IF NOT EXISTS vector;
