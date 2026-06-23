import subprocess

import pytest

from openpandora.git_context import ChangedLine, GitCommandError, collect_repo_context


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
        (
            "show",
            "--format=",
            "--unified=0",
            "HEAD",
        ): (
            "diff --git a/src/openpandora/cli.py b/src/openpandora/cli.py\n"
            "+++ b/src/openpandora/cli.py\n"
            "@@ -0,0 +1 @@\n"
            "+print('hello')\n"
        ),
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
    assert context.changed_lines == (
        ChangedLine(
            file_path="src/openpandora/cli.py",
            line_number=1,
            content="print('hello')",
        ),
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
    assert context.changed_lines == (
        ChangedLine(file_path="README.md", line_number=1, content="# demo"),
    )


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
    assert (
        ChangedLine(file_path="README.md", line_number=3, content="More notes.")
        in context.changed_lines
    )
    assert (
        ChangedLine(file_path="src/demo.py", line_number=1, content="print('hello')")
        in context.changed_lines
    )


def test_collect_repo_context_can_compare_against_a_base_ref(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / "README.md").write_text("# demo\n")
    _git(tmp_path, "add", "README.md")
    _git(tmp_path, "commit", "-m", "docs: add readme")

    _git(tmp_path, "checkout", "-b", "feature/demo")
    source_path = tmp_path / "src" / "demo.py"
    source_path.parent.mkdir()
    source_path.write_text("print('hello')\n")
    _git(tmp_path, "add", "src/demo.py")
    _git(tmp_path, "commit", "-m", "feat: add demo file")

    context = collect_repo_context(tmp_path, since_ref="main")

    assert context.branch_name == "feature/demo"
    assert context.base_ref == "main"
    assert context.changed_files == ("src/demo.py",)
    assert context.changed_lines == (
        ChangedLine(
            file_path="src/demo.py",
            line_number=1,
            content="print('hello')",
        ),
    )


def test_collect_repo_context_can_include_worktree_changes(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / "README.md").write_text("# demo\n")
    _git(tmp_path, "add", "README.md")
    _git(tmp_path, "commit", "-m", "docs: add readme")

    (tmp_path / "README.md").write_text("# demo\n\nWork in progress.\n")
    source_path = tmp_path / "src" / "demo.py"
    source_path.parent.mkdir()
    source_path.write_text("print('draft')\n")

    context = collect_repo_context(tmp_path, include_worktree=True)

    assert set(context.changed_files) == {"README.md", "src/demo.py"}
    assert (
        ChangedLine(file_path="README.md", line_number=3, content="Work in progress.")
        in context.changed_lines
    )
    assert (
        ChangedLine(file_path="src/demo.py", line_number=1, content="print('draft')")
        in context.changed_lines
    )


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
