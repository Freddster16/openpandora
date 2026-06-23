import pytest

from openpandora import __version__, cli
from openpandora.cli import main
from openpandora.findings import Finding, Severity
from openpandora.git_context import GitCommandError, RepoContext


def test_check_command_reports_no_issues(monkeypatch, capsys):
    context = RepoContext(
        branch_name="feature/demo",
        current_commit="abc123def4567890",
        changed_files=("src/openpandora/cli.py",),
    )
    monkeypatch.setattr(cli, "collect_repo_context", lambda repo_path=".": context)
    monkeypatch.setattr(cli, "load_learned_rules", lambda repo_path=".": ())
    monkeypatch.setattr(cli, "run_local_checks", lambda repo_context: ())

    assert main(["check"]) == 0

    output = capsys.readouterr().out
    assert "OpenPandora check" in output
    assert "Branch: feature/demo" in output
    assert "Commit: abc123def456" in output
    assert "Changed files: 1" in output
    assert "No issues found." in output


def test_check_command_reports_findings(monkeypatch, capsys):
    context = RepoContext(
        branch_name="feature/demo",
        current_commit="abc123def4567890",
        changed_files=("src/openpandora/cli.py",),
    )
    finding = Finding(
        title="Add a test",
        message="This change should include a focused test.",
        severity=Severity.ERROR,
        file_path="src/openpandora/cli.py",
        line_number=10,
        suggestion="Add a pytest case for the new behavior.",
    )
    monkeypatch.setattr(cli, "collect_repo_context", lambda repo_path=".": context)
    monkeypatch.setattr(cli, "load_learned_rules", lambda repo_path=".": ())
    monkeypatch.setattr(cli, "run_local_checks", lambda repo_context: (finding,))

    assert main(["check"]) == 1

    output = capsys.readouterr().out
    assert "Found 1 issue(s):" in output
    assert "[error] Add a test (src/openpandora/cli.py:10)" in output
    assert "Suggestion: Add a pytest case for the new behavior." in output


def test_check_command_explains_git_errors(monkeypatch, capsys):
    def raise_git_error(repo_path="."):
        raise GitCommandError("fatal: not a git repository")

    monkeypatch.setattr(cli, "collect_repo_context", raise_git_error)

    assert main(["check"]) == 1

    output = capsys.readouterr().out
    assert "OpenPandora could not check this project." in output
    assert "not a git repository" in output


def test_version_flag_shows_current_version(capsys):
    with pytest.raises(SystemExit) as error:
        main(["--version"])

    assert error.value.code == 0
    assert f"openpandora {__version__}" in capsys.readouterr().out


def test_help_lists_check_command(capsys):
    with pytest.raises(SystemExit) as error:
        main(["--help"])

    assert error.value.code == 0
    output = capsys.readouterr().out
    assert "Run beginner-friendly QA feedback for your code." in output
    assert "check" in output


def test_missing_command_exits_with_usage(capsys):
    with pytest.raises(SystemExit) as error:
        main([])

    assert error.value.code == 2
    error_output = capsys.readouterr().err
    assert "usage:" in error_output
    assert "the following arguments are required: command" in error_output
