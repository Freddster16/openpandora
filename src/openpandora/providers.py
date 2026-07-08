"""Describe AI provider auth options without touching secrets."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from openpandora.project_config import (
    CONFIG_FILE,
    global_config_path,
    load_project_config,
    update_global_config,
    update_project_config,
)


class Provider(StrEnum):
    """Name a supported AI provider choice."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    LOCAL = "local"


class AuthMethod(StrEnum):
    """Name how a provider can be authenticated."""

    OAUTH = "oauth"
    ENVIRONMENT = "environment"
    NONE = "none"


class ReasoningLevel(StrEnum):
    """Name the reasoning levels exposed by setup."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True)
class ProviderSetup:
    """Describe how a user can connect one provider safely."""

    provider: Provider
    display_name: str
    auth_methods: tuple[AuthMethod, ...]
    env_var: str | None
    configured: bool
    note: str


@dataclass(frozen=True)
class ModelOption:
    """Describe one model choice shown during setup."""

    provider: Provider
    model: str
    display_name: str
    note: str


@dataclass(frozen=True)
class ReasoningOption:
    """Describe one reasoning choice shown during setup."""

    level: ReasoningLevel
    display_name: str
    note: str


@dataclass(frozen=True)
class ProviderConfig:
    """Describe the selected provider without storing secrets."""

    provider: Provider
    config_path: Path
    auth_method: AuthMethod | None = None
    model: str | None = None
    reasoning: ReasoningLevel | None = None


def list_provider_setups(
    environment: Mapping[str, str] | None = None,
) -> tuple[ProviderSetup, ...]:
    """List provider setup options without reading secret values."""
    current_environment = os.environ if environment is None else environment
    return (
        _provider_setup(
            provider=Provider.OPENAI,
            display_name="OpenAI",
            auth_methods=(AuthMethod.OAUTH, AuthMethod.ENVIRONMENT),
            env_var="OPENAI_API_KEY",
            note=(
                "Use OpenAI account sign-in through Codex, or an API key from "
                "the environment."
            ),
            environment=current_environment,
        ),
        _provider_setup(
            provider=Provider.ANTHROPIC,
            display_name="Anthropic",
            auth_methods=(AuthMethod.ENVIRONMENT,),
            env_var="ANTHROPIC_API_KEY",
            note="Use an API key from the environment.",
            environment=current_environment,
        ),
        _provider_setup(
            provider=Provider.LOCAL,
            display_name="Local",
            auth_methods=(AuthMethod.NONE,),
            env_var=None,
            note="Set OPENPANDORA_LOCAL_COMMAND to call a local or self-hosted model.",
            environment=current_environment,
        ),
    )


def list_model_options(provider_name: str | Provider) -> tuple[ModelOption, ...]:
    """List model choices for a provider."""
    provider = Provider(provider_name)
    if provider is Provider.OPENAI:
        return (
            ModelOption(
                provider=provider,
                model="gpt-5-mini",
                display_name="GPT-5 mini",
                note="Fast default for everyday QA and small patches.",
            ),
            ModelOption(
                provider=provider,
                model="gpt-5",
                display_name="GPT-5",
                note="Stronger review model when you want deeper analysis.",
            ),
        )
    if provider is Provider.ANTHROPIC:
        return (
            ModelOption(
                provider=provider,
                model="claude-sonnet-4-5",
                display_name="Claude Sonnet 4.5",
                note="Balanced coding review model.",
            ),
            ModelOption(
                provider=provider,
                model="claude-opus-4-8",
                display_name="Claude Opus 4.8",
                note="Higher-depth model for harder review work.",
            ),
        )
    return (
        ModelOption(
            provider=provider,
            model="local-command",
            display_name="Local command",
            note="Use OPENPANDORA_LOCAL_COMMAND to call your model runner.",
        ),
    )


def list_reasoning_options() -> tuple[ReasoningOption, ...]:
    """List the reasoning levels shown during setup."""
    return (
        ReasoningOption(
            level=ReasoningLevel.LOW,
            display_name="Low",
            note="Quick checks with shorter provider thinking.",
        ),
        ReasoningOption(
            level=ReasoningLevel.MEDIUM,
            display_name="Medium",
            note="Balanced default for code review.",
        ),
        ReasoningOption(
            level=ReasoningLevel.HIGH,
            display_name="High",
            note="Spend more effort on security and tricky changes.",
        ),
    )


def select_provider(
    provider_name: str,
    repo_path: str | Path = ".",
    *,
    auth_method: str | None = None,
    model: str | None = None,
    reasoning: str | None = None,
    auto_create_pr: bool | None = None,
    global_config: bool = False,
) -> ProviderConfig:
    """Store the user's provider choice without storing API keys."""
    provider = Provider(provider_name)
    selected_auth_method = AuthMethod(auth_method) if auth_method else None
    selected_reasoning = ReasoningLevel(reasoning) if reasoning else None
    if global_config:
        saved_config = update_global_config(
            provider=provider.value,
            auth_method=selected_auth_method.value if selected_auth_method else None,
            model=model,
            reasoning=selected_reasoning.value if selected_reasoning else None,
            auto_create_pr=auto_create_pr,
        )
        config_path = global_config_path()
    else:
        saved_config = update_project_config(
            repo_path,
            provider=provider.value,
            auth_method=selected_auth_method.value if selected_auth_method else None,
            model=model,
            reasoning=selected_reasoning.value if selected_reasoning else None,
            auto_create_pr=auto_create_pr,
        )
        config_path = Path(repo_path) / CONFIG_FILE

    return ProviderConfig(
        provider=provider,
        config_path=config_path,
        auth_method=(
            AuthMethod(saved_config.auth_method) if saved_config.auth_method else None
        ),
        model=saved_config.model,
        reasoning=(
            ReasoningLevel(saved_config.reasoning) if saved_config.reasoning else None
        ),
    )


def load_selected_provider(repo_path: str | Path = ".") -> ProviderConfig | None:
    """Load the selected provider when the project has one."""
    config_path = Path(repo_path) / CONFIG_FILE
    if not config_path.exists():
        return None

    config = load_project_config(repo_path)
    if config.provider is None:
        return None

    return ProviderConfig(
        provider=Provider(config.provider),
        config_path=config_path,
        auth_method=AuthMethod(config.auth_method) if config.auth_method else None,
        model=config.model,
        reasoning=ReasoningLevel(config.reasoning) if config.reasoning else None,
    )


def _provider_setup(
    *,
    provider: Provider,
    display_name: str,
    auth_methods: tuple[AuthMethod, ...],
    env_var: str | None,
    note: str,
    environment: Mapping[str, str],
) -> ProviderSetup:
    configured = env_var is None or bool(environment.get(env_var))
    return ProviderSetup(
        provider=provider,
        display_name=display_name,
        auth_methods=auth_methods,
        env_var=env_var,
        configured=configured,
        note=note,
    )
