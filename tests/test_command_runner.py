from openpandora.command_runner import run_project_command, run_project_commands


def test_run_project_command_returns_success_output(tmp_path):
    result = run_project_command(
        "test",
        "python -c 'print(\"hello\")'",
        tmp_path,
    )

    assert result.passed is True
    assert result.return_code == 0
    assert result.stdout.strip() == "hello"
    assert result.stderr == ""


def test_run_project_command_returns_failure_output(tmp_path):
    result = run_project_command(
        "test",
        "python -c 'import sys; print(\"bad\"); sys.exit(7)'",
        tmp_path,
    )

    assert result.passed is False
    assert result.return_code == 7
    assert result.stdout.strip() == "bad"


def test_run_project_command_handles_missing_command(tmp_path):
    result = run_project_command("lint", "definitely-not-openpandora", tmp_path)

    assert result.passed is False
    assert result.return_code == 127
    assert "Command not found" in result.stderr


def test_run_project_command_handles_empty_command(tmp_path):
    result = run_project_command("test", "   ", tmp_path)

    assert result.passed is False
    assert result.return_code == 2
    assert result.stderr == "Command is empty."


def test_run_project_command_prefers_project_venv_python(tmp_path):
    python_path = tmp_path / ".venv" / "bin" / "python"
    python_path.parent.mkdir(parents=True)
    python_path.write_text("#!/bin/sh\nprintf 'venv python\\n'\n")
    python_path.chmod(0o700)

    result = run_project_command("test", "python -m pytest", tmp_path)

    assert result.passed is True
    assert result.stdout == "venv python\n"


def test_run_project_commands_runs_in_order(tmp_path):
    results = run_project_commands(
        (
            ("first", "python -c 'print(\"one\")'"),
            ("second", "python -c 'print(\"two\")'"),
        ),
        tmp_path,
    )

    assert [result.name for result in results] == ["first", "second"]
    assert [result.stdout.strip() for result in results] == ["one", "two"]
