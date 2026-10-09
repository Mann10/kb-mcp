"""Real-git tests for STOR-03 automatic note versioning (V-1..V-8).

Every test runs real dulwich against a per-test isolated ``tmp_path`` repo
(D-16/D-17) via the existing ``notes_dir``/``repository`` fixtures — repos are
never shared across tests/workers and no git-on-PATH skip guards are needed.
Assertions are branch-agnostic (default branch is ``master``, Pitfall P-9):
history is read via ``Repo.get_walker`` and ``repo.head()`` SHA, and every
explicitly opened ``Repo`` is closed immediately (Windows handle hygiene,
Pitfall P-7). Untracked-noise assertions are scoped to ``staged`` only so the
``.gitignore`` untracked entry never trips them (Pitfall P-5).
"""

import io
import logging

from dulwich import porcelain
from dulwich.repo import Repo


def _walker_entries(notes_dir):
    """Return newest-first [(message, author, committer)] list; closes Repo."""
    repo = Repo(str(notes_dir))
    try:
        return [
            (
                e.commit.message.decode().strip(),
                e.commit.author.decode(),
                e.commit.committer.decode(),
            )
            for e in repo.get_walker(max_entries=10)
        ]
    finally:
        repo.close()


def _walker_count(notes_dir):
    repo = Repo(str(notes_dir))
    try:
        return len(list(repo.get_walker(max_entries=10)))
    finally:
        repo.close()


def test_create_commits(repository, notes_dir):
    """V-1/SC-1: creating a note produces exactly one note(create) commit."""
    repository.write_note("my-note.md", "My Note", "hello body", ["t"], "2026-10-09")

    repo = Repo(str(notes_dir))
    try:
        entries = list(repo.get_walker(max_entries=10))
        assert len(entries) == 1
        commit = entries[0].commit
        assert commit.message.decode().strip() == "note(create): my-note"
        assert commit.author.decode() == "kb-mcp <kb-mcp@localhost>"
        assert commit.committer.decode() == "kb-mcp <kb-mcp@localhost>"
        assert repo.head() == commit.id
    finally:
        repo.close()


def test_update_commits(repository, notes_dir):
    """V-2/SC-2: rewriting a note produces a note(update) commit with changes."""
    repository.write_note("my-note.md", "My Note", "v1 body", [], "2026-10-09")
    repository.write_note("my-note.md", "My Note", "v2 body", [], "2026-10-09")

    repo = Repo(str(notes_dir))
    try:
        entries = list(repo.get_walker(max_entries=10))
        assert len(entries) == 2
        newest, oldest = entries[0].commit, entries[1].commit
        assert newest.message.decode().strip() == "note(update): my-note"
        assert oldest.message.decode().strip() == "note(create): my-note"
        new_tree = repo[newest.tree]
        old_tree = repo[oldest.tree]
        assert new_tree[b"my-note.md"][1] != old_tree[b"my-note.md"][1]
    finally:
        repo.close()


def test_delete_commits(repository, notes_dir):
    """V-3/SC-3: deleting a note commits the removal (file gone from HEAD)."""
    repository.write_note("gone.md", "Gone", "body", [], "2026-10-09")
    repository.delete_note("gone.md")

    repo = Repo(str(notes_dir))
    try:
        entries = list(repo.get_walker(max_entries=10))
        assert len(entries) == 2
        assert entries[0].commit.message.decode().strip() == "note(delete): gone"
        head_commit = repo[repo.head()]
        head_tree = repo[head_commit.tree]
        paths = [p for p, _mode, _sha in head_tree.items()]
        assert b"gone.md" not in paths
    finally:
        repo.close()

    staged = porcelain.status(str(notes_dir)).staged
    assert not (staged["add"] or staged["delete"] or staged["modify"])


def test_audit_trail_order(repository, notes_dir):
    """V-4/SC-4: walker shows reverse-chronological audit trail; log is readable."""
    repository.write_note("note-a.md", "A", "a1", [], "2026-10-09")
    # update via update_note (not write_note) to prove D-06 delegation commits.
    repository.update_note("note-a.md", body="a2")
    repository.write_note("note-b.md", "B", "b1", [], "2026-10-09")

    messages = [m for m, _a, _c in _walker_entries(notes_dir)]
    assert messages == [
        "note(create): note-b",
        "note(update): note-a",
        "note(create): note-a",
    ]

    # Human-readability smoke: porcelain.log renders the same messages as text.
    buf = io.StringIO()
    porcelain.log(str(notes_dir), outstream=buf, max_entries=10)
    text = buf.getvalue()
    assert "note(create): note-a" in text
    assert "note(update): note-a" in text
    assert "note(create): note-b" in text


def test_single_file_scope(repository, notes_dir):
    """V-5/D-05: each commit stages only its target file (no cross-file bleed)."""
    repository.write_note("note-a.md", "A", "a1", [], "2026-10-09")
    staged = porcelain.status(str(notes_dir)).staged
    assert not (staged["add"] or staged["delete"] or staged["modify"])

    repository.write_note("note-b.md", "B", "b1", [], "2026-10-09")

    repo = Repo(str(notes_dir))
    try:
        entries = list(repo.get_walker(max_entries=10))
        assert len(entries) == 2
        # Second commit's tree still contains note-a byte-identical: B's commit
        # did not restage or alter A.
        b_tree = repo[entries[0].commit.tree]
        a_tree = repo[entries[1].commit.tree]
        assert b_tree[b"note-a.md"][1] == a_tree[b"note-a.md"][1]
        assert b_tree[b"note-b.md"][1] is not None
    finally:
        repo.close()


def test_fail_open(repository, notes_dir, monkeypatch, caplog):
    """V-6/D-13/D-14: poisoned git never fails the write or delete (fail-open)."""

    def _boom(*args, **kwargs):
        raise RuntimeError("boom")

    # Valid target: 02-01 exposes module-level porcelain for monkeypatching.
    monkeypatch.setattr("kb_mcp.git_history.porcelain.commit", _boom)

    with caplog.at_level(logging.WARNING, logger="kb_mcp.git_history"):
        repository.write_note("fragile.md", "Fragile", "important body", ["t"], "2026-10-09")
        assert (notes_dir / "fragile.md").exists()
        assert "important body" in (notes_dir / "fragile.md").read_text(encoding="utf-8")

        repository.delete_note("fragile.md")
        assert not (notes_dir / "fragile.md").exists()

    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert warnings, "expected fail-open WARNING logs for poisoned commits"
    assert any("fragile.md" in r.getMessage() for r in warnings)


def test_list_ignores_git_dir(repository, notes_dir):
    """V-7/D-11: list_notes() sees only notes; the .git dir is invisible."""
    repository.write_note("one.md", "One", "b1", [], "2026-10-09")
    repository.write_note("two.md", "Two", "b2", [], "2026-10-09")

    assert (notes_dir / ".git").is_dir()
    assert len(repository.list_notes()) == 2


def test_no_empty_commit(repository, notes_dir):
    """V-8/P-2: identical-content update creates no commit (empty-commit guard)."""
    repository.write_note("steady.md", "Steady", "same body", ["t"], "2026-10-09")
    assert _walker_count(notes_dir) == 1

    repository.update_note("steady.md", body="same body")
    assert _walker_count(notes_dir) == 1
