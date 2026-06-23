"""Collect small, redacted file snippets for provider review."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

MAX_CONTEXT_FILES = 8
MAX_FILE_CHARACTERS = 6000
SECRET_WORDS = ("api_key", "apikey", "secret", "token", "password")


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

    redacted = _redact_sensitive_lines(content)
    truncated = len(redacted) > MAX_FILE_CHARACTERS
    if truncated:
        redacted = redacted[:MAX_FILE_CHARACTERS].rstrip()
    return FileContext(file_path=file_path, content=redacted, truncated=truncated)


def _redact_sensitive_lines(content: str) -> str:
    lines: list[str] = []
    for line in content.splitlines():
        lowered = line.lower()
        if any(word in lowered for word in SECRET_WORDS):
            lines.append("[redacted sensitive-looking line]")
        else:
            lines.append(line)
    return "\n".join(lines)
