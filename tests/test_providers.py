from openpandora.project_config import (
    ProjectConfig,
    load_project_config,
    write_project_config,
)
from openpandora.providers import (
    AuthMethod,
    Provider,
    list_provider_setups,
    load_selected_provider,
    select_provider,
)


def test_list_provider_setups_marks_api_key_provider_ready_when_env_var_exists():
    setups = list_provider_setups({"OPENAI_API_KEY": "secret-value"})
    openai_setup = next(setup for setup in setups if setup.provider is Provider.OPENAI)

    assert openai_setup.configured is True
    assert openai_setup.env_var == "OPENAI_API_KEY"
    assert AuthMethod.ENVIRONMENT in openai_setup.auth_methods


def test_list_provider_setups_marks_missing_api_key_provider_as_not_ready():
    setups = list_provider_setups({})
    anthropic_setup = next(
        setup for setup in setups if setup.provider is Provider.ANTHROPIC
    )

    assert anthropic_setup.configured is False
    assert anthropic_setup.env_var == "ANTHROPIC_API_KEY"


def test_list_provider_setups_keeps_local_provider_ready_without_secrets():
    setups = list_provider_setups({})
    local_setup = next(setup for setup in setups if setup.provider is Provider.LOCAL)

    assert local_setup.configured is True
    assert local_setup.env_var is None
    assert local_setup.auth_methods == (AuthMethod.NONE,)


def test_select_provider_saves_choice_without_secrets(tmp_path):
    config = select_provider("openai", tmp_path)

    assert config.provider is Provider.OPENAI
    assert config.config_path == tmp_path / ".openpandora" / "config.json"
    assert "OPENAI_API_KEY" not in config.config_path.read_text()

    loaded_config = load_selected_provider(tmp_path)
    assert loaded_config == config


def test_select_provider_preserves_configured_commands(tmp_path):
    write_project_config(ProjectConfig(test_command="pytest -q"), tmp_path)

    select_provider("anthropic", tmp_path)

    project_config = load_project_config(tmp_path)
    assert project_config.provider == "anthropic"
    assert project_config.test_command == "pytest -q"


def test_load_selected_provider_returns_none_when_config_is_missing(tmp_path):
    assert load_selected_provider(tmp_path) is None
