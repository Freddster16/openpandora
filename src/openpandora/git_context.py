"""Collect small pieces of Git context for QA checks."""

from __future__ import annotations

import re
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

HUNK_HEADER_PATTERN = re.compile(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


@dataclass(frozen=True)
class ChangedLine:
    """Describe one added line from a Git diff."""

    file_path: str
    line_number: int
    content: str


@dataclass(frozen=True)
class RepoContext:
    """Describe the current commit so QA can explain what it checked."""

    branch_name: str
    current_commit: str
    changed_files: tuple[str, ...]
    changed_lines: tuple[ChangedLine, ...] = ()
    base_ref: str | None = None


class GitCommandError(RuntimeError):
    """Raised when OpenPandora cannot read Git context safely."""


def collect_repo_context(
    repo_path: str | Path = ".", since_ref: str | None = None
) -> RepoContext:
    """Collect branch, commit, and changed files from the current Git repo."""
    path = Path(repo_path)
    branch_name = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], path)
    current_commit = _run_git(["rev-parse", "HEAD"], path)
    changed_files = _changed_files(path, since_ref)
    changed_lines = _changed_lines(path, since_ref)

    return RepoContext(
        branch_name=branch_name,
        current_commit=current_commit,
        changed_files=changed_files,
        changed_lines=changed_lines,
        base_ref=since_ref,
    )


def _changed_files(repo_path: Path, since_ref: str | None) -> tuple[str, ...]:
    if since_ref is not None:
        output = _run_git(["diff", "--name-only", f"{since_ref}...HEAD"], repo_path)
        return tuple(line for line in output.splitlines() if line)

    output = _run_git(
        ["diff-tree", "--root", "--no-commit-id", "--name-only", "-r", "HEAD"],
        repo_path,
    )
    return tuple(line for line in output.splitlines() if line)


def _changed_lines(repo_path: Path, since_ref: str | None) -> tuple[ChangedLine, ...]:
    if since_ref is not None:
        output = _run_git(["diff", "--unified=0", f"{since_ref}...HEAD"], repo_path)
    else:
        output = _run_git(["show", "--format=", "--unified=0", "HEAD"], repo_path)
    return _parse_changed_lines(output)


def _parse_changed_lines(diff_text: str) -> tuple[ChangedLine, ...]:
    changed_lines: list[ChangedLine] = []
    current_file: str | None = None
    current_line: int | None = None

    for line in diff_text.splitlines():
        if line.startswith("+++ "):
            current_file = _parse_new_file_path(line)
            current_line = None
            continue

        if line.startswith("@@ "):
            match = HUNK_HEADER_PATTERN.search(line)
            current_line = int(match.group(1)) if match else None
            continue

        if current_file is None or current_line is None:
            continue

        if line.startswith("+") and not line.startswith("+++"):
            changed_lines.append(
                ChangedLine(
                    file_path=current_file,
                    line_number=current_line,
                    content=line[1:],
                )
            )
            current_line += 1
        elif not line.startswith("-"):
            current_line += 1

    return tuple(changed_lines)


def _parse_new_file_path(line: str) -> str | None:
    path = line.removeprefix("+++ ")
    if path == "/dev/null":
        return None
    return path.removeprefix("b/")


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
