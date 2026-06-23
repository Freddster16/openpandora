"""Create fix branches and commits for OpenPandora changes."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

FIX_BRANCH_PREFIX = "openpandora/fix-"


class GitChangeError(RuntimeError):
    """Raised when OpenPandora cannot prepare fix branch changes."""


@dataclass(frozen=True)
class GitChangeResult:
    """Describe Git changes OpenPandora prepared."""

    branch_name: str
    commit_hash: str | None = None
    pushed: bool = False


def create_fix_branch(
    branch_name: str,
    repo_path: str | Path = ".",
) -> str:
    """Create or reset a local fix branch from the current HEAD."""
    _run_git(["switch", "-C", branch_name], Path(repo_path))
    return branch_name


def build_fix_branch_name(source_branch: str) -> str:
    """Build a predictable fix branch name from the source branch."""
    safe_name = "".join(
        character if character.isalnum() or character in {".", "_", "-"} else "-"
        for character in source_branch
    ).strip("-")
    if not safe_name:
        safe_name = "branch"
    return f"{FIX_BRANCH_PREFIX}{safe_name}"[:90]


def has_worktree_changes(repo_path: str | Path = ".") -> bool:
    """Return whether there are staged, unstaged, or untracked changes."""
    output = _run_git(["status", "--porcelain"], Path(repo_path))
    return bool(output.strip())


def commit_all_changes(
    message: str,
    repo_path: str | Path = ".",
) -> str:
    """Commit all current changes with a readable message."""
    path = Path(repo_path)
    _run_git(["add", "-A"], path)
    if not has_staged_changes(path):
        raise GitChangeError("There are no changes to commit.")
    _run_git(["commit", "-m", message], path)
    return _run_git(["rev-parse", "HEAD"], path)


def has_staged_changes(repo_path: str | Path = ".") -> bool:
    """Return whether Git has staged changes ready to commit."""
    result = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=Path(repo_path),
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode == 0:
        return False
    if result.returncode == 1:
        return True
    reason = result.stderr.strip() or result.stdout.strip() or "unknown Git error"
    raise GitChangeError(reason)


def push_branch(
    branch_name: str,
    repo_path: str | Path = ".",
    remote: str = "origin",
) -> GitChangeResult:
    """Push a local fix branch to GitHub."""
    _run_git(["push", "--set-upstream", remote, branch_name], Path(repo_path))
    return GitChangeResult(branch_name=branch_name, pushed=True)


def _run_git(arguments: list[str], repo_path: Path) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=repo_path,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        reason = result.stderr.strip() or result.stdout.strip() or "unknown Git error"
        raise GitChangeError(f"Git command failed: git {' '.join(arguments)}\n{reason}")
    return result.stdout.strip()
