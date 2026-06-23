"""Load editable project settings for OpenPandora."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CONFIG_FILE = Path(".openpandora") / "config.json"
PROVIDER_ENV_VAR = "OPENPANDORA_PROVIDER"
DEFAULT_BASE_REF = "main"
DEFAULT_TEST_COMMAND = "python -m pytest"
DEFAULT_LINT_COMMAND = "ruff check ."


@dataclass(frozen=True)
class ProjectConfig:
    """Describe user-editable OpenPandora project settings."""

    provider: str | None = None
    base_ref: str = DEFAULT_BASE_REF
    test_command: str = DEFAULT_TEST_COMMAND
    lint_command: str = DEFAULT_LINT_COMMAND


class ProjectConfigError(RuntimeError):
    """Raised when the project config is not readable."""


def load_project_config(repo_path: str | Path = ".") -> ProjectConfig:
    """Load project settings, falling back to safe defaults."""
    environment_provider = _environment_provider()
    config_path = Path(repo_path) / CONFIG_FILE
    if not config_path.exists():
        return ProjectConfig(provider=environment_provider)

    try:
        data = json.loads(config_path.read_text())
    except json.JSONDecodeError as error:
        raise ProjectConfigError(
            f"OpenPandora could not read {config_path}: {error.msg}"
        ) from error

    if not isinstance(data, dict):
        raise ProjectConfigError(f"{config_path} must contain a JSON object.")

    commands = _object_or_empty(data.get("commands"), config_path, "commands")
    file_provider = _optional_string(data.get("provider"), config_path, "provider")
    return ProjectConfig(
        provider=environment_provider or file_provider,
        base_ref=_string_or_default(
            data.get("base_ref"), DEFAULT_BASE_REF, config_path, "base_ref"
        ),
        test_command=_string_or_default(
            commands.get("test"), DEFAULT_TEST_COMMAND, config_path, "commands.test"
        ),
        lint_command=_string_or_default(
            commands.get("lint"), DEFAULT_LINT_COMMAND, config_path, "commands.lint"
        ),
    )


def write_project_config(config: ProjectConfig, repo_path: str | Path = ".") -> Path:
    """Save project settings without storing secret values."""
    config_path = Path(repo_path) / CONFIG_FILE
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(_to_json(config), indent=2) + "\n")
    return config_path


def update_project_config(
    repo_path: str | Path = ".",
    *,
    provider: str | None = None,
    base_ref: str | None = None,
    test_command: str | None = None,
    lint_command: str | None = None,
) -> ProjectConfig:
    """Update one or more settings while preserving the rest."""
    current_config = load_project_config(repo_path)
    next_config = ProjectConfig(
        provider=current_config.provider if provider is None else provider,
        base_ref=current_config.base_ref if base_ref is None else base_ref,
        test_command=(
            current_config.test_command if test_command is None else test_command
        ),
        lint_command=(
            current_config.lint_command if lint_command is None else lint_command
        ),
    )
    write_project_config(next_config, repo_path)
    return next_config


def default_config_payload() -> dict[str, Any]:
    """Return the starter config users can read and edit."""
    return _to_json(ProjectConfig())


def _to_json(config: ProjectConfig) -> dict[str, Any]:
    data: dict[str, Any] = {
        "base_ref": config.base_ref,
        "commands": {
            "test": config.test_command,
            "lint": config.lint_command,
        },
    }
    if config.provider is not None:
        data["provider"] = config.provider
    return data


def _object_or_empty(value: object, config_path: Path, name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    raise ProjectConfigError(f"{config_path} field '{name}' must be an object.")


def _optional_string(value: object, config_path: Path, name: str) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    raise ProjectConfigError(f"{config_path} field '{name}' must be a string.")


def _string_or_default(
    value: object, default: str, config_path: Path, name: str
) -> str:
    if value is None:
        return default
    if isinstance(value, str):
        return value
    raise ProjectConfigError(f"{config_path} field '{name}' must be a string.")


def _environment_provider() -> str | None:
    provider = os.environ.get(PROVIDER_ENV_VAR)
    if provider is None or not provider.strip():
        return None
    return provider.strip()
