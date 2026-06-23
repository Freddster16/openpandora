"""Command line interface for OpenPandora."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from openpandora import __version__
from openpandora.checks import run_local_checks
from openpandora.findings import Finding
from openpandora.git_context import GitCommandError, collect_repo_context
from openpandora.learned_rules import LearnedRule, LearnedRulesError, load_learned_rules
from openpandora.providers import list_provider_setups


def run_check(repo_path: str | Path = ".", json_output: bool = False) -> int:
    """Run local QA feedback before a user pushes code."""
    try:
        context = collect_repo_context(repo_path)
        learned_rules = load_learned_rules(repo_path)
    except (GitCommandError, LearnedRulesError) as error:
        if json_output:
            print(json.dumps(_error_payload(error), indent=2))
            return 1
        _print_check_error(error)
        return 1

    findings = run_local_checks(context, repo_path)
    if json_output:
        print(json.dumps(_success_payload(context, learned_rules, findings), indent=2))
        return 1 if findings else 0

    print("OpenPandora check")
    print(f"Branch: {context.branch_name}")
    print(f"Commit: {context.current_commit[:12]}")
    print(f"Changed files: {len(context.changed_files)}")
    if learned_rules:
        print(f"Loaded learned rules: {len(learned_rules)}")
        print("Learned rules are visible but not auto-applied yet.")
        for rule in learned_rules:
            print(f"- [{rule.severity}] {rule.title}")

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


def _success_payload(context, learned_rules, findings) -> dict:
    status = "failed" if findings else "passed"
    return {
        "status": status,
        "branch": context.branch_name,
        "commit": context.current_commit,
        "changed_files": list(context.changed_files),
        "learned_rules": [_rule_payload(rule) for rule in learned_rules],
        "findings": [_finding_payload(finding) for finding in findings],
    }


def _error_payload(error: Exception) -> dict:
    message = str(error)
    if "not a git repository" in message.lower():
        return {
            "status": "error",
            "message": "OpenPandora needs to run inside a Git project.",
            "next_step": "cd path/to/your/project && openpandora check",
        }

    return {"status": "error", "message": message}


def _finding_payload(finding: Finding) -> dict:
    return {
        "title": finding.title,
        "message": finding.message,
        "severity": finding.severity.value,
        "file_path": finding.file_path,
        "line_number": finding.line_number,
        "location": finding.location,
        "suggestion": finding.suggestion,
    }


def _rule_payload(rule: LearnedRule) -> dict:
    return {
        "title": rule.title,
        "message": rule.message,
        "severity": rule.severity.value,
    }


def run_providers() -> int:
    """Show provider auth options without exposing secret values."""
    print("OpenPandora provider setup")
    for setup in list_provider_setups():
        status = "ready" if setup.configured else "needs setup"
        print(f"- {setup.display_name} ({setup.provider}): {status}")
        if setup.env_var:
            print(f"  API key env var: {setup.env_var}")
        methods = ", ".join(method.value for method in setup.auth_methods)
        print(f"  Auth methods: {methods}")
        print(f"  {setup.note}")
    return 0


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
    check_parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable check results.",
    )
    check_parser.set_defaults(command_handler=run_check)

    providers_parser = subparsers.add_parser(
        "providers",
        help="Show available AI provider auth options.",
    )
    providers_parser.set_defaults(command_handler=run_providers)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the OpenPandora command line interface."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "check":
        return args.command_handler(json_output=args.json)
    return args.command_handler()
