"""Supabase-backed note repository (V2-01).

Same method surface and semantics as :class:`NoteRepository` (filesystem):
slugified stems as identity, ``*.md`` filenames at the boundary, identical
validation and error types. Differences are storage-implied only:

- Writes are transactional (row + revision row commit atomically).
- ``write_note`` is an upsert, exactly like the filesystem backend.
- Metadata is validated BEFORE the write (filesystem validates after; only
  error-path side effects differ — no partial writes here by construction).
- History goes to ``note_revisions`` via :class:`SupabaseHistory` instead of git.

Connections are per-operation via :mod:`kb_mcp.db` (no pooling by design —
correct at personal-KB scale, safe on scale-to-zero hosts).
"""

from pathlib import Path

from .db import connect
from .errors import FileIOError, InvalidTypeError, NoteNotFoundError
from .history import NoteSnapshot, insert_revision
from .models import Note, NoteMetadata
from .storage import _slugify_stem
from .validation import validate_filename


def _row_to_note(stem: str, title: str, body: str, tags: list, created) -> Note:
    """Build a Note from a DB row (``created`` may be date or ISO string)."""
    created_str = created.isoformat() if hasattr(created, "isoformat") else created
    return Note(
        filename=stem,
        metadata=NoteMetadata(title=title, tags=list(tags), created=created_str),
        body=body,
    )


class SupabaseNoteRepository:
    """Note CRUD over Supabase Postgres with revision history."""

    def __init__(self) -> None:
        pass

    def _read_row(self, cur, stem: str):
        cur.execute(
            "SELECT stem, title, body, tags, created FROM notes WHERE stem = %s",
            (stem,),
        )
        return cur.fetchone()

    def read_note(self, filename: str) -> Note:
        validate_filename(filename)
        stem = Path(filename).stem
        try:
            with connect() as conn, conn.cursor() as cur:
                row = self._read_row(cur, stem)
        except Exception as e:
            raise FileIOError(filename, "read", str(e))
        if row is None:
            raise NoteNotFoundError(filename)
        return _row_to_note(*row)

    def write_note(
        self,
        filename: str,
        title: str,
        body: str,
        tags: list[str],
        created: str,
        *,
        actor: str = "unknown",
    ) -> Note:
        validate_filename(filename)
        stem = Path(filename).stem
        # Validate before touching the DB (pydantic ValueError propagates,
        # same contract as the filesystem backend).
        validated = NoteMetadata(title=title, tags=tags, created=created)
        try:
            with connect() as conn, conn.cursor() as cur:
                existing = self._read_row(cur, stem)
                cur.execute(
                    """
                    INSERT INTO notes (stem, title, body, tags, created, updated_at)
                    VALUES (%s, %s, %s, %s, %s, now())
                    ON CONFLICT (stem) DO UPDATE SET
                        title = EXCLUDED.title,
                        body = EXCLUDED.body,
                        tags = EXCLUDED.tags,
                        created = EXCLUDED.created,
                        updated_at = now()
                    """,
                    (stem, validated.title, body, validated.tags, validated.created),
                )
                insert_revision(
                    cur,
                    "update" if existing else "create",
                    NoteSnapshot(
                        stem=stem,
                        title=validated.title,
                        body=body,
                        tags=validated.tags,
                        created=validated.created,
                    ),
                    actor=actor,
                )
        except Exception as e:
            raise FileIOError(filename, "write", str(e))
        return Note(
            filename=stem,
            metadata=validated,
            body=body,
        )

    def list_notes(self) -> list[NoteMetadata]:
        try:
            with connect() as conn, conn.cursor() as cur:
                cur.execute("SELECT title, tags, created FROM notes")
                rows = cur.fetchall()
        except Exception as e:
            raise FileIOError("<list>", "read", str(e))
        notes = [
            NoteMetadata(title=title, tags=list(tags), created=c.isoformat() if hasattr(c, "isoformat") else c)
            for title, tags, c in rows
        ]
        return sorted(notes, key=lambda n: n.created)

    def delete_note(self, filename: str, *, actor: str = "unknown") -> None:
        validate_filename(filename)
        stem = Path(filename).stem
        try:
            with connect() as conn, conn.cursor() as cur:
                row = self._read_row(cur, stem)
                if row is None:
                    raise NoteNotFoundError(filename)
                _, title, body, tags, created = row
                created_str = created.isoformat() if hasattr(created, "isoformat") else created
                cur.execute("DELETE FROM notes WHERE stem = %s", (stem,))
                insert_revision(
                    cur,
                    "delete",
                    NoteSnapshot(
                        stem=stem, title=title, body=body,
                        tags=list(tags), created=created_str,
                    ),
                    actor=actor,
                )
        except NoteNotFoundError:
            raise
        except Exception as e:
            raise FileIOError(filename, "delete", str(e))

    def update_note(
        self,
        filename: str,
        title: str | None = None,
        body: str | None = None,
        tags: list[str] | None = None,
        created: str | None = None,
        *,
        actor: str = "unknown",
    ) -> Note:
        validate_filename(filename)
        existing = self.read_note(filename)

        new_title = title.strip() if title is not None else existing.metadata.title
        new_body = body if body is not None else existing.body
        new_tags = tags if tags is not None else existing.metadata.tags
        new_created = created if created is not None else existing.metadata.created

        # Validate immediately: pydantic ValueError propagates to tool layer.
        validated = NoteMetadata(title=new_title, tags=new_tags, created=new_created)

        if title is None:
            return self.write_note(
                filename, validated.title, new_body, validated.tags,
                validated.created, actor=actor,
            )

        new_stem = _slugify_stem(title)
        if new_stem is None:
            raise InvalidTypeError(filename, "title", "safe lowercase-with-hyphens .md", title)
        validate_filename(new_stem + ".md")

        old_stem = Path(filename).stem
        if new_stem == old_stem:
            return self.write_note(
                filename, validated.title, new_body, validated.tags,
                validated.created, actor=actor,
            )

        try:
            with connect() as conn, conn.cursor() as cur:
                if self._read_row(cur, new_stem) is not None:
                    raise FileExistsError(f"rename target '{new_stem}' already exists")
                cur.execute(
                    """
                    INSERT INTO notes (stem, title, body, tags, created, updated_at)
                    VALUES (%s, %s, %s, %s, %s, now())
                    """,
                    (new_stem, validated.title, new_body, validated.tags, validated.created),
                )
                cur.execute("DELETE FROM notes WHERE stem = %s", (old_stem,))
                insert_revision(
                    cur,
                    "rename",
                    NoteSnapshot(
                        stem=new_stem,
                        title=validated.title,
                        body=new_body,
                        tags=validated.tags,
                        created=validated.created,
                    ),
                    actor=actor,
                    old_stem=old_stem,
                )
        except FileExistsError:
            raise
        except Exception as e:
            raise FileIOError(new_stem + ".md", "write", str(e))

        return Note(filename=new_stem, metadata=validated, body=new_body)
