"""Run deterministic local QA checks."""

from __future__ import annotations

from openpandora.findings import Finding
from openpandora.git_context import RepoContext


def run_local_checks(context: RepoContext) -> tuple[Finding, ...]:
    """Return local QA findings for the current repo context."""
    _ = context
    return ()
