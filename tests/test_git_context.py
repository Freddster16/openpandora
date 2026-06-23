import subprocess

import pytest

from openpandora.git_context import GitCommandError, collect_repo_context


def test_collect_repo_context_reads_branch_commit_and_changed_files(monkeypatch):
    outputs = {
        ("rev-parse", "--abbrev-ref", "HEAD"): "feature/demo\n",
        ("rev-parse", "HEAD"): "abc123\n",
        (
            "diff-tree",
            "--root",
            "--no-commit-id",
            "--name-only",
            "-r",
            "HEAD",
        ): "src/openpandora/cli.py\ntests/test_cli.py\n",
    }

    def fake_run(command, cwd, text, capture_output, check):
        assert command[0] == "git"
        assert str(cwd) == "."
        assert text is True
        assert capture_output is True
        assert check is False
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=outputs[tuple(command[1:])],
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    context = collect_repo_context()

    assert context.branch_name == "feature/demo"
    assert context.current_commit == "abc123"
    assert context.changed_files == (
        "src/openpandora/cli.py",
        "tests/test_cli.py",
    )


def test_collect_repo_context_explains_git_failures(monkeypatch):
    def fake_run(command, cwd, text, capture_output, check):
        return subprocess.CompletedProcess(
            command,
            128,
            stdout="",
            stderr="fatal: not a git repository\n",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(GitCommandError, match="not a git repository"):
        collect_repo_context()


def test_collect_repo_context_reads_a_real_initial_commit(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / "README.md").write_text("# demo\n")
    _git(tmp_path, "add", "README.md")
    _git(tmp_path, "commit", "-m", "docs: add readme")

    context = collect_repo_context(tmp_path)

    assert context.branch_name == "main"
    assert context.current_commit == _git(tmp_path, "rev-parse", "HEAD")
    assert context.changed_files == ("README.md",)


def test_collect_repo_context_reads_only_the_latest_real_commit(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / "README.md").write_text("# demo\n")
    _git(tmp_path, "add", "README.md")
    _git(tmp_path, "commit", "-m", "docs: add readme")

    package_path = tmp_path / "src" / "demo.py"
    package_path.parent.mkdir()
    package_path.write_text("print('hello')\n")
    (tmp_path / "README.md").write_text("# demo\n\nMore notes.\n")
    _git(tmp_path, "add", "README.md", "src/demo.py")
    _git(tmp_path, "commit", "-m", "feat: add demo file")

    context = collect_repo_context(tmp_path)

    assert context.branch_name == "main"
    assert context.current_commit == _git(tmp_path, "rev-parse", "HEAD")
    assert set(context.changed_files) == {"README.md", "src/demo.py"}


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
