"""Extract and apply provider-proposed patches safely."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

PATCH_BLOCK_PATTERN = re.compile(
    r"```(?:diff|patch)?\s*\n(?P<patch>.*?)(?:\n```|$)",
    re.DOTALL,
)


class PatchError(RuntimeError):
    """Raised when a proposed patch cannot be used safely."""


@dataclass(frozen=True)
class PatchResult:
    """Describe a patch application attempt."""

    applied: bool
    message: str


def extract_unified_diff(text: str) -> str | None:
    """Find a unified diff in provider text."""
    for match in PATCH_BLOCK_PATTERN.finditer(text):
        patch_text = match.group("patch").strip()
        if _looks_like_unified_diff(patch_text):
            return patch_text + "\n"

    diff_start = text.find("diff --git ")
    if diff_start >= 0:
        patch_text = text[diff_start:].strip()
        if _looks_like_unified_diff(patch_text):
            return patch_text + "\n"

    if _looks_like_unified_diff(text):
        return text.strip() + "\n"

    return None


def apply_unified_diff(
    patch_text: str,
    repo_path: str | Path = ".",
    check_only: bool = False,
) -> PatchResult:
    """Apply a unified diff after Git confirms it can be applied."""
    if not _looks_like_unified_diff(patch_text):
        raise PatchError("The provider did not return a usable unified diff.")

    path = Path(repo_path)
    check_result = _run_git_apply(path, patch_text, check=True)
    if check_result.returncode != 0:
        reason = check_result.stderr.strip() or check_result.stdout.strip()
        raise PatchError(f"Git could not apply the patch: {reason}")

    if check_only:
        return PatchResult(applied=False, message="Patch can be applied.")

    apply_result = _run_git_apply(path, patch_text, check=False)
    if apply_result.returncode != 0:
        reason = apply_result.stderr.strip() or apply_result.stdout.strip()
        raise PatchError(f"Git failed while applying the patch: {reason}")

    return PatchResult(applied=True, message="Patch applied.")


def _looks_like_unified_diff(text: str) -> bool:
    return "diff --git " in text and "\n--- " in text and "\n+++ " in text


def _run_git_apply(
    repo_path: Path,
    patch_text: str,
    check: bool,
) -> subprocess.CompletedProcess[str]:
    arguments = ["git", "apply"]
    if check:
        arguments.append("--check")
    return subprocess.run(
        arguments,
        cwd=repo_path,
        input=patch_text,
        text=True,
        capture_output=True,
        check=False,
    )
