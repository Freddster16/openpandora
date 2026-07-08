import runpy

import pytest

from openpandora import cli


def test_zipapp_entrypoint_exits_with_cli_status(monkeypatch):
    calls = []

    def fake_main():
        calls.append(True)
        return 7

    monkeypatch.setattr(cli, "main", fake_main)
    with pytest.raises(SystemExit) as error:
        runpy.run_path("src/__main__.py")
    assert error.value.code == 7
    assert calls == [True]
