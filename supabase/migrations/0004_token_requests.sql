-- Phase 11-01 (D-01): write-upgrade request queue beside tokens.
-- One row per request; one pending max per user enforced in application
-- code (D-03) so the denial message stays structured. Denied rows stay
-- visible to the requester with a timestamp; re-request allowed (D-04).

CREATE TABLE IF NOT EXISTS token_requests (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_email TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'denied')) DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    decided_at TIMESTAMPTZ,
    decided_by TEXT
);

CREATE INDEX IF NOT EXISTS token_requests_status_idx ON token_requests (status, created_at);
CREATE INDEX IF NOT EXISTS token_requests_user_idx ON token_requests (user_email);
