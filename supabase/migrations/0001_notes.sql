-- V2-01: notes + revision history for the Supabase backend.
-- Run once against the Supabase Postgres database. Safe to re-run
-- (CREATE TABLE IF NOT EXISTS; index creation is idempotent).
--
-- Identity: `stem` is the slugified note identity (filename without `.md`),
-- mirroring the filesystem backend where `{stem}.md` is the file.

CREATE TABLE IF NOT EXISTS notes (
    stem TEXT PRIMARY KEY,
    title TEXT NOT NULL CHECK (char_length(btrim(title)) > 0),
    body TEXT NOT NULL DEFAULT '',
    tags TEXT[] NOT NULL DEFAULT '{}',
    created DATE NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Every mutation inserts a revision row (replaces dulwich git history on the
-- Supabase backend). Snapshots carry the full note state for recovery.
CREATE TABLE IF NOT EXISTS note_revisions (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    stem TEXT NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('create', 'update', 'delete', 'rename')),
    old_stem TEXT,
    new_stem TEXT,
    title TEXT,
    body TEXT,
    tags TEXT[],
    created DATE,
    actor TEXT NOT NULL,
    at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS note_revisions_stem_idx ON note_revisions (stem, id DESC);
