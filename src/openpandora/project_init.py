"""Create beginner-friendly project files for OpenPandora."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from openpandora.learned_rules import RULES_FILE

DEFAULT_RULES = {
    "rules": [
        {
            "title": "Prefer focused tests",
            "message": "Add a small pytest test with each behavior change.",
            "severity": "warning",
        },
        {
            "title": "Explain risky changes",
            "message": "Tell the user why a risky change is safe.",
            "severity": "info",
        },
    ]
}


@dataclass(frozen=True)
class InitResult:
    """Describe whether OpenPandora created starter project files."""

    rules_path: Path
    created: bool


def initialize_project(repo_path: str | Path = ".") -> InitResult:
    """Create an editable learned-rules template when one is missing."""
    path = Path(repo_path) / RULES_FILE
    if path.exists():
        return InitResult(rules_path=path, created=False)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(DEFAULT_RULES, indent=2) + "\n")
    return InitResult(rules_path=path, created=True)
