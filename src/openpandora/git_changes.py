"""Create fix branches and commits for OpenPandora changes."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

FIX_BRANCH_PREFIX = "openpandora/fix-"
MAX_FIX_ATTEMPTS = 4
PRIVATE_AGENT_PATHS = (".openpandora",)


class GitChangeError(RuntimeError):
    """Raised when OpenPandora cannot prepare fix branch changes."""


@dataclass(frozen=True)
class GitChangeResult:
    """Describe Git changes OpenPandora prepared."""

    branch_name: str
    commit_hash: str | None = None
    pushed: bool = False


@dataclass(frozen=True)
class FixAttemptPlan:
    """Describe the next safe fix attempt for one source branch."""

    branch_name: str
    attempt_number: int
    max_attempts: int


def create_fix_branch(
    branch_name: str,
    repo_path: str | Path = ".",
) -> str:
    """Create or reset a local fix branch from the current HEAD."""
    _run_git(["switch", "-C", branch_name], Path(repo_path))
    return branch_name


def switch_branch(
    branch_name: str,
    repo_path: str | Path = ".",
) -> str:
    """Switch back to an existing branch."""
    _run_git(["switch", branch_name], Path(repo_path))
    return branch_name


def build_fix_branch_name(source_branch: str, attempt_number: int = 1) -> str:
    """Build a predictable fix branch name from the source branch."""
    if attempt_number < 1:
        raise GitChangeError("Fix attempt numbers must be 1 or higher.")

    suffix = "" if attempt_number == 1 else f"-attempt-{attempt_number}"
    max_length = 90 - len(suffix)
    return _base_fix_branch_name(source_branch, max_length) + suffix


def is_openpandora_fix_branch(branch_name: str) -> bool:
    """Return whether a branch was created by OpenPandora."""
    return branch_name.startswith(FIX_BRANCH_PREFIX)


def plan_fix_attempt(
    source_branch: str,
    repo_path: str | Path = ".",
    *,
    max_attempts: int = MAX_FIX_ATTEMPTS,
) -> FixAttemptPlan | None:
    """Choose the next fix branch, stopping after repeated attempts."""
    if max_attempts < 1:
        raise GitChangeError("Fix attempt limits must be 1 or higher.")

    attempts = find_fix_attempts(source_branch, repo_path)
    last_attempt = max(attempts, default=0)
    if last_attempt >= max_attempts:
        return None

    next_attempt = last_attempt + 1
    return FixAttemptPlan(
        branch_name=build_fix_branch_name(source_branch, next_attempt),
        attempt_number=next_attempt,
        max_attempts=max_attempts,
    )


def find_fix_attempts(
    source_branch: str,
    repo_path: str | Path = ".",
) -> tuple[int, ...]:
    """Find existing OpenPandora fix attempts for a source branch."""
    attempts = {
        attempt
        for branch_name in _known_fix_branch_names(Path(repo_path))
        if (attempt := _parse_fix_attempt(source_branch, branch_name)) is not None
    }
    return tuple(sorted(attempts))


def has_worktree_changes(repo_path: str | Path = ".") -> bool:
    """Return whether there are staged, unstaged, or untracked changes."""
    output = _run_git(["status", "--porcelain"], Path(repo_path))
    return any(
        not _status_line_is_private_agent_path(line)
        for line in output.splitlines()
        if line.strip()
    )


def commit_all_changes(
    message: str,
    repo_path: str | Path = ".",
) -> str:
    """Commit all current changes with a readable message."""
    path = Path(repo_path)
    _run_git(["add", "-A", "--", ".", ":(exclude).openpandora"], path)
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


def _base_fix_branch_name(source_branch: str, max_length: int = 90) -> str:
    safe_name = "".join(
        character if character.isalnum() or character in {".", "_", "-"} else "-"
        for character in source_branch
    ).strip("-")
    if not safe_name:
        safe_name = "branch"
    return f"{FIX_BRANCH_PREFIX}{safe_name}"[:max_length]


def _parse_fix_attempt(source_branch: str, branch_name: str) -> int | None:
    normalized_names = _normalized_branch_names(branch_name)
    attempt_one_branch = build_fix_branch_name(source_branch, 1)
    for normalized_name in normalized_names:
        if normalized_name == attempt_one_branch:
            return 1

        _, separator, attempt_text = normalized_name.rpartition("-attempt-")
        if not separator or not attempt_text.isdigit():
            continue

        attempt_number = int(attempt_text)
        if normalized_name == build_fix_branch_name(source_branch, attempt_number):
            return attempt_number
    return None


def _known_fix_branch_names(repo_path: Path) -> tuple[str, ...]:
    output = _run_git(
        [
            "for-each-ref",
            "--format=%(refname:short)",
            "refs/heads",
            "refs/remotes",
        ],
        repo_path,
    )
    return tuple(line for line in output.splitlines() if line)


def _normalized_branch_names(branch_name: str) -> tuple[str, ...]:
    names = [branch_name]
    _, separator, remote_branch_name = branch_name.partition("/")
    if separator and remote_branch_name.startswith(FIX_BRANCH_PREFIX):
        names.append(remote_branch_name)
    return tuple(names)


def _status_line_is_private_agent_path(line: str) -> bool:
    paths = line[3:].split(" -> ")
    return all(_is_private_agent_path(path) for path in paths if path)


def _is_private_agent_path(path: str) -> bool:
    normalized_path = path.strip('"')
    return any(
        normalized_path == private_path
        or normalized_path.startswith(f"{private_path}/")
        for private_path in PRIVATE_AGENT_PATHS
    )


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
