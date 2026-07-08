from openpandora.checks import run_local_checks
from openpandora.findings import Severity
from openpandora.git_context import ChangedLine, RepoContext


def test_run_local_checks_returns_no_findings_when_matching_test_changes(tmp_path):
    context = RepoContext(
        branch_name="feature/demo",
        current_commit="abc123",
        changed_files=("src/openpandora/cli.py", "tests/test_cli.py"),
    )

    assert run_local_checks(context, tmp_path) == ()


def test_run_local_checks_warns_when_source_changes_without_matching_test(tmp_path):
    context = RepoContext(
        branch_name="feature/demo",
        current_commit="abc123",
        changed_files=("src/openpandora/cli.py", "tests/test_git_context.py"),
    )

    findings = run_local_checks(context, tmp_path)

    assert len(findings) == 1
    assert findings[0].title == "Add a focused test"
    assert findings[0].severity is Severity.WARNING
    assert findings[0].location == "src/openpandora/cli.py"
    assert "tests/test_cli.py" in findings[0].suggestion


def test_run_local_checks_warns_for_swift_app_source_without_matching_test(tmp_path):
    context = RepoContext(
        branch_name="feature/swift",
        current_commit="abc123",
        changed_files=("Ergio/ErgioApp.swift",),
    )

    findings = run_local_checks(context, tmp_path)

    assert len(findings) == 1
    assert findings[0].title == "Add a focused test"
    assert findings[0].location == "Ergio/ErgioApp.swift"
    assert "ErgioTests/ErgioAppTests.swift" in findings[0].suggestion


def test_run_local_checks_ignores_swift_test_changes(tmp_path):
    context = RepoContext(
        branch_name="feature/swift",
        current_commit="abc123",
        changed_files=("ErgioTests/FocusSessionControllerTests.swift",),
    )

    assert run_local_checks(context, tmp_path) == ()


def test_run_local_checks_accepts_matching_swift_test_change(tmp_path):
    context = RepoContext(
        branch_name="feature/swift",
        current_commit="abc123",
        changed_files=(
            "Ergio/ErgioApp.swift",
            "ErgioTests/ErgioAppTests.swift",
        ),
    )

    assert run_local_checks(context, tmp_path) == ()


def test_run_local_checks_flags_secret_like_strings(tmp_path):
    secret_name = "API" + "_KEY"
    secret_value = "sk-" + "abcdefghijklmnopqrstuvwxyz123456"
    context = RepoContext(
        branch_name="feature/demo",
        current_commit="abc123",
        changed_files=("config.py",),
        changed_lines=(
            ChangedLine(
                file_path="config.py",
                line_number=12,
                content=f"{secret_name} = {secret_value!r}",
            ),
        ),
    )

    findings = run_local_checks(context, tmp_path)

    assert len(findings) == 1
    assert findings[0].title == "Possible secret in code"
    assert findings[0].severity is Severity.ERROR
    assert findings[0].location == "config.py:12"
    assert "environment variable" in findings[0].suggestion


def test_run_local_checks_does_not_scan_unchanged_secret_like_strings(tmp_path):
    unchanged_secret = "sk-" + "abcdefghijklmnopqrstuvwxyz123456"
    context = RepoContext(
        branch_name="feature/demo",
        current_commit="abc123",
        changed_files=("config.py",),
        changed_lines=(
            ChangedLine(
                file_path="config.py",
                line_number=1,
                content=f"# existing secret nearby: {unchanged_secret[:6]}",
            ),
        ),
    )

    assert run_local_checks(context, tmp_path) == ()


def test_run_local_checks_reports_each_file_once_for_secret_like_strings(tmp_path):
    first_name = "TO" + "KEN"
    first_value = "sk-" + "abcdefghijklmnopqrstuvwxyz123456"
    second_name = "PASS" + "WORD"
    second_value = "super-secret-password"
    context = RepoContext(
        branch_name="feature/demo",
        current_commit="abc123",
        changed_files=("settings.py",),
        changed_lines=(
            ChangedLine(
                file_path="settings.py",
                line_number=1,
                content=f"{first_name} = {first_value!r}",
            ),
            ChangedLine(
                file_path="settings.py",
                line_number=2,
                content=f"{second_name} = {second_value!r}",
            ),
        ),
    )

    findings = run_local_checks(context, tmp_path)

    assert len(findings) == 1
    assert findings[0].location == "settings.py:1"
