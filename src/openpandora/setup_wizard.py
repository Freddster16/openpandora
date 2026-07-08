"""Interactive terminal setup for OpenPandora."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

from openpandora.hooks import (
    HookError,
    HookInstallResult,
    install_git_hooks,
    is_git_repo,
)
from openpandora.openai_account import (
    OpenAIAccountAuthError,
    ensure_openai_account_auth,
)
from openpandora.project_config import (
    CONFIG_FILE,
    ProjectConfig,
    ProjectConfigError,
    global_config_path,
    load_project_config,
)
from openpandora.providers import (
    AuthMethod,
    ModelOption,
    Provider,
    ProviderSetup,
    ReasoningOption,
    list_model_options,
    list_provider_setups,
    list_reasoning_options,
    select_provider,
)

InputFunc = Callable[[str], str]
OutputFunc = Callable[[str], None]
AccountAuthFunc = Callable[..., object]
T = TypeVar("T")


@dataclass(frozen=True)
class SetupResult:
    """Describe the choices saved by the setup wizard."""

    provider: str
    auth_method: str
    model: str
    reasoning: str
    config_path: Path
    global_config: bool
    auto_create_pr: bool
    already_configured: bool = False
    hooks: HookInstallResult | None = None


def run_setup_wizard(
    repo_path: str | Path = ".",
    *,
    global_config: bool = True,
    reset: bool = False,
    skip_existing: bool = False,
    input_func: InputFunc = input,
    output_func: OutputFunc = print,
    account_auth_func: AccountAuthFunc = ensure_openai_account_auth,
) -> SetupResult:
    """Ask first-run setup questions in a small terminal UI."""
    output_func("OpenPandora setup")
    output_func("")

    existing_config = load_project_config(repo_path)
    if skip_existing and not reset and _is_complete_openai_setup(existing_config):
        config_path = _setup_config_path(repo_path, global_config)
        output_func("OpenPandora is already set up for OpenAI.")
        output_func(f"Using saved setup from {config_path}.")
        output_func("Run openpandora setup to change it.")
        return SetupResult(
            provider="openai",
            auth_method=existing_config.auth_method or "",
            model=existing_config.model or "",
            reasoning=existing_config.reasoning or "",
            config_path=config_path,
            global_config=global_config,
            auto_create_pr=existing_config.auto_create_pr,
            already_configured=True,
        )

    provider_setup = _openai_provider_setup(output_func)
    auth_method = _choose_auth_method(provider_setup, input_func, output_func)
    if auth_method is AuthMethod.OAUTH:
        account_auth_func(output_func=output_func)
    model = _choose_model(provider_setup.provider, input_func, output_func)
    reasoning = _choose_reasoning(input_func, output_func)
    auto_create_pr = _ask_yes_no(
        (
            "Create a fix branch and GitHub PR automatically when "
            "OpenPandora wakes and finds a safe patch?"
        ),
        default=False,
        input_func=input_func,
        output_func=output_func,
    )

    provider_config = select_provider(
        provider_setup.provider.value,
        repo_path,
        auth_method=auth_method.value,
        model=model,
        reasoning=reasoning.level.value,
        auto_create_pr=auto_create_pr,
        global_config=global_config,
    )

    hooks = None
    if is_git_repo(repo_path) and _ask_yes_no(
        "Put OpenPandora to sleep for this Git repo now?",
        default=False,
        input_func=input_func,
        output_func=output_func,
    ):
        hooks = install_git_hooks(repo_path, create_pr=auto_create_pr)

    output_func("")
    output_func(f"Saved setup to {provider_config.config_path}.")
    output_func("OpenPandora did not store any API keys or OAuth tokens.")
    _print_auth_next_step(provider_setup, auth_method, output_func)
    if auto_create_pr:
        output_func("Automatic PR creation also needs GITHUB_TOKEN when it wakes.")
    if hooks:
        output_func(f"Installed sleeping Git hooks in {hooks.hooks_dir}.")

    return SetupResult(
        provider=provider_setup.provider.value,
        auth_method=auth_method.value,
        model=model,
        reasoning=reasoning.level.value,
        config_path=provider_config.config_path,
        global_config=global_config,
        auto_create_pr=auto_create_pr,
        hooks=hooks,
    )


def _openai_provider_setup(
    output_func: OutputFunc,
) -> ProviderSetup:
    for setup in list_provider_setups():
        if setup.provider is Provider.OPENAI:
            output_func("AI company: OpenAI")
            return setup
    raise RuntimeError("OpenAI provider setup is not available.")


def _is_complete_openai_setup(config: ProjectConfig) -> bool:
    return bool(
        config.provider == "openai"
        and config.auth_method
        and config.model
        and config.reasoning
    )


def _setup_config_path(repo_path: str | Path, global_config: bool) -> Path:
    if global_config:
        return global_config_path()
    return Path(repo_path) / CONFIG_FILE


def _choose_auth_method(
    provider_setup: ProviderSetup,
    input_func: InputFunc,
    output_func: OutputFunc,
) -> AuthMethod:
    return _choose_from_menu(
        f"Choose auth for {provider_setup.display_name}:",
        provider_setup.auth_methods,
        _auth_method_label,
        input_func,
        output_func,
    )


def _choose_model(
    provider: str,
    input_func: InputFunc,
    output_func: OutputFunc,
) -> str:
    model_options = list_model_options(provider)
    choices: tuple[ModelOption | str, ...] = (*model_options, "custom")
    selected = _choose_from_menu(
        "Choose a model:",
        choices,
        _model_label,
        input_func,
        output_func,
    )
    if selected == "custom":
        while True:
            model = input_func("Model id: ").strip()
            if model:
                return model
            output_func("Enter a model id, such as gpt-5-mini.")
    return selected.model


def _choose_reasoning(
    input_func: InputFunc,
    output_func: OutputFunc,
) -> ReasoningOption:
    return _choose_from_menu(
        "Choose reasoning level:",
        list_reasoning_options(),
        lambda option: f"{option.display_name} - {option.note}",
        input_func,
        output_func,
        default_index=2,
    )


def _choose_from_menu(
    title: str,
    choices: tuple[T, ...],
    label_func: Callable[[T], str],
    input_func: InputFunc,
    output_func: OutputFunc,
    *,
    default_index: int = 1,
) -> T:
    output_func(title)
    for index, choice in enumerate(choices, start=1):
        default_marker = " (default)" if index == default_index else ""
        output_func(f"  {index}. {label_func(choice)}{default_marker}")

    while True:
        answer = input_func("> ").strip()
        if not answer:
            return choices[default_index - 1]
        if answer.isdigit():
            selected_index = int(answer)
            if 1 <= selected_index <= len(choices):
                return choices[selected_index - 1]
        output_func(f"Choose a number from 1 to {len(choices)}.")


def _ask_yes_no(
    question: str,
    *,
    default: bool,
    input_func: InputFunc,
    output_func: OutputFunc,
) -> bool:
    suffix = "Y/n" if default else "y/N"
    while True:
        answer = input_func(f"{question} [{suffix}] ").strip().lower()
        if not answer:
            return default
        if answer in {"y", "yes"}:
            return True
        if answer in {"n", "no"}:
            return False
        output_func("Answer yes or no.")


def _auth_method_label(auth_method: AuthMethod) -> str:
    if auth_method is AuthMethod.OAUTH:
        return "OpenAI account sign-in"
    if auth_method is AuthMethod.ENVIRONMENT:
        return "API key from environment"
    return "No auth needed"


def _model_label(model: ModelOption | str) -> str:
    if model == "custom":
        return "Custom model id"
    return f"{model.display_name} ({model.model}) - {model.note}"


def _print_auth_next_step(
    provider_setup: ProviderSetup,
    auth_method: AuthMethod,
    output_func: OutputFunc,
) -> None:
    if auth_method is AuthMethod.OAUTH:
        output_func(
            "OpenAI account auth was saved as the preferred auth method. "
            "Provider reviews will use your saved Codex ChatGPT login."
        )
        return

    if auth_method is AuthMethod.ENVIRONMENT and provider_setup.env_var:
        output_func(f"Before provider reviews, set {provider_setup.env_var}.")


def safe_run_setup_wizard(
    repo_path: str | Path = ".",
    *,
    global_config: bool = True,
    reset: bool = False,
    skip_existing: bool = False,
    input_func: InputFunc = input,
    output_func: OutputFunc = print,
) -> SetupResult | None:
    """Run setup and turn hook installation conflicts into readable output."""
    try:
        return run_setup_wizard(
            repo_path,
            global_config=global_config,
            reset=reset,
            skip_existing=skip_existing,
            input_func=input_func,
            output_func=output_func,
        )
    except (HookError, OpenAIAccountAuthError, ProjectConfigError) as error:
        output_func("OpenPandora could not finish setup.")
        output_func(str(error))
        return None
