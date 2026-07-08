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
SOURCE_EXTENSIONS = {
    ".c",
    ".cpp",
    ".cs",
    ".go",
    ".java",
    ".js",
    ".jsx",
    ".kt",
    ".m",
    ".mm",
    ".php",
    ".py",
    ".rb",
    ".rs",
    ".swift",
    ".ts",
    ".tsx",
}
TEST_PATH_MARKERS = {"test", "tests", "__tests__"}


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
        file_path for file_path in context.changed_files if _is_source_file(file_path)
    )
    findings = []
    changed_files = set(context.changed_files)

    for source_file in source_changes:
        expected_tests = _expected_test_files(source_file)
        if changed_files.intersection(expected_tests):
            continue

        findings.append(
            Finding(
                title="Add a focused test",
                message=(
                    f"{source_file} changed, but this commit does not include a "
                    "likely matching test change."
                ),
                severity=Severity.WARNING,
                file_path=source_file,
                suggestion=(
                    "Add or update one of these focused test files: "
                    f"{', '.join(expected_tests)}"
                ),
            )
        )

    return tuple(findings)


def _expected_test_files(source_file: str) -> tuple[str, ...]:
    source_path = Path(source_file)
    relative_path = _relative_source_path(source_path)
    module_parts = relative_path.with_suffix("").parts
    module_name = "_".join(part for part in module_parts if part != "__init__")
    if not module_name:
        module_name = source_path.parent.name

    leaf_name = relative_path.stem
    if leaf_name == "__init__":
        leaf_name = source_path.parent.name

    if source_path.suffix == ".swift":
        candidates = (
            f"{source_path.parts[0]}Tests/{leaf_name}Tests.swift",
            f"Tests/{leaf_name}Tests.swift",
            f"tests/test_{leaf_name}.py",
        )
    else:
        candidates = (
            f"tests/test_{leaf_name}.py",
            str(Path("tests") / relative_path.parent / f"test_{leaf_name}.py"),
            f"tests/test_{module_name}.py",
        )
    return tuple(dict.fromkeys(candidates))


def _is_source_file(file_path: str) -> bool:
    path = Path(file_path)
    if path.suffix not in SOURCE_EXTENSIONS:
        return False
    if path.suffix != ".swift" and (not path.parts or path.parts[0] != "src"):
        return False
    lowered_parts = {part.lower() for part in path.parts}
    if lowered_parts.intersection(TEST_PATH_MARKERS):
        return False
    if any(part.lower().endswith("tests") for part in path.parts):
        return False
    if path.name.lower().startswith("test_") or path.stem.lower().endswith("test"):
        return False
    return True


def _relative_source_path(source_path: Path) -> Path:
    if source_path.parts and source_path.parts[0] in {"src", "lib", "app"}:
        return Path(*source_path.parts[1:])
    return source_path


def _check_secret_like_strings(
    context: RepoContext, repo_path: Path
) -> tuple[Finding, ...]:
    _ = repo_path
    findings: list[Finding] = []
    files_with_findings: set[str] = set()

    for changed_line in context.changed_lines:
        if changed_line.file_path in files_with_findings:
            continue

        if _looks_like_secret(changed_line.content):
            findings.append(
                Finding(
                    title="Possible secret in code",
                    message=(
                        "This added line looks like it may contain an API key, token, "
                        "password, or secret."
                    ),
                    severity=Severity.ERROR,
                    file_path=changed_line.file_path,
                    line_number=changed_line.line_number,
                    suggestion=(
                        "Remove the secret from the code and load it from an "
                        "environment variable instead."
                    ),
                )
            )
            files_with_findings.add(changed_line.file_path)

    return tuple(findings)


def _looks_like_secret(line: str) -> bool:
    return any(pattern.search(line) for pattern in SECRET_PATTERNS)
