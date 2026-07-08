"""Represent QA findings in a clear, beginner-friendly shape."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Severity(StrEnum):
    """Rank how much attention a QA finding needs."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class Finding:
    """Describe one QA result so OpenPandora can explain it clearly."""

    title: str
    message: str
    severity: Severity = Severity.WARNING
    file_path: str | None = None
    line_number: int | None = None
    suggestion: str | None = None

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("Finding title is required.")
        if not self.message.strip():
            raise ValueError("Finding message is required.")
        if self.line_number is not None and self.line_number < 1:
            raise ValueError("Finding line number must be 1 or greater.")

    @property
    def location(self) -> str | None:
        """Return a compact file location for user-facing output."""
        if self.file_path is None:
            return None
        if self.line_number is None:
            return self.file_path
        return f"{self.file_path}:{self.line_number}"


def finding_label(finding: Finding) -> str:
    """Return a short label that includes location when available."""
    if finding.location is None:
        return finding.title
    return f"{finding.title} ({finding.location})"
