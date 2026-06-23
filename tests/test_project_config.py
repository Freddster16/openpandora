import json

import pytest

from openpandora.project_config import (
    ProjectConfig,
    ProjectConfigError,
    default_config_payload,
    load_project_config,
    update_project_config,
    write_project_config,
)


def test_load_project_config_uses_defaults_when_file_is_missing(tmp_path):
    config = load_project_config(tmp_path)

    assert config == ProjectConfig()


def test_load_project_config_uses_env_provider_when_file_is_missing(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("OPENPANDORA_PROVIDER", "anthropic")

    config = load_project_config(tmp_path)

    assert config.provider == "anthropic"


def test_write_and_load_project_config_round_trip(tmp_path):
    config = ProjectConfig(
        provider="openai",
        base_ref="develop",
        test_command="python -m pytest tests/test_cli.py",
        lint_command="ruff check src",
    )

    config_path = write_project_config(config, tmp_path)

    assert config_path == tmp_path / ".openpandora" / "config.json"
    assert load_project_config(tmp_path) == config
    assert "OPENAI_API_KEY" not in config_path.read_text()


def test_update_project_config_preserves_existing_settings(tmp_path):
    write_project_config(
        ProjectConfig(provider="local", test_command="pytest -q"),
        tmp_path,
    )

    config = update_project_config(tmp_path, provider="openai")

    assert config.provider == "openai"
    assert config.test_command == "pytest -q"


def test_load_project_config_env_provider_overrides_file_provider(
    tmp_path, monkeypatch
):
    write_project_config(ProjectConfig(provider="local"), tmp_path)
    monkeypatch.setenv("OPENPANDORA_PROVIDER", "openai")

    config = load_project_config(tmp_path)

    assert config.provider == "openai"


def test_load_project_config_rejects_invalid_json(tmp_path):
    config_path = tmp_path / ".openpandora" / "config.json"
    config_path.parent.mkdir()
    config_path.write_text("{not-json")

    with pytest.raises(ProjectConfigError, match="could not read"):
        load_project_config(tmp_path)


def test_load_project_config_rejects_non_string_command(tmp_path):
    config_path = tmp_path / ".openpandora" / "config.json"
    config_path.parent.mkdir()
    config_path.write_text(json.dumps({"commands": {"test": ["pytest"]}}))

    with pytest.raises(ProjectConfigError, match="commands.test"):
        load_project_config(tmp_path)


def test_default_config_payload_is_readable_json_shape():
    payload = default_config_payload()

    assert payload["base_ref"] == "main"
    assert payload["commands"]["test"] == "python -m pytest"
    assert payload["commands"]["lint"] == "ruff check ."
