"""Prepare safe improvement plans before any file edits happen."""

from __future__ import annotations

from openpandora.review import ReviewResult


def build_improve_plan(review_result: ReviewResult) -> str:
    """Explain what OpenPandora would improve without changing files."""
    lines = [
        "OpenPandora improve dry run",
        "",
        "No files were changed.",
        "",
        f"Provider: {review_result.provider}",
        f"Summary: {review_result.summary}",
        "",
        "Proposed next steps:",
    ]

    if review_result.suggestions:
        lines.extend(f"- {suggestion}" for suggestion in review_result.suggestions)
    else:
        lines.append("- No improvement patch is needed right now.")

    lines.extend(
        [
            "",
            (
                "Use --apply to apply a provider patch, or fix-pr to prepare a "
                "fix pull request."
            ),
        ]
    )
    return "\n".join(lines) + "\n"
