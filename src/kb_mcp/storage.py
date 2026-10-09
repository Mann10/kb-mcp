"""NoteRepository class with full CRUD operations and atomic writes."""

import os
from io import StringIO
from pathlib import Path

from ruamel.yaml import YAML

from .errors import FileIOError, NoteNotFoundError
from .models import Note, NoteMetadata
from .parsing import parse_frontmatter
from .validation import validate_filename, validate_path


def _build_note_content(title: str, tags: list[str], created: str, body: str) -> str:
    yaml = YAML()
    yaml.preserve_quotes = True
    stream = StringIO()
    data = {"title": title, "tags": tags, "created": created}
    yaml.dump(data, stream)
    yaml_text = stream.getvalue()
    return f"---\n{yaml_text}---\n{body}"


def _atomic_write(path: Path, content: str) -> None:
    temp_path = path.with_suffix(".tmp")
    try:
        temp_path.write_text(content, encoding="utf-8")
        os.replace(temp_path, path)
    except Exception as e:
        if temp_path.exists():
            temp_path.unlink()
        raise


class NoteRepository:
    """Repository for note CRUD operations with atomic writes."""

    def __init__(self, notes_dir: Path | None = None):
        if notes_dir is None:
            notes_dir_str = os.environ.get("NOTES_DIR")
            if notes_dir_str:
                notes_dir = Path(notes_dir_str)
            else:
                notes_dir = Path.home() / "knowledge-base" / "notes"
        self.notes_dir = notes_dir.resolve()
        self.notes_dir.mkdir(parents=True, exist_ok=True)

    def read_note(self, filename: str) -> Note:
        path = validate_path(self.notes_dir, filename)
        validate_filename(filename)

        if not path.exists():
            raise NoteNotFoundError(filename)

        content = path.read_text(encoding="utf-8-sig")
        metadata, body = parse_frontmatter(content, filename)

        return Note(filename=path.stem, metadata=metadata, body=body)

    def write_note(
        self,
        filename: str,
        title: str,
        body: str,
        tags: list[str],
        created: str,
    ) -> Note:
        validate_path(self.notes_dir, filename)
        validate_filename(filename)
        path = validate_path(self.notes_dir, filename)

        existed = path.exists()
        content = _build_note_content(title, tags, created, body)

        try:
            _atomic_write(path, content)
        except Exception as e:
            raise FileIOError(filename, "write", str(e))

        from .git_history import commit_note_file

        commit_note_file(str(self.notes_dir), filename, "update" if existed else "create")

        metadata = NoteMetadata(title=title, tags=tags, created=created)
        return Note(filename=path.stem, metadata=metadata, body=body)

    def list_notes(self) -> list[NoteMetadata]:
        notes: list[NoteMetadata] = []
        for file in self.notes_dir.iterdir():
            if not file.is_file():
                continue
            if file.suffix != ".md":
                continue
            try:
                content = file.read_text(encoding="utf-8-sig")
                metadata, _ = parse_frontmatter(content, file.name)
                notes.append(metadata)
            except Exception:
                continue
        return sorted(notes, key=lambda n: n.created)

    def delete_note(self, filename: str) -> None:
        validate_path(self.notes_dir, filename)
        validate_filename(filename)
        path = validate_path(self.notes_dir, filename)

        if not path.exists():
            raise NoteNotFoundError(filename)

        try:
            path.unlink()
        except Exception as e:
            raise FileIOError(filename, "delete", str(e))

        from .git_history import commit_note_deletion

        commit_note_deletion(str(self.notes_dir), filename)

    def update_note(
        self,
        filename: str,
        title: str | None = None,
        body: str | None = None,
        tags: list[str] | None = None,
        created: str | None = None,
    ) -> Note:
        existing = self.read_note(filename)

        new_title = title if title is not None else existing.metadata.title
        new_body = body if body is not None else existing.body
        new_tags = tags if tags is not None else existing.metadata.tags
        new_created = created if created is not None else existing.metadata.created

        return self.write_note(filename, new_title, new_body, new_tags, new_created)
