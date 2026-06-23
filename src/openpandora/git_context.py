"""Collect small pieces of Git context for QA checks."""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RepoContext:
    """Describe the current commit so QA can explain what it checked."""

    branch_name: str
    current_commit: str
    changed_files: tuple[str, ...]


class GitCommandError(RuntimeError):
    """Raised when OpenPandora cannot read Git context safely."""


def collect_repo_context(repo_path: str | Path = ".") -> RepoContext:
    """Collect branch, commit, and changed files from the current Git repo."""
    path = Path(repo_path)
    branch_name = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], path)
    current_commit = _run_git(["rev-parse", "HEAD"], path)
    changed_files = _changed_files_for_commit(path)

    return RepoContext(
        branch_name=branch_name,
        current_commit=current_commit,
        changed_files=changed_files,
    )


def _changed_files_for_commit(repo_path: Path) -> tuple[str, ...]:
    output = _run_git(
        ["diff-tree", "--root", "--no-commit-id", "--name-only", "-r", "HEAD"],
        repo_path,
    )
    return tuple(line for line in output.splitlines() if line)


def _run_git(arguments: Sequence[str], repo_path: Path) -> str:
    command = ["git", *arguments]
    result = subprocess.run(
        command,
        cwd=repo_path,
        text=True,
        capture_output=True,
        check=False,
    )

    if result.returncode != 0:
        reason = result.stderr.strip() or result.stdout.strip() or "unknown Git error"
        raise GitCommandError(
            f"Git command failed: git {' '.join(arguments)}\n{reason}"
        )

    return result.stdout.strip()
