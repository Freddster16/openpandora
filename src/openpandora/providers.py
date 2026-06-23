"""Describe AI provider auth options without touching secrets."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum


class Provider(StrEnum):
    """Name a supported AI provider choice."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    LOCAL = "local"


class AuthMethod(StrEnum):
    """Name how a provider can be authenticated."""

    ENVIRONMENT = "environment"
    GUIDED = "guided"
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


def list_provider_setups(
    environment: Mapping[str, str] | None = None,
) -> tuple[ProviderSetup, ...]:
    """List provider setup options without reading secret values."""
    current_environment = os.environ if environment is None else environment
    return (
        _provider_setup(
            provider=Provider.OPENAI,
            display_name="OpenAI",
            auth_methods=(AuthMethod.ENVIRONMENT, AuthMethod.GUIDED),
            env_var="OPENAI_API_KEY",
            note="Use an API key today; guided auth is planned.",
            environment=current_environment,
        ),
        _provider_setup(
            provider=Provider.ANTHROPIC,
            display_name="Anthropic",
            auth_methods=(AuthMethod.ENVIRONMENT, AuthMethod.GUIDED),
            env_var="ANTHROPIC_API_KEY",
            note="Use an API key today; guided auth is planned.",
            environment=current_environment,
        ),
        _provider_setup(
            provider=Provider.LOCAL,
            display_name="Local",
            auth_methods=(AuthMethod.NONE,),
            env_var=None,
            note="Reserved for local or self-hosted model review later.",
            environment=current_environment,
        ),
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
