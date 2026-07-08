import pytest


@pytest.fixture(autouse=True)
def isolate_global_openpandora_config(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENPANDORA_CONFIG_HOME", str(tmp_path / "config-home"))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig"))
