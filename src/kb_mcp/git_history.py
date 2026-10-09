"""Fail-open dulwich collaborator for note git history (STOR-03).

All storage hooks call into this module. Git is auxiliary: the filesystem
remains the source of truth, so every public function fails open — any git
error is logged as a warning with filename context and never raised.

History model is history-from-first-change (D-12 discretion): pre-existing
notes are NOT bulk-committed at repo init. Each note's first post-upgrade
edit stages and commits it via its normal write hook, so no extra code or
one-commit-per-note bulk loop is needed (a bulk ``note(init)`` commit would
also violate one-file-per-commit D-05).
"""

import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)

AUTHOR = b"kb-mcp <kb-mcp@localhost>"
COMMITTER = b"kb-mcp <kb-mcp@localhost>"

try:
    from dulwich import porcelain
    from dulwich.repo import Repo
    from dulwich.errors import NotGitRepository
    from dulwich.file import FileLocked
except ImportError:
    porcelain = Repo = NotGitRepository = FileLocked = None


def ensure_repo(repo_path: str) -> None:
    """Lazily init a git repo at ``repo_path`` if none exists (D-10).

    Guarded by ``NotGitRepository`` (never blind init: re-init raises
    ``FileExistsError``). A lost init race (two processes init at once) is
    tolerated via ``FileExistsError`` -> pass. Writes ``.gitignore`` with
    ``*.tmp`` so crash-residue atomic-write temp files are never stageable.
    """
    if porcelain is None:
        logger.warning("dulwich unavailable, skipping git init for %s", repo_path)
        return
    try:
        Repo(str(repo_path)).close()
    except NotGitRepository:
        try:
            porcelain.init(str(repo_path))
        except FileExistsError:
            pass  # lost the init race; repo exists now
    gitignore = Path(repo_path) / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text("*.tmp\n", encoding="utf-8")


def commit_note_file(repo_path: str, filename: str, action: str) -> None:
    """Stage a single written file and commit. Never raises (D-13)."""
    try:
        if porcelain is None:
            logger.warning("dulwich unavailable, skipping git commit for %s", filename)
            return
        repo_arg = str(repo_path)
        ensure_repo(repo_arg)
        try:
            porcelain.add(repo_arg, paths=[filename])
        except FileLocked:
            time.sleep(0.1)
            porcelain.add(repo_arg, paths=[filename])
        staged = porcelain.status(repo_arg).staged
        if not (staged["add"] or staged["delete"] or staged["modify"]):
            return
        porcelain.commit(
            repo_arg,
            message=f"note({action}): {Path(filename).stem}".encode(),
            author=AUTHOR,
            committer=COMMITTER,
        )
    except Exception as e:  # noqa: BLE001 — fail-open is the spec (D-13)
        logger.warning("git commit failed for %s: %s: %s", filename, type(e).__name__, e)


def commit_note_deletion(repo_path: str, filename: str) -> None:
    """Stage a single deletion and commit. Never raises (D-13)."""
    try:
        if porcelain is None:
            logger.warning("dulwich unavailable, skipping git commit for %s", filename)
            return
        repo_arg = str(repo_path)
        ensure_repo(repo_arg)
        try:
            porcelain.remove(repo_arg, paths=[filename])
        except FileLocked:
            time.sleep(0.1)
            porcelain.remove(repo_arg, paths=[filename])
        staged = porcelain.status(repo_arg).staged
        if not (staged["add"] or staged["delete"] or staged["modify"]):
            return
        porcelain.commit(
            repo_arg,
            message=f"note(delete): {Path(filename).stem}".encode(),
            author=AUTHOR,
            committer=COMMITTER,
        )
    except Exception as e:  # noqa: BLE001 — fail-open is the spec (D-13)
        logger.warning("git commit failed for %s: %s: %s", filename, type(e).__name__, e)
