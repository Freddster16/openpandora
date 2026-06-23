"""Load user-editable rules that OpenPandora can learn from later."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from openpandora.findings import Severity

RULES_FILE = Path(".openpandora") / "rules.json"


class LearnedRulesError(RuntimeError):
    """Raised when a learned rules file is present but not usable."""


@dataclass(frozen=True)
class LearnedRule:
    """Describe one user-controlled rule OpenPandora may use for QA."""

    title: str
    message: str
    severity: Severity = Severity.WARNING

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("Learned rule title is required.")
        if not self.message.strip():
            raise ValueError("Learned rule message is required.")


def load_learned_rules(repo_path: str | Path = ".") -> tuple[LearnedRule, ...]:
    """Load readable learned rules without changing user code."""
    rules_path = Path(repo_path) / RULES_FILE
    if not rules_path.exists():
        return ()

    try:
        data = json.loads(rules_path.read_text())
        if not isinstance(data, dict):
            raise TypeError("rules file must be a JSON object")
        raw_rules = data.get("rules", [])
        if not isinstance(raw_rules, list):
            raise TypeError("rules must be a list")
        return tuple(_parse_rule(raw_rule) for raw_rule in raw_rules)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise LearnedRulesError(
            f"Could not load learned rules from {rules_path}: {error}"
        ) from error


def _parse_rule(raw_rule: object) -> LearnedRule:
    if not isinstance(raw_rule, dict):
        raise TypeError("each rule must be an object")

    return LearnedRule(
        title=str(raw_rule.get("title", "")),
        message=str(raw_rule.get("message", "")),
        severity=Severity(str(raw_rule.get("severity", Severity.WARNING))),
    )
