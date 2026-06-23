from openpandora.findings import Finding, Severity
from openpandora.git_context import RepoContext
from openpandora.history import load_history, record_findings, record_fix


def test_record_findings_appends_readable_history(tmp_path):
    context = RepoContext(
        branch_name="feature/demo",
        current_commit="abc123",
        changed_files=("src/demo.py",),
        base_ref="main",
    )
    finding = Finding(
        title="Add a focused test",
        message="A source file changed without a test.",
        severity=Severity.WARNING,
        file_path="src/demo.py",
        suggestion="Add tests/test_demo.py.",
    )

    result = record_findings(context, (finding,), tmp_path)

    assert result is not None
    assert result.path == tmp_path / ".openpandora" / "history.jsonl"

    events = load_history(tmp_path)
    assert len(events) == 1
    assert events[0]["type"] == "findings"
    assert events[0]["branch"] == "feature/demo"
    assert events[0]["base_ref"] == "main"
    assert events[0]["findings"][0]["title"] == "Add a focused test"
    assert events[0]["findings"][0]["severity"] == "warning"


def test_record_findings_skips_empty_findings(tmp_path):
    context = RepoContext(
        branch_name="feature/demo",
        current_commit="abc123",
        changed_files=(),
    )

    assert record_findings(context, (), tmp_path) is None
    assert load_history(tmp_path) == ()


def test_record_fix_appends_fix_history(tmp_path):
    context = RepoContext(
        branch_name="feature/demo",
        current_commit="abc123",
        changed_files=("src/demo.py",),
    )

    record_fix(
        context,
        tmp_path,
        fix_branch="openpandora/fix-feature-demo",
        commit_hash="def456",
        pull_request_url="https://github.com/owner/repo/pull/1",
    )

    events = load_history(tmp_path)
    assert events[0]["type"] == "fix"
    assert events[0]["fix_branch"] == "openpandora/fix-feature-demo"
    assert events[0]["commit"] == "def456"
    assert events[0]["pull_request_url"] == "https://github.com/owner/repo/pull/1"
