import pytest

from openpandora.findings import Finding, Severity, finding_label


def test_finding_defaults_to_warning_without_location():
    finding = Finding(
        title="Tests were not run",
        message="Run the test suite before pushing so problems are easier to fix.",
    )

    assert finding.severity is Severity.WARNING
    assert finding.location is None
    assert finding.suggestion is None


def test_finding_formats_file_location_with_line_number():
    finding = Finding(
        title="Possible typo",
        message="This line may contain a typo.",
        severity=Severity.INFO,
        file_path="src/openpandora/cli.py",
        line_number=12,
        suggestion="Double-check the wording before shipping.",
    )

    assert finding.location == "src/openpandora/cli.py:12"


def test_finding_formats_file_location_without_line_number():
    finding = Finding(
        title="Missing tests",
        message="This file changed without a matching test update.",
        file_path="src/openpandora/git_context.py",
    )

    assert finding.location == "src/openpandora/git_context.py"


def test_finding_label_includes_location_when_available():
    finding = Finding(
        title="Missing tests",
        message="This file changed without a matching test update.",
        file_path="src/openpandora/findings.py",
    )

    assert finding_label(finding) == "Missing tests (src/openpandora/findings.py)"


def test_finding_requires_a_title():
    with pytest.raises(ValueError, match="title is required"):
        Finding(title=" ", message="Use a short explanation.")


def test_finding_requires_a_message():
    with pytest.raises(ValueError, match="message is required"):
        Finding(title="Missing explanation", message="")


def test_finding_rejects_zero_line_number():
    with pytest.raises(ValueError, match="line number must be 1 or greater"):
        Finding(
            title="Invalid line",
            message="Line numbers should match editor line numbers.",
            line_number=0,
        )
