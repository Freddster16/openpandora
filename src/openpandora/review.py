"""Build a readable review from checks, commands, and learned rules."""

from __future__ import annotations

from dataclasses import dataclass

from openpandora.command_runner import CommandResult
from openpandora.file_context import FileContext
from openpandora.findings import Finding
from openpandora.git_context import RepoContext
from openpandora.learned_rules import LearnedRule


@dataclass(frozen=True)
class ReviewRequest:
    """Collect the evidence OpenPandora uses for one review."""

    provider: str
    context: RepoContext
    findings: tuple[Finding, ...]
    auth_method: str | None = None
    model: str | None = None
    reasoning: str | None = None
    learned_rules: tuple[LearnedRule, ...] = ()
    command_results: tuple[CommandResult, ...] = ()
    file_context: tuple[FileContext, ...] = ()


@dataclass(frozen=True)
class ReviewResult:
    """Describe OpenPandora's review without changing files."""

    provider: str
    summary: str
    suggestions: tuple[str, ...]
    findings: tuple[Finding, ...]
    command_results: tuple[CommandResult, ...]
    provider_text: str | None = None
    provider_error: str | None = None

    @property
    def has_issues(self) -> bool:
        """Return whether the review found anything to improve."""
        return bool(
            self.findings
            or failed_command_results(self.command_results)
            or self.provider_error
        )


def build_review(
    request: ReviewRequest,
    provider_text: str | None = None,
    provider_error: str | None = None,
) -> ReviewResult:
    """Create a local review from concrete evidence."""
    failed_commands = failed_command_results(request.command_results)
    suggestions = _finding_suggestions(request.findings)
    suggestions.extend(_command_suggestions(failed_commands))

    if suggestions:
        summary = "OpenPandora found work to review before this branch is ready."
    else:
        summary = "OpenPandora did not find anything to improve right now."

    return ReviewResult(
        provider=request.provider,
        summary=summary,
        suggestions=tuple(suggestions),
        findings=request.findings,
        command_results=request.command_results,
        provider_text=provider_text,
        provider_error=provider_error,
    )


def build_review_report(request: ReviewRequest, result: ReviewResult) -> str:
    """Format a review so it can be printed or pasted into a PR."""
    lines = [
        "OpenPandora review",
        f"Provider: {result.provider}",
        f"Branch: {request.context.branch_name}",
        f"Commit: {request.context.current_commit[:12]}",
    ]
    if request.model:
        lines.append(f"Model: {request.model}")
    if request.reasoning:
        lines.append(f"Reasoning: {request.reasoning}")
    if request.auth_method:
        lines.append(f"Auth: {request.auth_method}")
    if request.context.base_ref:
        lines.append(f"Compared with: {request.context.base_ref}")

    lines.extend(["", "Summary:", result.summary])

    if result.provider_text:
        lines.extend(["", "Provider review:", result.provider_text])
    elif result.provider_error:
        lines.extend(["", "Provider setup:", result.provider_error])

    if request.learned_rules:
        lines.extend(["", "Learned rules loaded:"])
        for rule in request.learned_rules:
            lines.append(f"- [{rule.severity}] {rule.title}")

    lines.extend(["", "Command results:"])
    if request.command_results:
        for command_result in request.command_results:
            status = "passed" if command_result.passed else "failed"
            lines.append(
                f"- {command_result.name}: {status} ({command_result.command})"
            )
    else:
        lines.append("- Not run.")

    lines.extend(["", "Suggestions:"])
    if result.suggestions:
        lines.extend(f"- {suggestion}" for suggestion in result.suggestions)
    else:
        lines.append("- No changes suggested.")

    return "\n".join(lines) + "\n"


def failed_command_results(
    command_results: tuple[CommandResult, ...],
) -> tuple[CommandResult, ...]:
    """Return the commands that failed during review."""
    return tuple(result for result in command_results if not result.passed)


def _finding_suggestions(findings: tuple[Finding, ...]) -> list[str]:
    suggestions: list[str] = []
    for finding in findings:
        if finding.suggestion:
            suggestions.append(finding.suggestion)
        else:
            suggestions.append(finding.message)
    return suggestions


def _command_suggestions(failed_commands: tuple[CommandResult, ...]) -> list[str]:
    return [
        f"Fix the failing {result.name.lower()} command: {result.command}"
        for result in failed_commands
    ]
