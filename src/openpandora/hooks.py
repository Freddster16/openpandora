"""Install Git hooks that wake OpenPandora on Git events."""

from __future__ import annotations

import os
import shlex
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path

HOOK_MARKER = "# OpenPandora managed hook"
CONFIG_HOME_ENV_VAR = "OPENPANDORA_CONFIG_HOME"
HOOK_COMMAND_ENV_VAR = "OPENPANDORA_HOOK_COMMAND"


class HookError(RuntimeError):
    """Raised when OpenPandora cannot install or inspect Git hooks."""


@dataclass(frozen=True)
class HookInstallResult:
    """Describe Git hooks installed for one repository."""

    hooks_dir: Path
    post_commit_hook: Path
    pre_push_hook: Path
    create_pr: bool


@dataclass(frozen=True)
class GlobalHookInstallResult:
    """Describe computer-wide Git hooks installed for all repositories."""

    hooks_dir: Path
    post_commit_hook: Path
    pre_push_hook: Path
    previous_hooks_path: str | None = None


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


def install_global_git_hooks(
    *,
    executable: str = "openpandora",
    hooks_dir: str | Path | None = None,
) -> GlobalHookInstallResult:
    """Install one global Git hooks path so every repo can wake OpenPandora."""
    resolved_hooks_dir = Path(hooks_dir) if hooks_dir else _default_global_hooks_dir()
    resolved_hooks_dir.mkdir(parents=True, exist_ok=True)

    current_hooks_path = _current_global_hooks_path()
    previous_hooks_path = (
        current_hooks_path
        if current_hooks_path
        and Path(current_hooks_path).expanduser() != resolved_hooks_dir
        else None
    )

    post_commit_hook = resolved_hooks_dir / "post-commit"
    pre_push_hook = resolved_hooks_dir / "pre-push"
    _write_managed_hook(
        post_commit_hook,
        _global_hook_script(executable, "commit", previous_hooks_path),
    )
    _write_managed_hook(
        pre_push_hook,
        _global_hook_script(executable, "push", previous_hooks_path),
    )
    _run_git_config(["--global", "core.hooksPath", str(resolved_hooks_dir)])

    return GlobalHookInstallResult(
        hooks_dir=resolved_hooks_dir,
        post_commit_hook=post_commit_hook,
        pre_push_hook=pre_push_hook,
        previous_hooks_path=previous_hooks_path,
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
    executable_text = shlex.quote(executable)
    return (
        "#!/bin/sh\n"
        f"{HOOK_MARKER}\n"
        f"exec {executable_text} wake --event {event}{create_pr_flag}\n"
    )


def _global_hook_script(
    executable: str,
    event: str,
    previous_hooks_path: str | None,
) -> str:
    executable_text = shlex.quote(executable)
    previous_hooks_text = shlex.quote(previous_hooks_path or "")
    hook_name = "pre-push" if event == "push" else "post-commit"
    return f"""#!/bin/sh
{HOOK_MARKER}
event={shlex.quote(event)}
hook_name={shlex.quote(hook_name)}
openpandora_command={executable_text}
previous_hooks_path={previous_hooks_text}
status=0
input_file=""

cleanup() {{
  if [ -n "$input_file" ]; then
    rm -f "$input_file"
  fi
}}
trap cleanup EXIT HUP INT TERM

if [ "$event" = "push" ]; then
  input_file="$(mktemp "${{TMPDIR:-/tmp}}/openpandora-hook.XXXXXX")" || exit 1
  cat > "$input_file"
fi

run_with_input() {{
  if [ -n "$input_file" ]; then
    "$@" < "$input_file"
  else
    "$@"
  fi
}}

run_hook_file() {{
  hook_path="$1"
  shift
  if [ -z "$hook_path" ] || [ ! -x "$hook_path" ]; then
    return 0
  fi
  if grep -q "{HOOK_MARKER}" "$hook_path" 2>/dev/null; then
    return 0
  fi
  run_with_input "$hook_path" "$@" || return $?
  return 0
}}

hook_from_dir() {{
  hook_dir="$1"
  repo_root="$2"
  case "$hook_dir" in
    "~") printf "%s/%s" "$HOME" "$hook_name" ;;
    "~/"*) printf "%s/%s/%s" "$HOME" "${{hook_dir#\\~/}}" "$hook_name" ;;
    /*) printf "%s/%s" "$hook_dir" "$hook_name" ;;
    *) printf "%s/%s/%s" "$repo_root" "$hook_dir" "$hook_name" ;;
  esac
}}

run_with_input "$openpandora_command" wake --event "$event" || status=$?

repo_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
common_dir="$(git rev-parse --git-common-dir 2>/dev/null || true)"
local_hook=""
if [ -n "$common_dir" ]; then
  local_hook="$(hook_from_dir "$common_dir/hooks" "$repo_root")"
  run_hook_file "$local_hook" "$@" || status=$?
fi

if [ -n "$previous_hooks_path" ]; then
  previous_hook="$(hook_from_dir "$previous_hooks_path" "$repo_root")"
  if [ "$previous_hook" != "$local_hook" ]; then
    run_hook_file "$previous_hook" "$@" || status=$?
  fi
fi

exit "$status"
"""


def _default_global_hooks_dir() -> Path:
    configured_home = os.environ.get(CONFIG_HOME_ENV_VAR)
    if configured_home:
        return Path(configured_home) / "openpandora" / "git-hooks"

    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config_home:
        return Path(xdg_config_home) / "openpandora" / "git-hooks"

    return Path.home() / ".config" / "openpandora" / "git-hooks"


def _current_global_hooks_path() -> str | None:
    result = _run_git_config_result(["--global", "--get", "core.hooksPath"])
    if result.returncode == 1:
        return None
    if result.returncode != 0:
        reason = result.stderr.strip() or result.stdout.strip() or "unknown Git error"
        raise HookError(
            f"Git command failed: git config --global --get core.hooksPath\n{reason}"
        )
    return result.stdout.strip() or None


def _run_git_config(arguments: list[str]) -> str:
    result = _run_git_config_result(arguments)
    if result.returncode != 0:
        reason = result.stderr.strip() or result.stdout.strip() or "unknown Git error"
        raise HookError(
            f"Git command failed: git config {' '.join(arguments)}\n{reason}"
        )
    return result.stdout.strip()


def _run_git_config_result(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "config", *arguments],
        text=True,
        capture_output=True,
        check=False,
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
