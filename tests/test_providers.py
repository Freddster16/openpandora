from openpandora.providers import AuthMethod, Provider, list_provider_setups


def test_list_provider_setups_marks_api_key_provider_ready_when_env_var_exists():
    setups = list_provider_setups({"OPENAI_API_KEY": "secret-value"})
    openai_setup = next(setup for setup in setups if setup.provider is Provider.OPENAI)

    assert openai_setup.configured is True
    assert openai_setup.env_var == "OPENAI_API_KEY"
    assert AuthMethod.ENVIRONMENT in openai_setup.auth_methods
    assert AuthMethod.GUIDED in openai_setup.auth_methods


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
