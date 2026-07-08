import json

import pytest

from openpandora.findings import Finding, Severity
from openpandora.git_context import RepoContext
from openpandora.history import record_findings
from openpandora.learned_rules import (
    LearnedRulesError,
    add_learned_rule,
    learn_from_history,
    load_learned_rules,
)


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


def test_add_learned_rule_saves_user_constraint(tmp_path):
    result = add_learned_rule(
        tmp_path,
        title="Keep README minimal",
        message="Keep README changes short and focused.",
        severity=Severity.INFO,
    )

    assert result is not None
    assert result.path == tmp_path / ".openpandora" / "rules.json"

    rules = load_learned_rules(tmp_path)
    assert len(rules) == 1
    assert rules[0].title == "Keep README minimal"
    assert rules[0].message == "Keep README changes short and focused."
    assert rules[0].severity is Severity.INFO


def test_add_learned_rule_skips_duplicate_constraint(tmp_path):
    kwargs = {
        "title": "Keep README minimal",
        "message": "Keep README changes short and focused.",
        "severity": Severity.INFO,
    }

    assert add_learned_rule(tmp_path, **kwargs) is not None
    assert add_learned_rule(tmp_path, **kwargs) is None
    assert len(load_learned_rules(tmp_path)) == 1


def test_learn_from_history_promotes_repeated_findings(tmp_path):
    context = RepoContext(
        branch_name="feature/demo",
        current_commit="abc123",
        changed_files=("src/demo.py",),
    )
    finding = Finding(
        title="Add a focused test",
        message="Source changed without a matching test.",
        severity=Severity.WARNING,
        file_path="src/demo.py",
    )

    record_findings(context, (finding,), tmp_path)
    assert learn_from_history(tmp_path) is None

    record_findings(context, (finding,), tmp_path)
    result = learn_from_history(tmp_path)

    assert result is not None
    assert result.added_rules[0].title == "Learned: add focused tests"
    assert "focused matching test" in result.added_rules[0].message


def test_learn_from_history_does_not_duplicate_promoted_rules(tmp_path):
    context = RepoContext(
        branch_name="feature/demo",
        current_commit="abc123",
        changed_files=("src/demo.py",),
    )
    finding = Finding(
        title="Add a focused test",
        message="Source changed without a matching test.",
        severity=Severity.WARNING,
        file_path="src/demo.py",
    )
    record_findings(context, (finding,), tmp_path)
    record_findings(context, (finding,), tmp_path)

    assert learn_from_history(tmp_path) is not None
    assert learn_from_history(tmp_path) is None
    assert len(load_learned_rules(tmp_path)) == 1
