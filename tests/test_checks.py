from openpandora.checks import run_local_checks
from openpandora.findings import Severity
from openpandora.git_context import RepoContext


def test_run_local_checks_returns_no_findings_when_source_and_tests_change(tmp_path):
    context = RepoContext(
        branch_name="feature/demo",
        current_commit="abc123",
        changed_files=("src/openpandora/cli.py", "tests/test_cli.py"),
    )

    assert run_local_checks(context, tmp_path) == ()


def test_run_local_checks_warns_when_source_changes_without_tests(tmp_path):
    context = RepoContext(
        branch_name="feature/demo",
        current_commit="abc123",
        changed_files=("src/openpandora/cli.py",),
    )

    findings = run_local_checks(context, tmp_path)

    assert len(findings) == 1
    assert findings[0].title == "Add a focused test"
    assert findings[0].severity is Severity.WARNING
    assert "src/openpandora/cli.py" in findings[0].suggestion


def test_run_local_checks_flags_secret_like_strings(tmp_path):
    secret_file = tmp_path / "config.py"
    secret_name = "API" + "_KEY"
    secret_value = "sk-" + "abcdefghijklmnopqrstuvwxyz123456"
    secret_file.write_text(f"{secret_name} = {secret_value!r}\n")
    context = RepoContext(
        branch_name="feature/demo",
        current_commit="abc123",
        changed_files=("config.py",),
    )

    findings = run_local_checks(context, tmp_path)

    assert len(findings) == 1
    assert findings[0].title == "Possible secret in code"
    assert findings[0].severity is Severity.ERROR
    assert findings[0].location == "config.py:1"
    assert "environment variable" in findings[0].suggestion


def test_run_local_checks_skips_missing_changed_files(tmp_path):
    context = RepoContext(
        branch_name="feature/demo",
        current_commit="abc123",
        changed_files=("deleted.py",),
    )

    assert run_local_checks(context, tmp_path) == ()


def test_run_local_checks_reports_each_file_once_for_secret_like_strings(tmp_path):
    secret_file = tmp_path / "settings.py"
    first_name = "TO" + "KEN"
    first_value = "sk-" + "abcdefghijklmnopqrstuvwxyz123456"
    second_name = "PASS" + "WORD"
    second_value = "super-secret-password"
    secret_file.write_text(
        f"{first_name} = {first_value!r}\n{second_name} = {second_value!r}\n"
    )
    context = RepoContext(
        branch_name="feature/demo",
        current_commit="abc123",
        changed_files=("settings.py",),
    )

    findings = run_local_checks(context, tmp_path)

    assert len(findings) == 1
    assert findings[0].location == "settings.py:1"
