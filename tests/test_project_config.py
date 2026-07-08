import json
import stat

import pytest

from openpandora.project_config import (
    ProjectConfig,
    ProjectConfigError,
    default_config_payload,
    global_config_path,
    load_project_config,
    update_project_config,
    write_global_config,
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


def test_load_project_config_uses_global_provider_defaults(tmp_path):
    write_global_config(
        ProjectConfig(
            provider="openai",
            auth_method="environment",
            model="gpt-5",
            reasoning="high",
            auto_create_pr=True,
        )
    )

    config = load_project_config(tmp_path)

    assert config.provider == "openai"
    assert config.auth_method == "environment"
    assert config.model == "gpt-5"
    assert config.reasoning == "high"
    assert config.auto_create_pr is True
    assert global_config_path().exists()
    assert stat.S_IMODE(global_config_path().parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(global_config_path().stat().st_mode) == 0o600


def test_load_project_config_prefers_project_settings_over_global(tmp_path):
    write_global_config(ProjectConfig(provider="openai", model="gpt-5"))
    write_project_config(
        ProjectConfig(provider="local", model="local-command"), tmp_path
    )

    config = load_project_config(tmp_path)

    assert config.provider == "local"
    assert config.model == "local-command"


def test_load_project_config_env_model_overrides_files(tmp_path, monkeypatch):
    write_global_config(ProjectConfig(model="gpt-5"))
    write_project_config(ProjectConfig(model="claude-sonnet-4-5"), tmp_path)
    monkeypatch.setenv("OPENPANDORA_MODEL", "override-model")

    config = load_project_config(tmp_path)

    assert config.model == "override-model"


def test_write_and_load_project_config_round_trip(tmp_path):
    config = ProjectConfig(
        provider="openai",
        auth_method="environment",
        model="gpt-5-mini",
        reasoning="medium",
        auto_create_pr=True,
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


def test_load_project_config_rejects_non_boolean_auto_create_pr(tmp_path):
    config_path = tmp_path / ".openpandora" / "config.json"
    config_path.parent.mkdir()
    config_path.write_text(json.dumps({"auto_create_pr": "yes"}))

    with pytest.raises(ProjectConfigError, match="auto_create_pr"):
        load_project_config(tmp_path)


def test_default_config_payload_is_readable_json_shape():
    payload = default_config_payload()

    assert payload["auto_create_pr"] is True
    assert payload["base_ref"] == "main"
    assert payload["commands"]["test"] == "python -m pytest"
    assert payload["commands"]["lint"] == "ruff check ."
