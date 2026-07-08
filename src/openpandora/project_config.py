"""Load editable project settings for OpenPandora."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CONFIG_FILE = Path(".openpandora") / "config.json"
CONFIG_HOME_ENV_VAR = "OPENPANDORA_CONFIG_HOME"
PROVIDER_ENV_VAR = "OPENPANDORA_PROVIDER"
AUTH_METHOD_ENV_VAR = "OPENPANDORA_AUTH_METHOD"
MODEL_ENV_VAR = "OPENPANDORA_MODEL"
REASONING_ENV_VAR = "OPENPANDORA_REASONING"
DEFAULT_BASE_REF = "main"
DEFAULT_TEST_COMMAND = "python -m pytest"
DEFAULT_LINT_COMMAND = "ruff check ."


@dataclass(frozen=True)
class ProjectConfig:
    """Describe user-editable OpenPandora project settings."""

    provider: str | None = None
    auth_method: str | None = None
    model: str | None = None
    reasoning: str | None = None
    auto_create_pr: bool = False
    base_ref: str = DEFAULT_BASE_REF
    test_command: str = DEFAULT_TEST_COMMAND
    lint_command: str = DEFAULT_LINT_COMMAND


class ProjectConfigError(RuntimeError):
    """Raised when the project config is not readable."""


def load_project_config(repo_path: str | Path = ".") -> ProjectConfig:
    """Load project settings, falling back to safe defaults."""
    global_path = global_config_path()
    global_data = _read_config_data(global_path)
    config_path = Path(repo_path) / CONFIG_FILE
    data = _read_config_data(config_path)
    commands = _object_or_empty(data.get("commands"), config_path, "commands")
    file_provider = _optional_string(data.get("provider"), config_path, "provider")
    global_provider = _optional_string(
        global_data.get("provider"), global_path, "provider"
    )
    return ProjectConfig(
        provider=_environment_provider() or file_provider or global_provider,
        auth_method=(
            _environment_string(AUTH_METHOD_ENV_VAR)
            or _optional_string(data.get("auth_method"), config_path, "auth_method")
            or _optional_string(
                global_data.get("auth_method"), global_path, "auth_method"
            )
        ),
        model=(
            _environment_string(MODEL_ENV_VAR)
            or _optional_string(data.get("model"), config_path, "model")
            or _optional_string(global_data.get("model"), global_path, "model")
        ),
        reasoning=(
            _environment_string(REASONING_ENV_VAR)
            or _optional_string(data.get("reasoning"), config_path, "reasoning")
            or _optional_string(global_data.get("reasoning"), global_path, "reasoning")
        ),
        auto_create_pr=_optional_bool(
            data.get("auto_create_pr"),
            config_path,
            "auto_create_pr",
            default=_optional_bool(
                global_data.get("auto_create_pr"),
                global_path,
                "auto_create_pr",
                default=False,
            ),
        ),
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


def global_config_path() -> Path:
    """Return the per-user OpenPandora config path."""
    configured_home = os.environ.get(CONFIG_HOME_ENV_VAR)
    if configured_home:
        return Path(configured_home) / "openpandora" / "config.json"

    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config_home:
        return Path(xdg_config_home) / "openpandora" / "config.json"

    return Path.home() / ".config" / "openpandora" / "config.json"


def write_global_config(config: ProjectConfig) -> Path:
    """Save per-user OpenPandora settings without storing secret values."""
    config_path = global_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    payload = _to_json(config, include_project=False)
    config_path.write_text(json.dumps(payload, indent=2) + "\n")
    return config_path


def update_project_config(
    repo_path: str | Path = ".",
    *,
    provider: str | None = None,
    auth_method: str | None = None,
    model: str | None = None,
    reasoning: str | None = None,
    auto_create_pr: bool | None = None,
    base_ref: str | None = None,
    test_command: str | None = None,
    lint_command: str | None = None,
) -> ProjectConfig:
    """Update one or more settings while preserving the rest."""
    current_config = load_project_config(repo_path)
    next_config = ProjectConfig(
        provider=current_config.provider if provider is None else provider,
        auth_method=(
            current_config.auth_method if auth_method is None else auth_method
        ),
        model=current_config.model if model is None else model,
        reasoning=current_config.reasoning if reasoning is None else reasoning,
        auto_create_pr=(
            current_config.auto_create_pr if auto_create_pr is None else auto_create_pr
        ),
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


def update_global_config(
    *,
    provider: str | None = None,
    auth_method: str | None = None,
    model: str | None = None,
    reasoning: str | None = None,
    auto_create_pr: bool | None = None,
) -> ProjectConfig:
    """Update per-user settings while preserving existing values."""
    current_config = _load_global_config()
    next_config = ProjectConfig(
        provider=current_config.provider if provider is None else provider,
        auth_method=(
            current_config.auth_method if auth_method is None else auth_method
        ),
        model=current_config.model if model is None else model,
        reasoning=current_config.reasoning if reasoning is None else reasoning,
        auto_create_pr=(
            current_config.auto_create_pr if auto_create_pr is None else auto_create_pr
        ),
    )
    write_global_config(next_config)
    return next_config


def default_config_payload() -> dict[str, Any]:
    """Return the starter config users can read and edit."""
    return _to_json(ProjectConfig())


def _to_json(config: ProjectConfig, *, include_project: bool = True) -> dict[str, Any]:
    data: dict[str, Any] = {}
    if config.provider is not None:
        data["provider"] = config.provider
    if config.auth_method is not None:
        data["auth_method"] = config.auth_method
    if config.model is not None:
        data["model"] = config.model
    if config.reasoning is not None:
        data["reasoning"] = config.reasoning
    if config.auto_create_pr:
        data["auto_create_pr"] = config.auto_create_pr
    if include_project:
        data.update(
            {
                "base_ref": config.base_ref,
                "commands": {
                    "test": config.test_command,
                    "lint": config.lint_command,
                },
            }
        )
    return data


def _load_global_config() -> ProjectConfig:
    config_path = global_config_path()
    data = _read_config_data(config_path)
    return ProjectConfig(
        provider=_optional_string(data.get("provider"), config_path, "provider"),
        auth_method=_optional_string(
            data.get("auth_method"), config_path, "auth_method"
        ),
        model=_optional_string(data.get("model"), config_path, "model"),
        reasoning=_optional_string(data.get("reasoning"), config_path, "reasoning"),
        auto_create_pr=_optional_bool(
            data.get("auto_create_pr"),
            config_path,
            "auto_create_pr",
            default=False,
        ),
    )


def _read_config_data(config_path: Path) -> dict[str, Any]:
    if not config_path.exists():
        return {}

    try:
        data = json.loads(config_path.read_text())
    except json.JSONDecodeError as error:
        raise ProjectConfigError(
            f"OpenPandora could not read {config_path}: {error.msg}"
        ) from error

    if not isinstance(data, dict):
        raise ProjectConfigError(f"{config_path} must contain a JSON object.")

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


def _optional_bool(
    value: object, config_path: Path, name: str, *, default: bool
) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    raise ProjectConfigError(f"{config_path} field '{name}' must be a boolean.")


def _environment_provider() -> str | None:
    return _environment_string(PROVIDER_ENV_VAR)


def _environment_string(name: str) -> str | None:
    value = os.environ.get(name)
    if value is None or not value.strip():
        return None
    return value.strip()
