"""Install repo-local Git hooks that wake OpenPandora on Git events."""

from __future__ import annotations

import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path

HOOK_MARKER = "# OpenPandora managed hook"


class HookError(RuntimeError):
    """Raised when OpenPandora cannot install or inspect Git hooks."""


@dataclass(frozen=True)
class HookInstallResult:
    """Describe Git hooks installed for one repository."""

    hooks_dir: Path
    post_commit_hook: Path
    pre_push_hook: Path
    create_pr: bool


def install_git_hooks(
    repo_path: str | Path = ".",
    *,
    create_pr: bool = False,
    executable: str = "openpandora",
) -> HookInstallResult:
    """Install post-commit and pre-push hooks for the current repository."""
    root_path = Path(repo_path)
    hooks_dir = _git_hooks_dir(root_path)
    hooks_dir.mkdir(parents=True, exist_ok=True)

    post_commit_hook = hooks_dir / "post-commit"
    pre_push_hook = hooks_dir / "pre-push"
    _write_managed_hook(
        post_commit_hook,
        _hook_script(executable, "commit", create_pr),
    )
    _write_managed_hook(
        pre_push_hook,
        _hook_script(executable, "push", create_pr),
    )

    return HookInstallResult(
        hooks_dir=hooks_dir,
        post_commit_hook=post_commit_hook,
        pre_push_hook=pre_push_hook,
        create_pr=create_pr,
    )


def is_git_repo(repo_path: str | Path = ".") -> bool:
    """Return whether the path is inside a Git repository."""
    result = subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        cwd=Path(repo_path),
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def _git_hooks_dir(repo_path: Path) -> Path:
    git_dir = _run_git(["rev-parse", "--git-dir"], repo_path)
    git_dir_path = Path(git_dir)
    if not git_dir_path.is_absolute():
        git_dir_path = repo_path / git_dir_path
    return git_dir_path / "hooks"


def _write_managed_hook(path: Path, content: str) -> None:
    if path.exists():
        existing = path.read_text()
        if HOOK_MARKER not in existing:
            raise HookError(
                f"{path} already exists and was not created by OpenPandora."
            )

    path.write_text(content)
    current_mode = path.stat().st_mode
    path.chmod(current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _hook_script(executable: str, event: str, create_pr: bool) -> str:
    create_pr_flag = " --create-pr" if create_pr else ""
    return (
        "#!/bin/sh\n"
        f"{HOOK_MARKER}\n"
        f'exec "{executable}" wake --event {event}{create_pr_flag}\n'
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
        raise HookError(f"Git command failed: git {' '.join(arguments)}\n{reason}")
    return result.stdout.strip()
