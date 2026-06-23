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
