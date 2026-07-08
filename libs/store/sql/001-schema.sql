-- 001-schema.sql
-- Namespace and extension foundation.
-- Must sort first so infotriage.* references in later files resolve correctly.
-- Idempotent: both statements use IF NOT EXISTS.
CREATE SCHEMA IF NOT EXISTS infotriage;
SET search_path = infotriage, public;
-- WITH SCHEMA public: without it, the extension installs into the first
-- search_path schema (infotriage), and connections using the default
-- search_path ("$user", public) cannot resolve the vector type —
-- register_vector() then fails on any freshly-bootstrapped database.
CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;
