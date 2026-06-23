from openpandora.command_runner import CommandResult
from openpandora.findings import Finding, Severity
from openpandora.git_context import RepoContext
from openpandora.learned_rules import LearnedRule
from openpandora.review import ReviewRequest, build_review, build_review_report


def test_build_review_reports_no_issues_when_evidence_is_clean():
    request = ReviewRequest(
        provider="local",
        context=RepoContext(
            branch_name="feature/demo",
            current_commit="abc123def4567890",
            changed_files=("README.md",),
            base_ref="main",
        ),
        findings=(),
        command_results=(
            CommandResult("Tests", "python -m pytest", 0, "", ""),
            CommandResult("Lint", "ruff check .", 0, "", ""),
        ),
    )

    result = build_review(request)
    report = build_review_report(request, result)

    assert result.has_issues is False
    assert "OpenPandora did not find anything to improve" in result.summary
    assert "Provider: local" in report
    assert "Compared with: main" in report
    assert "- Tests: passed" in report
    assert "- No changes suggested." in report


def test_build_review_turns_findings_and_failed_commands_into_suggestions():
    finding = Finding(
        title="Add a focused test",
        message="A source file changed without a matching test.",
        severity=Severity.WARNING,
        suggestion="Add tests/test_cli.py.",
    )
    request = ReviewRequest(
        provider="local",
        context=RepoContext(
            branch_name="feature/demo",
            current_commit="abc123def4567890",
            changed_files=("src/openpandora/cli.py",),
        ),
        findings=(finding,),
        learned_rules=(
            LearnedRule(
                title="Prefer focused tests",
                message="Add a small test.",
            ),
        ),
        command_results=(CommandResult("Tests", "python -m pytest", 1, "", "failed"),),
    )

    result = build_review(request)
    report = build_review_report(request, result)

    assert result.has_issues is True
    assert "Add tests/test_cli.py." in result.suggestions
    assert "Fix the failing tests command" in result.suggestions[1]
    assert "Learned rules loaded:" in report
    assert "- [warning] Prefer focused tests" in report
    assert "- Tests: failed" in report


def test_build_review_reports_provider_setup_errors_as_issues():
    request = ReviewRequest(
        provider="openai",
        context=RepoContext(
            branch_name="feature/demo",
            current_commit="abc123def4567890",
            changed_files=("README.md",),
        ),
        findings=(),
    )

    result = build_review(request, provider_error="OpenAI key missing.")
    report = build_review_report(request, result)

    assert result.has_issues is True
    assert "Provider setup:" in report
    assert "OpenAI key missing." in report


def test_build_review_report_includes_provider_text():
    request = ReviewRequest(
        provider="openai",
        context=RepoContext(
            branch_name="feature/demo",
            current_commit="abc123def4567890",
            changed_files=("README.md",),
        ),
        findings=(),
    )

    result = build_review(request, provider_text="AI review text.")
    report = build_review_report(request, result)

    assert "Provider review:" in report
    assert "AI review text." in report
