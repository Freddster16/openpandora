"""Use the local Codex CLI for OpenAI account authentication."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CODEX_COMMAND_ENV_VAR = "OPENPANDORA_CODEX_COMMAND"
CODEX_INSTALL_URL_ENV_VAR = "OPENPANDORA_CODEX_INSTALL_URL"
CODEX_ALLOW_INSECURE_INSTALL_ENV_VAR = "OPENPANDORA_ALLOW_INSECURE_CODEX_INSTALL"
DEFAULT_CODEX_INSTALL_URL = "https://chatgpt.com/codex/install.sh"

OutputFunc = Callable[[str], None]
Runner = Callable[..., Any]
Installer = Callable[..., str]


class OpenAIAccountAuthError(RuntimeError):
    """Raised when OpenAI account auth cannot be prepared."""


class CodexCliMissingError(OpenAIAccountAuthError):
    """Raised when the Codex CLI command is not available."""


@dataclass(frozen=True)
class OpenAIAccountAuthResult:
    """Describe the OpenAI account auth state."""

    command: str
    already_signed_in: bool
    installed_codex: bool = False


def ensure_openai_account_auth(
    *,
    environment: Mapping[str, str] | None = None,
    output_func: OutputFunc = print,
    runner: Runner = subprocess.run,
    installer: Installer | None = None,
) -> OpenAIAccountAuthResult:
    """Ensure Codex has a cached ChatGPT login for OpenAI account auth."""
    current_environment = os.environ if environment is None else environment
    command = current_environment.get(CODEX_COMMAND_ENV_VAR, "codex")
    install_codex = install_codex_cli if installer is None else installer
    installed_codex = False

    try:
        status = _run_status(command, runner)
    except CodexCliMissingError:
        output_func("Codex CLI was not found. Installing it now.")
        command = install_codex(
            command=command,
            environment=current_environment,
            output_func=output_func,
            runner=runner,
        )
        installed_codex = True
        status = _run_status(command, runner)

    if status.returncode == 0 and _status_mentions_chatgpt(status):
        output_func("OpenAI account auth is already signed in through Codex.")
        return OpenAIAccountAuthResult(
            command=command,
            already_signed_in=True,
            installed_codex=installed_codex,
        )

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

    return OpenAIAccountAuthResult(
        command=command,
        already_signed_in=False,
        installed_codex=installed_codex,
    )


def install_codex_cli(
    *,
    command: str = "codex",
    environment: Mapping[str, str] | None = None,
    output_func: OutputFunc = print,
    runner: Runner = subprocess.run,
) -> str:
    """Install the Codex CLI from OpenAI's standalone installer."""
    current_environment = os.environ if environment is None else environment
    install_url = current_environment.get(
        CODEX_INSTALL_URL_ENV_VAR,
        DEFAULT_CODEX_INSTALL_URL,
    )
    _validate_install_url(install_url, current_environment)

    with tempfile.TemporaryDirectory(prefix="openpandora-codex-install-") as temp_dir:
        installer_path = Path(temp_dir) / "install.sh"
        _download_installer(install_url, installer_path)
        installer_path.chmod(0o700)

        output_func("Downloaded Codex CLI installer from OpenAI.")
        result = runner(
            ["sh", str(installer_path)],
            check=False,
            env=_installer_environment(current_environment),
            timeout=300,
        )

    if result.returncode != 0:
        raise OpenAIAccountAuthError("Codex CLI installer did not finish successfully.")

    resolved_command = _find_codex_command(command, current_environment)
    if resolved_command is None and command != "codex":
        resolved_command = _find_codex_command("codex", current_environment)
    if resolved_command is None:
        raise OpenAIAccountAuthError(
            "Codex CLI installed, but the codex command was not found. "
            "Add the installer location to PATH and run openpandora setup again."
        )

    output_func("Codex CLI installed.")
    return resolved_command


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
        raise CodexCliMissingError("Codex CLI command was not found.") from error


def _validate_install_url(
    install_url: str,
    environment: Mapping[str, str],
) -> None:
    if install_url == DEFAULT_CODEX_INSTALL_URL:
        return
    if environment.get(CODEX_ALLOW_INSECURE_INSTALL_ENV_VAR) == "1":
        return
    raise OpenAIAccountAuthError(
        "Codex CLI auto-install only uses OpenAI's official installer URL."
    )


def _download_installer(install_url: str, installer_path: Path) -> None:
    try:
        with urllib.request.urlopen(install_url, timeout=60) as response:
            installer_path.write_bytes(response.read())
    except (urllib.error.URLError, TimeoutError) as error:
        raise OpenAIAccountAuthError(
            "Could not download the Codex CLI installer."
        ) from error


def _installer_environment(environment: Mapping[str, str]) -> dict[str, str]:
    return {
        **os.environ,
        **dict(environment),
        "CODEX_NON_INTERACTIVE": "1",
    }


def _find_codex_command(
    command: str,
    environment: Mapping[str, str],
) -> str | None:
    resolved = shutil.which(command, path=environment.get("PATH"))
    if resolved:
        return resolved

    if Path(command).name != command:
        command_path = Path(command).expanduser()
        return str(command_path) if command_path.exists() else None

    home = Path(environment.get("HOME") or Path.home()).expanduser()
    for candidate in (
        home / ".local" / "bin" / command,
        home / ".codex" / "bin" / command,
        Path("/opt/homebrew/bin") / command,
        Path("/usr/local/bin") / command,
    ):
        if candidate.exists():
            return str(candidate)
    return None


def _status_mentions_chatgpt(status) -> bool:
    status_parts = (
        getattr(status, "stdout", ""),
        getattr(status, "stderr", ""),
    )
    output = "\n".join(value for value in status_parts if value)
    return "chatgpt" in output.lower()
