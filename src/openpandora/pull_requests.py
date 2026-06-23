"""Prepare readable pull request text from QA findings."""

from __future__ import annotations

from openpandora.findings import Finding
from openpandora.git_context import RepoContext
from openpandora.learned_rules import LearnedRule


def build_pr_body(
    context: RepoContext,
    findings: tuple[Finding, ...],
    learned_rules: tuple[LearnedRule, ...] = (),
) -> str:
    """Build a PR/comment body without creating anything on GitHub."""
    lines = [
        "# OpenPandora QA",
        "",
        f"Branch: `{context.branch_name}`",
        f"Commit: `{context.current_commit[:12]}`",
    ]
    if context.base_ref:
        lines.append(f"Compared with: `{context.base_ref}`")

    lines.extend(["", "## Summary", ""])
    if findings:
        lines.append(f"OpenPandora found {len(findings)} issue(s) to review.")
    else:
        lines.append("OpenPandora did not find any issues in this check.")

    if learned_rules:
        lines.extend(["", "## Learned Rules", ""])
        for rule in learned_rules:
            lines.append(f"- `[{rule.severity}]` {rule.title}")

    lines.extend(["", "## Findings", ""])
    if not findings:
        lines.append("- No findings.")
    else:
        for finding in findings:
            location = f" at `{finding.location}`" if finding.location else ""
            lines.append(f"- `[{finding.severity}]` {finding.title}{location}")
            lines.append(f"  - {finding.message}")
            if finding.suggestion:
                lines.append(f"  - Suggestion: {finding.suggestion}")

    lines.extend(
        [
            "",
            "OpenPandora has not changed any files or opened a fix PR yet.",
        ]
    )
    return "\n".join(lines) + "\n"
