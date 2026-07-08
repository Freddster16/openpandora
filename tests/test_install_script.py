import subprocess


def test_install_script_is_valid_shell():
    result = subprocess.run(
        ["sh", "-n", "install.sh"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_install_script_downloads_latest_release_asset():
    script = open("install.sh").read()

    assert "releases/latest/download/openpandora.pyz" in script
    assert "OPENPANDORA_INSTALL_DIR" in script
    assert "OPENPANDORA_PYTHON" in script
    assert "python3.11" in script
    assert "curl" in script
    assert "wget" in script
    assert "OPENPANDORA_SKIP_SETUP" in script
    assert '"$target" setup --global' in script
    assert 'exec "$python_cmd" "$app_file" "\\$@"' in script
