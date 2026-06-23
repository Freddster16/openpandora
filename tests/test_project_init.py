import json

from openpandora.project_init import initialize_project


def test_initialize_project_creates_editable_rules_template(tmp_path):
    result = initialize_project(tmp_path)

    assert result.created is True
    assert result.rules_path == tmp_path / ".openpandora" / "rules.json"
    assert result.config_path == tmp_path / ".openpandora" / "config.json"

    data = json.loads(result.rules_path.read_text())
    assert data["rules"][0]["title"] == "Prefer focused tests"
    assert data["rules"][0]["severity"] == "warning"

    config_data = json.loads(result.config_path.read_text())
    assert config_data["commands"]["test"] == "python -m pytest"
    assert config_data["commands"]["lint"] == "ruff check ."


def test_initialize_project_does_not_overwrite_existing_rules(tmp_path):
    rules_dir = tmp_path / ".openpandora"
    rules_dir.mkdir()
    rules_path = rules_dir / "rules.json"
    rules_path.write_text('{"rules": []}\n')

    result = initialize_project(tmp_path)

    assert result.created is False
    assert rules_path.read_text() == '{"rules": []}\n'


def test_initialize_project_does_not_overwrite_existing_config(tmp_path):
    config_dir = tmp_path / ".openpandora"
    config_dir.mkdir()
    config_path = config_dir / "config.json"
    config_path.write_text('{"provider": "local"}\n')

    result = initialize_project(tmp_path)

    assert result.config_created is False
    assert config_path.read_text() == '{"provider": "local"}\n'
