from openpandora.checks import run_local_checks
from openpandora.git_context import RepoContext


def test_run_local_checks_returns_no_findings_for_initial_version():
    context = RepoContext(
        branch_name="feature/demo",
        current_commit="abc123",
        changed_files=("src/openpandora/cli.py",),
    )

    assert run_local_checks(context) == ()
