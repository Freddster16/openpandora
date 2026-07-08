"""Use the local Codex CLI for OpenAI account authentication."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

CODEX_COMMAND_ENV_VAR = "OPENPANDORA_CODEX_COMMAND"

OutputFunc = Callable[[str], None]
Runner = Callable[..., Any]


class OpenAIAccountAuthError(RuntimeError):
    """Raised when OpenAI account auth cannot be prepared."""


@dataclass(frozen=True)
class OpenAIAccountAuthResult:
    """Describe the OpenAI account auth state."""

    command: str
    already_signed_in: bool


def ensure_openai_account_auth(
    *,
    environment: Mapping[str, str] | None = None,
    output_func: OutputFunc = print,
    runner: Runner = subprocess.run,
) -> OpenAIAccountAuthResult:
    """Ensure Codex has a cached ChatGPT login for OpenAI account auth."""
    current_environment = os.environ if environment is None else environment
    command = current_environment.get(CODEX_COMMAND_ENV_VAR, "codex")

    status = _run_status(command, runner)
    if status.returncode == 0 and _status_mentions_chatgpt(status):
        output_func("OpenAI account auth is already signed in through Codex.")
        return OpenAIAccountAuthResult(command=command, already_signed_in=True)

    output_func("Opening OpenAI account sign-in through Codex.")
    output_func("Finish the browser login, then return to this terminal.")
    try:
        login = runner([command, "login"], check=False)
    except FileNotFoundError as error:
        raise OpenAIAccountAuthError(
            "OpenAI account auth needs the Codex CLI. Install Codex or choose "
            "API key auth."
        ) from error

    if login.returncode != 0:
        raise OpenAIAccountAuthError("Codex login did not finish successfully.")

    status = _run_status(command, runner)
    if status.returncode != 0 or not _status_mentions_chatgpt(status):
        raise OpenAIAccountAuthError(
            "Codex login finished, but no ChatGPT account session was found."
        )

    return OpenAIAccountAuthResult(command=command, already_signed_in=False)


def _run_status(command: str, runner: Runner):
    try:
        return runner(
            [command, "login", "status"],
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
    except FileNotFoundError as error:
        raise OpenAIAccountAuthError(
            "OpenAI account auth needs the Codex CLI. Install Codex or choose "
            "API key auth."
        ) from error


def _status_mentions_chatgpt(status) -> bool:
    status_parts = (
        getattr(status, "stdout", ""),
        getattr(status, "stderr", ""),
    )
    output = "\n".join(
        value for value in status_parts if value
    )
    return "chatgpt" in output.lower()
