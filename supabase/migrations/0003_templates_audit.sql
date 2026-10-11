-- V2-02: template registry + audit log for the Supabase backend.

CREATE TABLE IF NOT EXISTS templates (
    name TEXT PRIMARY KEY,
    body_skeleton TEXT NOT NULL DEFAULT '',
    default_tags TEXT[] NOT NULL DEFAULT '{}'
);

-- Append-only audit trail (replaces the flat mcp_audit.log file).
CREATE TABLE IF NOT EXISTS audit_log (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    at TIMESTAMPTZ NOT NULL DEFAULT now(),
    username TEXT NOT NULL,
    tool TEXT NOT NULL,
    filename TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS audit_log_at_idx ON audit_log (at DESC);
