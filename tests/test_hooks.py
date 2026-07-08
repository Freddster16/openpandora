import os
import subprocess

import pytest

from openpandora.hooks import HookError, install_git_hooks, is_git_repo


def test_install_git_hooks_writes_managed_wake_hooks(tmp_path):
    _init_git_repo(tmp_path)

    result = install_git_hooks(tmp_path, create_pr=True, executable="openpandora")

    assert result.post_commit_hook.exists()
    assert result.pre_push_hook.exists()
    assert "wake --event commit --create-pr" in result.post_commit_hook.read_text()
    assert "wake --event push --create-pr" in result.pre_push_hook.read_text()
    assert os.access(result.post_commit_hook, os.X_OK)
    assert os.access(result.pre_push_hook, os.X_OK)


def test_install_git_hooks_refuses_to_overwrite_user_hooks(tmp_path):
    _init_git_repo(tmp_path)
    hook_path = tmp_path / ".git" / "hooks" / "post-commit"
    hook_path.write_text("#!/bin/sh\necho user hook\n")

    with pytest.raises(HookError, match="not created by OpenPandora"):
        install_git_hooks(tmp_path)


def test_is_git_repo_returns_false_outside_git(tmp_path):
    assert is_git_repo(tmp_path) is False


def _init_git_repo(path):
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
