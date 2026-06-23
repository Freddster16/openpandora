"""Command line interface for OpenPandora."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from openpandora import __version__
from openpandora.checks import run_local_checks
from openpandora.git_context import GitCommandError, collect_repo_context
from openpandora.learned_rules import LearnedRulesError, load_learned_rules


def run_check(repo_path: str | Path = ".") -> int:
    """Run local QA feedback before a user pushes code."""
    try:
        context = collect_repo_context(repo_path)
        learned_rules = load_learned_rules(repo_path)
    except (GitCommandError, LearnedRulesError) as error:
        _print_check_error(error)
        return 1

    findings = run_local_checks(context)

    print("OpenPandora check")
    print(f"Branch: {context.branch_name}")
    print(f"Commit: {context.current_commit[:12]}")
    print(f"Changed files: {len(context.changed_files)}")
    if learned_rules:
        print(f"Loaded learned rules: {len(learned_rules)}")

    if not findings:
        print("No issues found.")
        return 0

    print(f"Found {len(findings)} issue(s):")
    for finding in findings:
        location = f" ({finding.location})" if finding.location else ""
        print(f"- [{finding.severity}] {finding.title}{location}")
        print(f"  {finding.message}")
        if finding.suggestion:
            print(f"  Suggestion: {finding.suggestion}")

    return 1


def _print_check_error(error: Exception) -> None:
    print("OpenPandora could not check this project.")

    message = str(error)
    if "not a git repository" in message.lower():
        print("OpenPandora needs to run inside a Git project.")
        print("Try: cd path/to/your/project")
        print("Then run: openpandora check")
        return

    print(message)


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser so commands stay small and testable."""
    parser = argparse.ArgumentParser(
        prog="openpandora",
        description="Run beginner-friendly QA feedback for your code.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)
    check_parser = subparsers.add_parser(
        "check",
        help="Check the current project before you push.",
    )
    check_parser.set_defaults(command_handler=run_check)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the OpenPandora command line interface."""
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.command_handler()
