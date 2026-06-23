import json

import pytest

from openpandora.findings import Severity
from openpandora.learned_rules import LearnedRulesError, load_learned_rules


def test_load_learned_rules_returns_empty_tuple_when_file_is_missing(tmp_path):
    assert load_learned_rules(tmp_path) == ()


def test_load_learned_rules_reads_user_editable_json(tmp_path):
    rules_dir = tmp_path / ".openpandora"
    rules_dir.mkdir()
    (rules_dir / "rules.json").write_text(
        json.dumps(
            {
                "rules": [
                    {
                        "title": "Prefer focused tests",
                        "message": "Add a small test with each behavior change.",
                        "severity": "info",
                    }
                ]
            }
        )
    )

    rules = load_learned_rules(tmp_path)

    assert len(rules) == 1
    assert rules[0].title == "Prefer focused tests"
    assert rules[0].message == "Add a small test with each behavior change."
    assert rules[0].severity is Severity.INFO


def test_load_learned_rules_uses_warning_as_default_severity(tmp_path):
    rules_dir = tmp_path / ".openpandora"
    rules_dir.mkdir()
    (rules_dir / "rules.json").write_text(
        json.dumps(
            {
                "rules": [
                    {
                        "title": "Explain risky changes",
                        "message": "Tell the user why the change is safe.",
                    }
                ]
            }
        )
    )

    rules = load_learned_rules(tmp_path)

    assert rules[0].severity is Severity.WARNING


def test_load_learned_rules_rejects_invalid_json(tmp_path):
    rules_dir = tmp_path / ".openpandora"
    rules_dir.mkdir()
    (rules_dir / "rules.json").write_text("{nope")

    with pytest.raises(LearnedRulesError, match="Could not load learned rules"):
        load_learned_rules(tmp_path)


def test_load_learned_rules_rejects_non_object_json(tmp_path):
    rules_dir = tmp_path / ".openpandora"
    rules_dir.mkdir()
    (rules_dir / "rules.json").write_text(json.dumps([]))

    with pytest.raises(LearnedRulesError, match="rules file must be a JSON object"):
        load_learned_rules(tmp_path)


def test_load_learned_rules_rejects_blank_rule_title(tmp_path):
    rules_dir = tmp_path / ".openpandora"
    rules_dir.mkdir()
    (rules_dir / "rules.json").write_text(
        json.dumps({"rules": [{"title": "", "message": "Use clear language."}]})
    )

    with pytest.raises(LearnedRulesError, match="title is required"):
        load_learned_rules(tmp_path)
