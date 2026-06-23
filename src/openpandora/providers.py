"""Describe AI provider auth options without touching secrets."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from openpandora.project_config import (
    CONFIG_FILE,
    load_project_config,
    update_project_config,
)


class Provider(StrEnum):
    """Name a supported AI provider choice."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    LOCAL = "local"


class AuthMethod(StrEnum):
    """Name how a provider can be authenticated."""

    ENVIRONMENT = "environment"
    NONE = "none"


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
class ProviderConfig:
    """Describe the selected provider without storing secrets."""

    provider: Provider
    config_path: Path


def list_provider_setups(
    environment: Mapping[str, str] | None = None,
) -> tuple[ProviderSetup, ...]:
    """List provider setup options without reading secret values."""
    current_environment = os.environ if environment is None else environment
    return (
        _provider_setup(
            provider=Provider.OPENAI,
            display_name="OpenAI",
            auth_methods=(AuthMethod.ENVIRONMENT,),
            env_var="OPENAI_API_KEY",
            note="Use an API key from the environment.",
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


def select_provider(provider_name: str, repo_path: str | Path = ".") -> ProviderConfig:
    """Store the user's provider choice without storing API keys."""
    provider = Provider(provider_name)
    config_path = Path(repo_path) / CONFIG_FILE
    update_project_config(repo_path, provider=provider.value)
    return ProviderConfig(provider=provider, config_path=config_path)


def load_selected_provider(repo_path: str | Path = ".") -> ProviderConfig | None:
    """Load the selected provider when the project has one."""
    config_path = Path(repo_path) / CONFIG_FILE
    if not config_path.exists():
        return None

    config = load_project_config(repo_path)
    if config.provider is None:
        return None

    return ProviderConfig(provider=Provider(config.provider), config_path=config_path)


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
