"""Load and update user-editable rules OpenPandora learns locally."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from openpandora.findings import Severity
from openpandora.history import load_history

RULES_FILE = Path(".openpandora") / "rules.json"
LEARNED_THRESHOLD = 2


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


@dataclass(frozen=True)
class LearnedRulesWrite:
    """Describe learned rules written to disk."""

    path: Path
    added_rules: tuple[LearnedRule, ...]


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


def add_learned_rule(
    repo_path: str | Path = ".",
    *,
    message: str,
    title: str | None = None,
    severity: Severity = Severity.INFO,
    source: str = "user",
) -> LearnedRulesWrite | None:
    """Remember one local user preference without duplicating known rules."""
    rule = LearnedRule(
        title=(title or _title_from_message(message)).strip(),
        message=message.strip(),
        severity=severity,
    )
    return _append_rules(repo_path, (rule,), source=source)


def learn_from_history(
    repo_path: str | Path = ".",
    *,
    threshold: int = LEARNED_THRESHOLD,
) -> LearnedRulesWrite | None:
    """Promote repeated finding patterns into local learned rules."""
    events = load_history(repo_path)
    pattern_counts: dict[str, int] = {}
    pattern_examples: dict[str, dict[str, Any]] = {}

    for event in events:
        if event.get("type") != "findings":
            continue
        findings = event.get("findings", [])
        if not isinstance(findings, list):
            continue
        for raw_finding in findings:
            if not isinstance(raw_finding, dict):
                continue
            key = _finding_key(raw_finding)
            pattern_counts[key] = pattern_counts.get(key, 0) + 1
            pattern_examples.setdefault(key, raw_finding)

    learned_rules = tuple(
        _rule_from_finding(pattern_examples[key])
        for key, count in pattern_counts.items()
        if count >= threshold
    )
    if not learned_rules:
        return None

    return _append_rules(repo_path, learned_rules, source="history")


def _parse_rule(raw_rule: object) -> LearnedRule:
    if not isinstance(raw_rule, dict):
        raise TypeError("each rule must be an object")

    return LearnedRule(
        title=str(raw_rule.get("title", "")),
        message=str(raw_rule.get("message", "")),
        severity=Severity(str(raw_rule.get("severity", Severity.WARNING))),
    )


def _append_rules(
    repo_path: str | Path,
    rules: tuple[LearnedRule, ...],
    *,
    source: str,
) -> LearnedRulesWrite | None:
    rules_path = Path(repo_path) / RULES_FILE
    payload = _load_rules_payload(rules_path)
    raw_rules = payload.setdefault("rules", [])
    if not isinstance(raw_rules, list):
        raise LearnedRulesError(
            f"Could not load learned rules from {rules_path}: rules must be a list"
        )

    existing_rules = tuple(_parse_rule(raw_rule) for raw_rule in raw_rules)
    existing_keys = {_rule_key(rule) for rule in existing_rules}
    added_rules: list[LearnedRule] = []

    for rule in rules:
        key = _rule_key(rule)
        if key in existing_keys:
            continue
        raw_rules.append(
            {
                "title": rule.title,
                "message": rule.message,
                "severity": rule.severity.value,
                "source": source,
                "learned_at": datetime.now(UTC).isoformat(),
            }
        )
        existing_keys.add(key)
        added_rules.append(rule)

    if not added_rules:
        return None

    rules_path.parent.mkdir(parents=True, exist_ok=True)
    rules_path.write_text(json.dumps(payload, indent=2) + "\n")
    return LearnedRulesWrite(path=rules_path, added_rules=tuple(added_rules))


def _load_rules_payload(rules_path: Path) -> dict[str, Any]:
    if not rules_path.exists():
        return {"rules": []}

    try:
        data = json.loads(rules_path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise LearnedRulesError(
            f"Could not load learned rules from {rules_path}: {error}"
        ) from error
    if not isinstance(data, dict):
        raise LearnedRulesError(
            f"Could not load learned rules from {rules_path}: "
            "rules file must be a JSON object"
        )
    if "rules" in data and not isinstance(data["rules"], list):
        raise LearnedRulesError(
            f"Could not load learned rules from {rules_path}: rules must be a list"
        )
    return data


def _rule_from_finding(raw_finding: dict[str, Any]) -> LearnedRule:
    title = str(raw_finding.get("title", "Repeated finding"))
    severity = Severity(str(raw_finding.get("severity", Severity.WARNING)))

    if title == "Add a focused test":
        return LearnedRule(
            title="Learned: add focused tests",
            message=(
                "When source code changes, include or update a focused matching "
                "test in the same change."
            ),
            severity=severity,
        )
    if title == "Possible secret in code":
        return LearnedRule(
            title="Learned: keep secrets out of code",
            message=(
                "Keep API keys, tokens, passwords, and secrets out of code; load "
                "them from environment variables."
            ),
            severity=severity,
        )

    message = str(raw_finding.get("suggestion") or raw_finding.get("message") or title)
    return LearnedRule(
        title=f"Learned: {title}",
        message=message,
        severity=severity,
    )


def _finding_key(raw_finding: dict[str, Any]) -> str:
    return _normalize_text(str(raw_finding.get("title", "")))


def _rule_key(rule: LearnedRule) -> str:
    return f"{_normalize_text(rule.title)}::{_normalize_text(rule.message)}"


def _title_from_message(message: str) -> str:
    words = message.strip().split()
    title = " ".join(words[:8])
    if len(words) > 8:
        title = f"{title}..."
    return title or "User preference"


def _normalize_text(text: str) -> str:
    return " ".join(text.lower().split())
