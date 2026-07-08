from openpandora.project_config import (
    ProjectConfig,
    load_project_config,
    write_global_config,
)
from openpandora.setup_wizard import _apply_menu_key, run_setup_wizard


def test_setup_wizard_if_needed_skips_when_openai_setup_is_already_saved(tmp_path):
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
        skip_existing=True,
        input_func=fail_input,
        output_func=output.append,
    )

    assert result.already_configured is True
    assert result.provider == "openai"
    assert result.model == "gpt-5-mini"
    assert result.hooks is not None
    assert result.hooks.post_commit_hook.exists()
    assert "already set up" in "\n".join(output)
    assert "openpandora setup to change it" in "\n".join(output)
    assert "asleep for all Git repos" in "\n".join(output)


def test_setup_wizard_reopens_saved_setup_by_default(tmp_path):
    write_global_config(
        ProjectConfig(
            provider="openai",
            auth_method="environment",
            model="gpt-5-mini",
            reasoning="medium",
        )
    )
    inputs = iter(["2", "2", "3", "n"])
    output = []

    result = run_setup_wizard(
        tmp_path,
        input_func=lambda prompt: next(inputs),
        output_func=output.append,
    )

    config = load_project_config(tmp_path)

    assert result.already_configured is False
    assert result.model == "gpt-5"
    assert result.reasoning == "high"
    assert config.model == "gpt-5"
    assert config.reasoning == "high"
    assert "already set up" not in "\n".join(output)


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


def test_setup_wizard_defaults_to_automatic_fix_prs(tmp_path):
    inputs = iter(["2", "1", "2", ""])
    output = []

    result = run_setup_wizard(
        tmp_path,
        global_config=False,
        input_func=lambda prompt: next(inputs),
        output_func=output.append,
    )

    config = load_project_config(tmp_path)

    assert result.auto_create_pr is True
    assert config.auto_create_pr is True


def test_setup_wizard_runs_openai_account_auth_for_oauth(tmp_path):
    inputs = iter(["1", "1", "2", "n"])
    calls = []
    output = []

    result = run_setup_wizard(
        tmp_path,
        global_config=False,
        input_func=lambda prompt: next(inputs),
        output_func=output.append,
        account_auth_func=lambda **kwargs: calls.append(kwargs["output_func"]),
    )

    assert result.auth_method == "oauth"
    assert result.model == "gpt-5-mini"
    assert calls
    output_text = "\n".join(output)
    assert "saved Codex ChatGPT login" in output_text
    assert "OPENAI_API_KEY" not in output_text


def test_setup_wizard_can_install_computer_wide_sleeping_hooks(tmp_path):
    inputs = iter(["2", "", "", "n"])
    output = []

    result = run_setup_wizard(
        tmp_path,
        global_config=False,
        input_func=lambda prompt: next(inputs),
        output_func=output.append,
    )

    assert result.hooks is not None
    assert result.hooks.post_commit_hook.exists()
    assert result.hooks.pre_push_hook.exists()
    assert "asleep for all Git repos" in "\n".join(output)


def test_keyboard_menu_selects_with_enter_or_space():
    assert _apply_menu_key(1, "enter", 3) == (1, True)
    assert _apply_menu_key(1, "space", 3) == (1, True)


def test_keyboard_menu_moves_with_arrows_and_jk():
    assert _apply_menu_key(0, "down", 3) == (1, False)
    assert _apply_menu_key(1, "j", 3) == (2, False)
    assert _apply_menu_key(2, "up", 3) == (1, False)
    assert _apply_menu_key(0, "k", 3) == (2, False)


def test_keyboard_menu_uses_cbreak_not_raw(monkeypatch):
    calls = []
    inputs = iter(["enter"])

    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    monkeypatch.setattr("sys.stdin.fileno", lambda: 0)
    monkeypatch.setattr("termios.tcgetattr", lambda fd: ["old"])
    monkeypatch.setattr("termios.tcsetattr", lambda *args: calls.append(args))
    monkeypatch.setattr("tty.setcbreak", lambda fd: calls.append(("cbreak", fd)))
    monkeypatch.setattr(
        "openpandora.setup_wizard._read_keyboard_key",
        lambda: next(inputs),
    )

    from openpandora.setup_wizard import _choose_from_menu

    result = _choose_from_menu(
        "Pick one",
        ("first", "second"),
        lambda value: value,
        input,
        print,
    )

    assert result == "first"
    assert ("cbreak", 0) in calls
