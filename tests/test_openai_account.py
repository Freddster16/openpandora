from types import SimpleNamespace

import pytest

from openpandora.openai_account import (
    CODEX_INSTALL_URL_ENV_VAR,
    OpenAIAccountAuthError,
    ensure_openai_account_auth,
    install_codex_cli,
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


def test_ensure_openai_account_auth_installs_missing_codex_then_logs_in():
    calls = []
    install_calls = []

    def fake_runner(arguments, **kwargs):
        calls.append(arguments)
        if len(calls) == 1:
            raise FileNotFoundError(arguments[0])
        if arguments == ["codex", "login", "status"] and len(calls) == 2:
            return SimpleNamespace(returncode=1, stdout="", stderr="")
        if arguments == ["codex", "login"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        return SimpleNamespace(
            returncode=0,
            stdout="Logged in using ChatGPT",
            stderr="",
        )

    def fake_installer(**kwargs):
        install_calls.append(kwargs["command"])
        return "codex"

    result = ensure_openai_account_auth(
        runner=fake_runner,
        installer=fake_installer,
        output_func=lambda text: None,
    )

    assert result.already_signed_in is False
    assert result.installed_codex is True
    assert install_calls == ["codex"]
    assert calls == [
        ["codex", "login", "status"],
        ["codex", "login", "status"],
        ["codex", "login"],
        ["codex", "login", "status"],
    ]


def test_ensure_openai_account_auth_reports_failed_codex_install():
    def fake_runner(arguments, **kwargs):
        raise FileNotFoundError(arguments[0])

    def fake_installer(**kwargs):
        raise OpenAIAccountAuthError("installer failed")

    with pytest.raises(OpenAIAccountAuthError, match="installer failed"):
        ensure_openai_account_auth(
            runner=fake_runner,
            installer=fake_installer,
            output_func=lambda text: None,
        )


def test_install_codex_cli_rejects_non_official_url():
    with pytest.raises(OpenAIAccountAuthError, match="official installer"):
        install_codex_cli(
            environment={CODEX_INSTALL_URL_ENV_VAR: "http://example.test/install.sh"},
            output_func=lambda text: None,
        )


def test_install_codex_cli_downloads_and_runs_non_interactively(tmp_path, monkeypatch):
    install_calls = []
    home_dir = tmp_path / "home"
    codex_path = home_dir / ".local" / "bin" / "codex"

    class FakeDownload:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def read(self):
            return b"#!/bin/sh\n"

    def fake_urlopen(url, timeout):
        assert url == "https://chatgpt.com/codex/install.sh"
        assert timeout == 60
        return FakeDownload()

    def fake_runner(arguments, **kwargs):
        install_calls.append((arguments, kwargs))
        codex_path.parent.mkdir(parents=True)
        codex_path.write_text("#!/bin/sh\n")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    command = install_codex_cli(
        environment={"HOME": str(home_dir), "PATH": ""},
        runner=fake_runner,
        output_func=lambda text: None,
    )

    assert command == str(codex_path)
    assert install_calls[0][0][0] == "sh"
    assert install_calls[0][1]["env"]["CODEX_NON_INTERACTIVE"] == "1"
