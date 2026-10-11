-- V2-02: token store for the Supabase backend.
-- Mirrors TokenStore JSON fields exactly (ISO-8601 TEXT timestamps) so the
-- same parsing/validation semantics apply unchanged. Only SHA-256 digests
-- are stored — raw secrets never touch the database.

CREATE TABLE IF NOT EXISTS tokens (
    key_hash TEXT PRIMARY KEY,
    key_prefix TEXT NOT NULL,
    key_suffix TEXT NOT NULL,
    username TEXT NOT NULL,
    token_type TEXT NOT NULL CHECK (token_type IN ('read', 'read_write')),
    created_at TEXT NOT NULL,
    last_used_at TEXT,
    revoked_at TEXT,
    expires_at TEXT
);

CREATE INDEX IF NOT EXISTS tokens_prefix_idx ON tokens (key_prefix);
CREATE INDEX IF NOT EXISTS tokens_username_idx ON tokens (username);
