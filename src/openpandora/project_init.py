"""Create beginner-friendly project files for OpenPandora."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from openpandora.learned_rules import RULES_FILE
from openpandora.project_config import CONFIG_FILE, default_config_payload

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
    config_path: Path
    rules_created: bool
    config_created: bool

    @property
    def created(self) -> bool:
        """Return whether the learned-rules file was created."""
        return self.rules_created


def initialize_project(repo_path: str | Path = ".") -> InitResult:
    """Create editable starter files when they are missing."""
    root_path = Path(repo_path)
    rules_path = root_path / RULES_FILE
    config_path = root_path / CONFIG_FILE

    rules_created = _write_json_if_missing(rules_path, DEFAULT_RULES)
    config_created = _write_json_if_missing(config_path, default_config_payload())

    return InitResult(
        rules_path=rules_path,
        config_path=config_path,
        rules_created=rules_created,
        config_created=config_created,
    )


def _write_json_if_missing(path: Path, payload: object) -> bool:
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")
    return True
