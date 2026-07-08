from types import SimpleNamespace

import pytest

from openpandora.github_auth import (
    GitHubCliAuthError,
    GitHubCliMissingError,
    ensure_github_cli_auth,
)


def test_ensure_github_cli_auth_reuses_existing_login():
    calls = []
    output = []

    def fake_runner(arguments, **kwargs):
        calls.append(arguments)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    result = ensure_github_cli_auth(
        runner=fake_runner,
        output_func=output.append,
    )

    assert result.already_signed_in is True
    assert result.used_token is False
    assert calls == [["gh", "auth", "status", "--hostname", "github.com"]]
    assert "already signed in" in "\n".join(output)


def test_ensure_github_cli_auth_runs_login_when_status_fails():
    calls = []

    def fake_runner(arguments, **kwargs):
        calls.append(arguments)
        if arguments == ["gh", "auth", "status", "--hostname", "github.com"]:
            return SimpleNamespace(
                returncode=0 if len(calls) == 3 else 1,
                stdout="",
                stderr="",
            )
        if arguments == ["gh", "auth", "login", "--hostname", "github.com", "--web"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        raise AssertionError(arguments)

    result = ensure_github_cli_auth(
        runner=fake_runner,
        output_func=lambda text: None,
    )

    assert result.already_signed_in is False
    assert calls == [
        ["gh", "auth", "status", "--hostname", "github.com"],
        ["gh", "auth", "login", "--hostname", "github.com", "--web"],
        ["gh", "auth", "status", "--hostname", "github.com"],
    ]


def test_ensure_github_cli_auth_accepts_existing_token():
    output = []

    def fail_runner(arguments, **kwargs):
        raise AssertionError("gh should not run when GITHUB_TOKEN is set")

    result = ensure_github_cli_auth(
        environment={"GITHUB_TOKEN": "secret-value"},
        runner=fail_runner,
        output_func=output.append,
    )

    assert result.used_token is True
    assert result.already_signed_in is True
    assert "secret-value" not in "\n".join(output)


def test_ensure_github_cli_auth_reports_missing_gh():
    def fake_runner(arguments, **kwargs):
        raise FileNotFoundError(arguments[0])

    with pytest.raises(GitHubCliMissingError, match="GitHub CLI"):
        ensure_github_cli_auth(
            runner=fake_runner,
            output_func=lambda text: None,
        )


def test_ensure_github_cli_auth_reports_failed_login():
    def fake_runner(arguments, **kwargs):
        if arguments == ["gh", "auth", "status", "--hostname", "github.com"]:
            return SimpleNamespace(returncode=1, stdout="", stderr="")
        return SimpleNamespace(returncode=1, stdout="", stderr="")

    with pytest.raises(GitHubCliAuthError, match="login"):
        ensure_github_cli_auth(
            runner=fake_runner,
            output_func=lambda text: None,
        )
