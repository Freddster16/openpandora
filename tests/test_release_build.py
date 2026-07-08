import subprocess
import sys


def test_build_release_creates_executable_zipapp(tmp_path):
    output_path = tmp_path / "openpandora.pyz"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_release.py",
            "--output",
            str(output_path),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert output_path.exists()

    version_result = subprocess.run(
        [sys.executable, str(output_path), "--version"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert version_result.returncode == 0, version_result.stderr
    assert "openpandora" in version_result.stdout

    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    _git(repo_path, "init")
    _git(repo_path, "config", "user.name", "OpenPandora Tests")
    _git(repo_path, "config", "user.email", "tests@example.com")
    source_dir = repo_path / "src"
    source_dir.mkdir()
    (source_dir / "demo.py").write_text("print('hello')\n")
    _git(repo_path, "add", ".")
    _git(repo_path, "commit", "-m", "add demo")
    (source_dir / "demo.py").write_text("print('hello world')\n")
    _git(repo_path, "add", ".")
    _git(repo_path, "commit", "-m", "change demo without test")

    check_result = subprocess.run(
        [sys.executable, str(output_path), "check", "--since", "HEAD~1"],
        cwd=repo_path,
        text=True,
        capture_output=True,
        check=False,
    )

    assert check_result.returncode == 1
    assert "Add a focused test" in check_result.stdout


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
