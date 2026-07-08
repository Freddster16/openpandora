from types import SimpleNamespace

import pytest

from openpandora.openai_account import (
    OpenAIAccountAuthError,
    ensure_openai_account_auth,
)


def test_ensure_openai_account_auth_reuses_existing_chatgpt_login():
    calls = []

    def fake_runner(arguments, **kwargs):
        calls.append(arguments)
        return SimpleNamespace(
            returncode=0,
            stdout="Logged in using ChatGPT",
            stderr="",
        )

    result = ensure_openai_account_auth(
        runner=fake_runner,
        output_func=lambda text: None,
    )

    assert result.already_signed_in is True
    assert calls == [["codex", "login", "status"]]


def test_ensure_openai_account_auth_runs_login_when_status_is_not_chatgpt():
    calls = []

    def fake_runner(arguments, **kwargs):
        calls.append(arguments)
        if arguments == ["codex", "login", "status"] and len(calls) == 1:
            return SimpleNamespace(returncode=1, stdout="", stderr="")
        if arguments == ["codex", "login"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        return SimpleNamespace(
            returncode=0,
            stdout="Logged in using ChatGPT",
            stderr="",
        )

    result = ensure_openai_account_auth(
        runner=fake_runner,
        output_func=lambda text: None,
    )

    assert result.already_signed_in is False
    assert calls == [
        ["codex", "login", "status"],
        ["codex", "login"],
        ["codex", "login", "status"],
    ]


def test_ensure_openai_account_auth_reports_missing_codex():
    def fake_runner(arguments, **kwargs):
        raise FileNotFoundError(arguments[0])

    with pytest.raises(OpenAIAccountAuthError, match="Codex CLI"):
        ensure_openai_account_auth(runner=fake_runner, output_func=lambda text: None)
