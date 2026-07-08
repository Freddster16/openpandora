"""Prepare GitHub CLI auth for local pull request creation."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

GITHUB_COMMAND_ENV_VAR = "OPENPANDORA_GH_COMMAND"
GITHUB_TOKEN_ENV_VAR = "GITHUB_TOKEN"
GITHUB_HOSTNAME = "github.com"

OutputFunc = Callable[[str], None]
Runner = Callable[..., Any]


class GitHubCliAuthError(RuntimeError):
    """Raised when GitHub CLI auth cannot be prepared."""


class GitHubCliMissingError(GitHubCliAuthError):
    """Raised when the GitHub CLI command is not available."""


@dataclass(frozen=True)
class GitHubCliAuthResult:
    """Describe how OpenPandora can create GitHub pull requests."""

    command: str
    already_signed_in: bool
    used_token: bool = False


def ensure_github_cli_auth(
    *,
    environment: Mapping[str, str] | None = None,
    output_func: OutputFunc = print,
    runner: Runner = subprocess.run,
) -> GitHubCliAuthResult:
    """Ensure local PR creation can use GitHub token auth or gh auth."""
    current_environment = os.environ if environment is None else environment
    if current_environment.get(GITHUB_TOKEN_ENV_VAR):
        output_func("GitHub token is available for PR creation.")
        return GitHubCliAuthResult(
            command="",
            already_signed_in=True,
            used_token=True,
        )

    command = current_environment.get(GITHUB_COMMAND_ENV_VAR, "gh")
    status = _run_status(command, runner)
    if status.returncode == 0:
        output_func("GitHub CLI is already signed in.")
        return GitHubCliAuthResult(command=command, already_signed_in=True)

    output_func("Opening GitHub sign-in with GitHub CLI.")
    output_func("Finish the browser login, then return to this terminal.")
    try:
        login = runner(
            [
                command,
                "auth",
                "login",
                "--hostname",
                GITHUB_HOSTNAME,
                "--web",
            ],
            check=False,
        )
    except FileNotFoundError as error:
        raise GitHubCliMissingError(
            "GitHub CLI was not found. Install gh or set GITHUB_TOKEN, then run "
            "openpandora setup again."
        ) from error

    if login.returncode != 0:
        raise GitHubCliAuthError("GitHub CLI login did not finish successfully.")

    status = _run_status(command, runner)
    if status.returncode != 0:
        raise GitHubCliAuthError(
            "GitHub CLI login finished, but no GitHub session was found."
        )

    return GitHubCliAuthResult(command=command, already_signed_in=False)


def _run_status(command: str, runner: Runner):
    try:
        return runner(
            [command, "auth", "status", "--hostname", GITHUB_HOSTNAME],
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
    except FileNotFoundError as error:
        raise GitHubCliMissingError(
            "GitHub CLI was not found. Install gh or set GITHUB_TOKEN, then run "
            "openpandora setup again."
        ) from error
