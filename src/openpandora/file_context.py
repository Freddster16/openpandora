"""Collect small, redacted file snippets for provider review."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

MAX_CONTEXT_FILES = 8
MAX_FILE_CHARACTERS = 6000
SECRET_WORDS = ("api_key", "apikey", "secret", "token", "password")
SECRET_VALUE_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
)


@dataclass(frozen=True)
class FileContext:
    """Describe one changed file's safe provider context."""

    file_path: str
    content: str
    truncated: bool = False


def collect_file_context(
    changed_files: tuple[str, ...],
    repo_path: str | Path = ".",
) -> tuple[FileContext, ...]:
    """Collect small text snapshots for changed files."""
    contexts: list[FileContext] = []
    root_path = Path(repo_path)
    for file_path in changed_files:
        if len(contexts) >= MAX_CONTEXT_FILES:
            break
        context = _read_file_context(root_path, file_path)
        if context is not None:
            contexts.append(context)
    return tuple(contexts)


def _read_file_context(root_path: Path, file_path: str) -> FileContext | None:
    path = root_path / file_path
    if not path.is_file():
        return None

    try:
        content = path.read_text()
    except UnicodeDecodeError:
        return None

    redacted = redact_sensitive_text(content)
    truncated = len(redacted) > MAX_FILE_CHARACTERS
    if truncated:
        redacted = redacted[:MAX_FILE_CHARACTERS].rstrip()
    return FileContext(file_path=file_path, content=redacted, truncated=truncated)


def redact_sensitive_text(content: str) -> str:
    """Remove lines that look like they contain credentials or tokens."""
    lines: list[str] = []
    for line in content.splitlines():
        lowered = line.lower()
        if any(word in lowered for word in SECRET_WORDS) or any(
            pattern.search(line) for pattern in SECRET_VALUE_PATTERNS
        ):
            lines.append("[redacted sensitive-looking line]")
        else:
            lines.append(line)
    return "\n".join(lines)
