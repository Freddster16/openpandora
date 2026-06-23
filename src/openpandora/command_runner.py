"""Run local project commands and keep their output explainable."""

from __future__ import annotations

import shlex
import shutil
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CommandResult:
    """Describe the result of one local project command."""

    name: str
    command: str
    return_code: int
    stdout: str
    stderr: str

    @property
    def passed(self) -> bool:
        """Return whether the command finished successfully."""
        return self.return_code == 0


def run_project_command(
    name: str,
    command: str,
    repo_path: str | Path = ".",
    timeout_seconds: int = 120,
) -> CommandResult:
    """Run one configured command without invoking a shell."""
    arguments = _split_command(command)
    if not arguments:
        return CommandResult(
            name=name,
            command=command,
            return_code=2,
            stdout="",
            stderr="Command is empty.",
        )

    try:
        result = subprocess.run(
            arguments,
            cwd=Path(repo_path),
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout_seconds,
        )
    except FileNotFoundError:
        return CommandResult(
            name=name,
            command=command,
            return_code=127,
            stdout="",
            stderr=f"Command not found: {arguments[0]}",
        )
    except subprocess.TimeoutExpired as error:
        return CommandResult(
            name=name,
            command=command,
            return_code=124,
            stdout=error.stdout or "",
            stderr=f"Command timed out after {timeout_seconds} seconds.",
        )

    return CommandResult(
        name=name,
        command=command,
        return_code=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )


def run_project_commands(
    commands: Sequence[tuple[str, str]],
    repo_path: str | Path = ".",
) -> tuple[CommandResult, ...]:
    """Run configured commands in order so failures are easy to read."""
    return tuple(
        run_project_command(name, command, repo_path) for name, command in commands
    )


def _split_command(command: str) -> list[str]:
    arguments = shlex.split(command)
    if not arguments:
        return arguments

    arguments[0] = _resolve_executable(arguments[0])
    return arguments


def _resolve_executable(executable: str) -> str:
    if executable == "python":
        return sys.executable

    if shutil.which(executable):
        return executable

    sibling_executable = Path(sys.executable).parent / executable
    if sibling_executable.exists():
        return str(sibling_executable)

    return executable
