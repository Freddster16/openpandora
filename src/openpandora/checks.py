"""Run deterministic local QA checks."""

from __future__ import annotations

import re
from pathlib import Path

from openpandora.findings import Finding, Severity
from openpandora.git_context import RepoContext

SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bghp_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(
        r"(?i)\b(api[_-]?key|secret|token|password)\b\s*[:=]\s*['\"][^'\"]{8,}['\"]"
    ),
)


def run_local_checks(
    context: RepoContext, repo_path: str | Path = "."
) -> tuple[Finding, ...]:
    """Return local QA findings for the current repo context."""
    findings: list[Finding] = []
    findings.extend(_check_missing_tests(context))
    findings.extend(_check_secret_like_strings(context, Path(repo_path)))
    return tuple(findings)


def _check_missing_tests(context: RepoContext) -> tuple[Finding, ...]:
    source_changes = tuple(
        file_path for file_path in context.changed_files if file_path.startswith("src/")
    )
    test_changes = tuple(
        file_path
        for file_path in context.changed_files
        if file_path.startswith("tests/")
    )

    if not source_changes or test_changes:
        return ()

    changed_files = ", ".join(source_changes)
    return (
        Finding(
            title="Add a focused test",
            message=(
                "Source code changed, but this commit does not include a matching "
                "test change."
            ),
            severity=Severity.WARNING,
            suggestion=f"Add or update a pytest test for: {changed_files}",
        ),
    )


def _check_secret_like_strings(
    context: RepoContext, repo_path: Path
) -> tuple[Finding, ...]:
    findings: list[Finding] = []
    for changed_file in context.changed_files:
        file_path = repo_path / changed_file
        text = _read_text_file(file_path)
        if text is None:
            continue

        for line_number, line in enumerate(text.splitlines(), start=1):
            if _looks_like_secret(line):
                findings.append(
                    Finding(
                        title="Possible secret in code",
                        message=(
                            "This line looks like it may contain an API key, token, "
                            "password, or secret."
                        ),
                        severity=Severity.ERROR,
                        file_path=changed_file,
                        line_number=line_number,
                        suggestion=(
                            "Remove the secret from the code and load it from an "
                            "environment variable instead."
                        ),
                    )
                )
                break

    return tuple(findings)


def _read_text_file(file_path: Path) -> str | None:
    try:
        return file_path.read_text()
    except (OSError, UnicodeDecodeError):
        return None


def _looks_like_secret(line: str) -> bool:
    return any(pattern.search(line) for pattern in SECRET_PATTERNS)
