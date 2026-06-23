import subprocess

import pytest

from openpandora.patches import PatchError, apply_unified_diff, extract_unified_diff

PATCH_TEXT = """diff --git a/demo.txt b/demo.txt
--- a/demo.txt
+++ b/demo.txt
@@ -1 +1 @@
-hello
+hello world
"""


def test_extract_unified_diff_reads_fenced_diff_block():
    text = f"Here is the fix:\n\n```diff\n{PATCH_TEXT}```\n"

    assert extract_unified_diff(text) == PATCH_TEXT


def test_extract_unified_diff_reads_raw_diff():
    assert extract_unified_diff(f"Notes first.\n{PATCH_TEXT}") == PATCH_TEXT


def test_extract_unified_diff_returns_none_without_patch():
    assert extract_unified_diff("No patch here.") is None


def test_apply_unified_diff_can_check_without_changing_files(tmp_path):
    _init_repo(tmp_path)
    file_path = tmp_path / "demo.txt"
    file_path.write_text("hello\n")
    _git(tmp_path, "add", "demo.txt")
    _git(tmp_path, "commit", "-m", "docs: add demo")

    result = apply_unified_diff(PATCH_TEXT, tmp_path, check_only=True)

    assert result.applied is False
    assert file_path.read_text() == "hello\n"


def test_apply_unified_diff_changes_files_after_git_check(tmp_path):
    _init_repo(tmp_path)
    file_path = tmp_path / "demo.txt"
    file_path.write_text("hello\n")
    _git(tmp_path, "add", "demo.txt")
    _git(tmp_path, "commit", "-m", "docs: add demo")

    result = apply_unified_diff(PATCH_TEXT, tmp_path)

    assert result.applied is True
    assert file_path.read_text() == "hello world\n"


def test_apply_unified_diff_rejects_non_patch_text(tmp_path):
    with pytest.raises(PatchError, match="usable unified diff"):
        apply_unified_diff("just words", tmp_path)


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
