import subprocess

from openpandora.project_config import (
    ProjectConfig,
    load_project_config,
    write_global_config,
)
from openpandora.setup_wizard import run_setup_wizard


def test_setup_wizard_skips_when_openai_setup_is_already_saved(tmp_path):
    write_global_config(
        ProjectConfig(
            provider="openai",
            auth_method="environment",
            model="gpt-5-mini",
            reasoning="medium",
        )
    )
    output = []

    def fail_input(prompt):
        raise AssertionError("setup should not ask questions")

    result = run_setup_wizard(
        tmp_path,
        input_func=fail_input,
        output_func=output.append,
    )

    assert result.already_configured is True
    assert result.provider == "openai"
    assert result.model == "gpt-5-mini"
    assert "already set up" in "\n".join(output)
    assert "--reset" in "\n".join(output)


def test_setup_wizard_saves_provider_model_reasoning_without_secrets(tmp_path):
    inputs = iter(["2", "2", "3", "y"])
    output = []

    result = run_setup_wizard(
        tmp_path,
        global_config=False,
        input_func=lambda prompt: next(inputs),
        output_func=output.append,
    )

    config = load_project_config(tmp_path)
    config_text = result.config_path.read_text()

    assert result.provider == "openai"
    assert result.auth_method == "environment"
    assert result.model == "gpt-5"
    assert result.reasoning == "high"
    assert result.auto_create_pr is True
    assert config.provider == "openai"
    assert config.auth_method == "environment"
    assert config.model == "gpt-5"
    assert config.reasoning == "high"
    assert config.auto_create_pr is True
    assert "OPENAI_API_KEY" not in config_text
    assert "Saved setup" in "\n".join(output)


def test_setup_wizard_runs_openai_account_auth_for_oauth(tmp_path):
    inputs = iter(["1", "1", "2", "n"])
    calls = []

    result = run_setup_wizard(
        tmp_path,
        global_config=False,
        input_func=lambda prompt: next(inputs),
        output_func=lambda message: None,
        account_auth_func=lambda **kwargs: calls.append(kwargs["output_func"]),
    )

    assert result.auth_method == "oauth"
    assert result.model == "gpt-5-mini"
    assert calls


def test_setup_wizard_can_install_sleeping_hooks(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    inputs = iter(["2", "", "", "n", "y"])

    result = run_setup_wizard(
        tmp_path,
        global_config=False,
        input_func=lambda prompt: next(inputs),
        output_func=lambda message: None,
    )

    assert result.hooks is not None
    assert result.hooks.post_commit_hook.exists()
    assert result.hooks.pre_push_hook.exists()
