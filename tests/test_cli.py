import pytest

from openpandora import __version__
from openpandora.cli import main


def test_check_command_is_available(capsys):
    assert main(["check"]) == 0

    output = capsys.readouterr().out
    assert "OpenPandora is ready." in output
    assert "No QA checks are connected yet." in output


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
