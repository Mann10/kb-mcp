"""Note-history seam (V2-01).

Every note mutation records history. The filesystem backend keeps its dulwich
git commits (unchanged behavior); the Supabase backend inserts revision rows.
Both implement :class:`NoteHistory`, so storage code depends on the seam,
not on git.

Snapshot rule: revisions carry the full note state after the mutation (and the
pre-delete state for deletes), so any revision alone is sufficient for recovery.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class NoteSnapshot:
    """Immutable note state captured for one history entry."""

    stem: str
    title: str
    body: str
    tags: list[str]
    created: str


class NoteHistory(Protocol):
    """Record history for one note mutation."""

    def record(
        self,
        action: str,
        snapshot: NoteSnapshot,
        *,
        actor: str,
        old_stem: str | None = None,
    ) -> None:
        """Record ``action`` (create|update|delete|rename) for ``snapshot``.

        ``actor`` is the token owner performing the mutation (``"unknown"``
        when unattributed). ``old_stem`` carries the pre-rename stem for
        renames only.
        """
        ...


class DulwichHistory:
    """Git-backed history for filesystem runs (v1 behavior, unchanged)."""

    def __init__(self, notes_dir: Path | str):
        self.notes_dir = str(notes_dir)

    def record(
        self,
        action: str,
        snapshot: NoteSnapshot,
        *,
        actor: str,
        old_stem: str | None = None,
    ) -> None:
        from .git_history import (
            commit_note_deletion,
            commit_note_file,
            commit_note_rename,
        )

        filename = snapshot.stem + ".md"
        if action in ("create", "update"):
            commit_note_file(self.notes_dir, filename, action)
        elif action == "delete":
            commit_note_deletion(self.notes_dir, filename)
        elif action == "rename":
            if old_stem is None:
                raise ValueError("rename requires old_stem")
            commit_note_rename(self.notes_dir, old_stem + ".md", filename)
        else:
            raise ValueError(f"unknown history action: {action!r}")


class SupabaseHistory:
    """Revision-row history for the Supabase backend (no git on serverless)."""

    def record(
        self,
        action: str,
        snapshot: NoteSnapshot,
        *,
        actor: str,
        old_stem: str | None = None,
    ) -> None:
        from .db import connect

        with connect() as conn, conn.cursor() as cur:
            insert_revision(cur, action, snapshot, actor=actor, old_stem=old_stem)


def insert_revision(cur, action: str, snapshot: NoteSnapshot, *, actor: str, old_stem: str | None = None) -> None:
    """Insert one revision row on an existing cursor (shares the caller's transaction).

    Repositories use this so the note row and its revision commit atomically.
    """
    if action not in ("create", "update", "delete", "rename"):
        raise ValueError(f"unknown history action: {action!r}")
    new_stem = snapshot.stem if action == "rename" else None
    cur.execute(
        """
        INSERT INTO note_revisions
            (stem, action, old_stem, new_stem, title, body, tags, created, actor)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            snapshot.stem,
            action,
            old_stem,
            new_stem,
            snapshot.title,
            snapshot.body,
            snapshot.tags,
            snapshot.created,
            actor,
        ),
    )
