import subprocess

import pytest

from openpandora.git_changes import (
    GitChangeError,
    build_fix_branch_name,
    commit_all_changes,
    create_fix_branch,
    has_worktree_changes,
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
