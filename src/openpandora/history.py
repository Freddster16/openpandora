"""Record OpenPandora findings and fixes in a readable history file."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from openpandora.findings import Finding
from openpandora.git_context import RepoContext

HISTORY_FILE = Path(".openpandora") / "history.jsonl"


@dataclass(frozen=True)
class HistoryWrite:
    """Describe one history write so the CLI can surface it."""

    path: Path
    event_count: int


def record_findings(
    context: RepoContext,
    findings: tuple[Finding, ...],
    repo_path: str | Path = ".",
) -> HistoryWrite | None:
    """Record findings without turning them into rules automatically."""
    if not findings:
        return None

    return append_history_event(
        "findings",
        context,
        repo_path,
        {
            "findings": [_finding_payload(finding) for finding in findings],
        },
    )


def record_fix(
    context: RepoContext,
    repo_path: str | Path = ".",
    *,
    fix_branch: str,
    commit_hash: str,
    pull_request_url: str | None = None,
) -> HistoryWrite:
    """Record a fix OpenPandora prepared for user review."""
    return append_history_event(
        "fix",
        context,
        repo_path,
        {
            "fix_branch": fix_branch,
            "commit": commit_hash,
            "pull_request_url": pull_request_url,
        },
    )


def append_history_event(
    event_type: str,
    context: RepoContext,
    repo_path: str | Path,
    payload: dict[str, Any],
) -> HistoryWrite:
    """Append one JSON Lines history event."""
    history_path = Path(repo_path) / HISTORY_FILE
    history_path.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "type": event_type,
        "created_at": datetime.now(UTC).isoformat(),
        "branch": context.branch_name,
        "commit": context.current_commit,
        "base_ref": context.base_ref,
        **payload,
    }
    with history_path.open("a") as history_file:
        history_file.write(json.dumps(event, sort_keys=True) + "\n")
    return HistoryWrite(path=history_path, event_count=1)


def load_history(repo_path: str | Path = ".") -> tuple[dict[str, Any], ...]:
    """Load readable history events for display."""
    history_path = Path(repo_path) / HISTORY_FILE
    if not history_path.exists():
        return ()
    return tuple(
        json.loads(line) for line in history_path.read_text().splitlines() if line
    )


def _finding_payload(finding: Finding) -> dict[str, Any]:
    return {
        "title": finding.title,
        "message": finding.message,
        "severity": finding.severity.value,
        "file_path": finding.file_path,
        "line_number": finding.line_number,
        "suggestion": finding.suggestion,
    }
