import os
import subprocess

import pytest

from openpandora.hooks import (
    HookError,
    install_git_hooks,
    install_global_git_hooks,
    is_git_repo,
)


def test_install_git_hooks_writes_managed_wake_hooks(tmp_path):
    _init_git_repo(tmp_path)

    result = install_git_hooks(
        tmp_path,
        create_pr=True,
        executable="/tmp/open pandora",
    )

    assert result.post_commit_hook.exists()
    assert result.pre_push_hook.exists()
    assert (
        "exec '/tmp/open pandora' wake --event commit --create-pr"
        in result.post_commit_hook.read_text()
    )
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


def test_install_global_git_hooks_writes_computer_wide_hooks(tmp_path):
    hooks_dir = tmp_path / "global-hooks"

    result = install_global_git_hooks(
        executable="/tmp/open pandora",
        hooks_dir=hooks_dir,
    )

    configured_hooks_path = subprocess.run(
        ["git", "config", "--global", "--get", "core.hooksPath"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert configured_hooks_path.stdout.strip() == str(hooks_dir)
    assert result.post_commit_hook.exists()
    assert result.pre_push_hook.exists()
    assert "openpandora_command='/tmp/open pandora'" in result.pre_push_hook.read_text()
    assert 'wake --event "$event"' in result.pre_push_hook.read_text()
    assert os.access(result.post_commit_hook, os.X_OK)
    assert os.access(result.pre_push_hook, os.X_OK)


def test_install_global_git_hooks_chains_previous_global_hooks_path(tmp_path):
    previous_hooks_dir = tmp_path / "previous-hooks"
    subprocess.run(
        ["git", "config", "--global", "core.hooksPath", str(previous_hooks_dir)],
        check=True,
    )

    result = install_global_git_hooks(
        executable="openpandora",
        hooks_dir=tmp_path / "openpandora-hooks",
    )

    assert result.previous_hooks_path == str(previous_hooks_dir)
    assert (
        f"previous_hooks_path={previous_hooks_dir}" in result.pre_push_hook.read_text()
    )


def test_install_global_git_hooks_chains_tilde_previous_hooks_path(
    tmp_path,
    monkeypatch,
):
    home_dir = tmp_path / "home"
    previous_hooks_dir = home_dir / "previous-hooks"
    previous_hooks_dir.mkdir(parents=True)
    previous_post_commit = previous_hooks_dir / "post-commit"
    previous_post_commit.write_text(
        "#!/bin/sh\nprintf 'previous\\n' >> \"$OPENPANDORA_TEST_LOG\"\n"
    )
    previous_post_commit.chmod(0o755)

    fake_openpandora = tmp_path / "openpandora"
    fake_openpandora.write_text(
        "#!/bin/sh\nprintf 'openpandora\\n' >> \"$OPENPANDORA_TEST_LOG\"\n"
    )
    fake_openpandora.chmod(0o755)

    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
    monkeypatch.setenv("HOME", str(home_dir))
    subprocess.run(
        ["git", "config", "--global", "core.hooksPath", "~/previous-hooks"],
        check=True,
    )

    result = install_global_git_hooks(
        executable=str(fake_openpandora),
        hooks_dir=tmp_path / "openpandora-hooks",
    )

    log_path = tmp_path / "wake.log"
    env = os.environ | {"OPENPANDORA_TEST_LOG": str(log_path)}
    subprocess.run(
        [str(result.post_commit_hook)],
        cwd=repo_path,
        env=env,
        check=True,
    )

    assert result.previous_hooks_path == "~/previous-hooks"
    assert log_path.read_text().splitlines() == ["openpandora", "previous"]


def test_is_git_repo_returns_false_outside_git(tmp_path):
    assert is_git_repo(tmp_path) is False


def _init_git_repo(path):
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
