import subprocess

import pytest

from openpandora.git_changes import (
    GitChangeError,
    build_fix_branch_name,
    commit_all_changes,
    create_fix_branch,
    has_worktree_changes,
    is_openpandora_fix_branch,
    plan_fix_attempt,
)


def test_create_fix_branch_switches_to_named_branch(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / "demo.txt").write_text("hello\n")
    _git(tmp_path, "add", "demo.txt")
    _git(tmp_path, "commit", "-m", "docs: add demo")

    branch_name = create_fix_branch("openpandora/fix-demo", tmp_path)

    assert branch_name == "openpandora/fix-demo"
    assert _git(tmp_path, "rev-parse", "--abbrev-ref", "HEAD") == branch_name


def test_build_fix_branch_name_sanitizes_source_branch():
    assert (
        build_fix_branch_name("feature/demo branch")
        == "openpandora/fix-feature-demo-branch"
    )


def test_build_fix_branch_name_includes_attempt_after_first_try():
    assert (
        build_fix_branch_name("feature/demo branch", 2)
        == "openpandora/fix-feature-demo-branch-attempt-2"
    )


def test_is_openpandora_fix_branch_detects_generated_branches():
    assert is_openpandora_fix_branch("openpandora/fix-feature-demo") is True
    assert is_openpandora_fix_branch("feature/demo") is False


def test_plan_fix_attempt_uses_next_attempt_branch(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / "demo.txt").write_text("hello\n")
    _git(tmp_path, "add", "demo.txt")
    _git(tmp_path, "commit", "-m", "docs: add demo")
    _git(tmp_path, "branch", "openpandora/fix-feature-demo")
    _git(tmp_path, "branch", "openpandora/fix-feature-demo-attempt-2")

    plan = plan_fix_attempt("feature/demo", tmp_path)

    assert plan is not None
    assert plan.branch_name == "openpandora/fix-feature-demo-attempt-3"
    assert plan.attempt_number == 3
    assert plan.max_attempts == 4


def test_plan_fix_attempt_stops_after_four_attempts(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / "demo.txt").write_text("hello\n")
    _git(tmp_path, "add", "demo.txt")
    _git(tmp_path, "commit", "-m", "docs: add demo")
    _git(tmp_path, "branch", "openpandora/fix-feature-demo")
    _git(tmp_path, "branch", "openpandora/fix-feature-demo-attempt-2")
    _git(tmp_path, "branch", "openpandora/fix-feature-demo-attempt-3")
    _git(tmp_path, "branch", "openpandora/fix-feature-demo-attempt-4")

    assert plan_fix_attempt("feature/demo", tmp_path) is None


def test_commit_all_changes_stages_and_commits_worktree(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / "demo.txt").write_text("hello\n")
    _git(tmp_path, "add", "demo.txt")
    _git(tmp_path, "commit", "-m", "docs: add demo")

    (tmp_path / "demo.txt").write_text("hello world\n")

    assert has_worktree_changes(tmp_path) is True
    commit_hash = commit_all_changes("fix: update demo", tmp_path)

    assert commit_hash == _git(tmp_path, "rev-parse", "HEAD")
    assert has_worktree_changes(tmp_path) is False
    assert _git(tmp_path, "log", "--format=%s", "-1") == "fix: update demo"


def test_commit_all_changes_explains_empty_commit(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / "demo.txt").write_text("hello\n")
    _git(tmp_path, "add", "demo.txt")
    _git(tmp_path, "commit", "-m", "docs: add demo")

    with pytest.raises(GitChangeError, match="no changes"):
        commit_all_changes("fix: empty", tmp_path)


def _init_repo(repo_path):
    _git(repo_path, "init")
    _git(repo_path, "branch", "-M", "main")
    _git(repo_path, "config", "user.name", "OpenPandora Tests")
    _git(repo_path, "config", "user.email", "tests@example.com")


def _git(repo_path, *arguments):
    result = subprocess.run(
        ["git", *arguments],
        cwd=repo_path,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()
