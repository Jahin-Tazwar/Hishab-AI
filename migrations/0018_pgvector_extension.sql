-- 0018_pgvector_extension.sql
-- Enables pgvector for citation-corpus ANN search used by the notice drafter.
-- Idempotent: harmless if the extension was already enabled.

CREATE EXTENSION IF NOT EXISTS vector;
