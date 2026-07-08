from openpandora.findings import Finding, Severity
from openpandora.git_context import RepoContext
from openpandora.learned_rules import LearnedRule
from openpandora.pull_requests import build_pr_body


def test_build_pr_body_summarizes_no_findings():
    context = RepoContext(
        branch_name="feature/demo",
        current_commit="abc123def4567890",
        changed_files=("README.md",),
    )

    body = build_pr_body(context, ())

    assert "# OpenPandora QA" in body
    assert "Branch: `feature/demo`" in body
    assert "Commit: `abc123def456`" in body
    assert "OpenPandora did not find any issues" in body
    assert "- No findings." in body


def test_build_pr_body_summarizes_findings_and_rules():
    context = RepoContext(
        branch_name="feature/demo",
        current_commit="abc123def4567890",
        changed_files=("src/openpandora/cli.py",),
        base_ref="main",
    )
    finding = Finding(
        title="Add a focused test",
        message="A source file changed without a matching test.",
        severity=Severity.WARNING,
        file_path="src/openpandora/cli.py",
        suggestion="Add tests/test_cli.py.",
    )
    rule = LearnedRule(
        title="Prefer focused tests",
        message="Add a small pytest test with each behavior change.",
    )

    body = build_pr_body(context, (finding,), (rule,))

    assert "Compared with: `main`" in body
    assert "OpenPandora found 1 issue(s)" in body
    assert "`[warning]` Prefer focused tests" in body
    assert "`[warning]` Add a focused test at `src/openpandora/cli.py`" in body
    assert "OpenPandora has not changed any files" in body


def test_build_pr_body_can_describe_created_fix_pr():
    context = RepoContext(
        branch_name="feature/demo",
        current_commit="abc123def4567890",
        changed_files=("src/openpandora/cli.py",),
        base_ref="main",
    )
    finding = Finding(
        title="Add a focused test",
        message="A source file changed without a matching test.",
        severity=Severity.WARNING,
        file_path="src/openpandora/cli.py",
    )

    body = build_pr_body(context, (finding,), contains_fix=True)

    assert "This PR contains OpenPandora's proposed fix" in body
    assert "has not changed any files" not in body
