"""Command line interface for OpenPandora."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from openpandora import __version__
from openpandora.checks import run_local_checks
from openpandora.command_runner import CommandResult, run_project_commands
from openpandora.file_context import collect_file_context
from openpandora.findings import Finding
from openpandora.git_changes import (
    GitChangeError,
    commit_all_changes,
    create_fix_branch,
    has_worktree_changes,
    is_openpandora_fix_branch,
    plan_fix_attempt,
    push_branch,
)
from openpandora.git_context import GitCommandError, collect_repo_context
from openpandora.github_pull_requests import (
    GitHubPullRequestError,
    build_pull_request_plan,
    create_pull_request,
    detect_github_repo,
)
from openpandora.history import load_history, record_findings, record_fix
from openpandora.improve import build_improve_plan
from openpandora.learned_rules import LearnedRule, LearnedRulesError, load_learned_rules
from openpandora.patches import PatchError, apply_unified_diff, extract_unified_diff
from openpandora.project_config import ProjectConfigError, load_project_config
from openpandora.project_init import initialize_project
from openpandora.provider_clients import (
    ProviderReviewError,
    request_provider_fix,
    request_provider_review,
)
from openpandora.providers import list_provider_setups, select_provider
from openpandora.pull_requests import build_pr_body
from openpandora.review import ReviewRequest, build_review, build_review_report


def run_check(
    repo_path: str | Path = ".",
    json_output: bool = False,
    since_ref: str | None = None,
) -> int:
    """Run local QA feedback before a user pushes code."""
    try:
        context = collect_repo_context(
            repo_path,
            since_ref=since_ref,
            include_worktree=True,
        )
        learned_rules = load_learned_rules(repo_path)
    except (GitCommandError, LearnedRulesError) as error:
        if json_output:
            print(json.dumps(_error_payload(error), indent=2))
            return 1
        _print_check_error(error)
        return 1

    findings = run_local_checks(context, repo_path)
    history_write = record_findings(context, findings, repo_path)
    if json_output:
        print(json.dumps(_success_payload(context, learned_rules, findings), indent=2))
        return 1 if findings else 0

    print("OpenPandora check")
    print(f"Branch: {context.branch_name}")
    print(f"Commit: {context.current_commit[:12]}")
    if context.base_ref:
        print(f"Compared with: {context.base_ref}")
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

    if history_write:
        print(f"Recorded this finding history in {history_write.path}.")
        print("OpenPandora did not add or enforce any learned rule automatically.")

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
        "base_ref": context.base_ref,
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


def run_providers(
    action: str = "list",
    provider_name: str | None = None,
    repo_path: str | Path = ".",
) -> int:
    """Show provider auth options without exposing secret values."""
    if action == "select":
        if provider_name is None:
            print("Choose a provider: openai, anthropic, or local.")
            return 1
        provider_config = select_provider(provider_name, repo_path)
        print(f"Selected {provider_config.provider} for AI review.")
        print(f"Saved choice to {provider_config.config_path}.")
        print("OpenPandora did not store any API keys.")
        return 0

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


def run_pr_body(repo_path: str | Path = ".", since_ref: str | None = None) -> int:
    """Print a GitHub-ready QA summary without opening a PR."""
    try:
        context = collect_repo_context(
            repo_path,
            since_ref=since_ref,
            include_worktree=True,
        )
        learned_rules = load_learned_rules(repo_path)
    except (GitCommandError, LearnedRulesError) as error:
        _print_check_error(error)
        return 1

    findings = run_local_checks(context, repo_path)
    print(build_pr_body(context, findings, learned_rules))
    return 1 if findings else 0


def run_pr_create(
    repo_path: str | Path = ".",
    since_ref: str | None = None,
    create: bool = False,
) -> int:
    """Prepare or create a GitHub pull request for the current branch."""
    try:
        config = load_project_config(repo_path)
        base_ref = since_ref or config.base_ref
        context = collect_repo_context(
            repo_path,
            since_ref=base_ref,
            include_worktree=True,
        )
        learned_rules = load_learned_rules(repo_path)
        findings = run_local_checks(context, repo_path)
        repo = detect_github_repo(repo_path)
        body = build_pr_body(context, findings, learned_rules)
        plan = build_pull_request_plan(
            repo=repo,
            title=f"OpenPandora QA for {context.branch_name}",
            body=body,
            head=context.branch_name,
            base=base_ref,
        )
    except (
        GitCommandError,
        GitHubPullRequestError,
        LearnedRulesError,
        ProjectConfigError,
    ) as error:
        _print_check_error(error)
        return 1

    if not create:
        print("OpenPandora pull request dry run")
        print("No GitHub pull request was opened.")
        print(f"Repository: {plan.repo.owner}/{plan.repo.name}")
        print(f"Base: {plan.base}")
        print(f"Head: {plan.head}")
        print(f"Title: {plan.title}")
        return 0

    try:
        result = create_pull_request(plan)
    except GitHubPullRequestError as error:
        _print_check_error(error)
        return 1

    print(f"Created pull request: {result.url}")
    return 0


def run_init(repo_path: str | Path = ".") -> int:
    """Create starter OpenPandora files for a project."""
    result = initialize_project(repo_path)
    if result.rules_created:
        print(f"Created {result.rules_path}")
    else:
        print(f"{result.rules_path} already exists.")
        print("OpenPandora left it unchanged.")

    if result.config_created:
        print(f"Created {result.config_path}")
    else:
        print(f"{result.config_path} already exists.")
        print("OpenPandora left it unchanged.")
    print("You can edit these files anytime.")
    return 0


def run_history(repo_path: str | Path = ".") -> int:
    """Show recorded OpenPandora findings and fixes."""
    events = load_history(repo_path)
    print("OpenPandora history")
    if not events:
        print("No history recorded yet.")
        return 0

    for event in events[-10:]:
        event_type = event.get("type", "event")
        branch = event.get("branch", "unknown")
        created_at = event.get("created_at", "unknown time")
        print(f"- {event_type} on {branch} at {created_at}")
        if event_type == "findings":
            findings = event.get("findings", [])
            print(f"  Findings: {len(findings)}")
        if event_type == "fix" and event.get("pull_request_url"):
            print(f"  PR: {event['pull_request_url']}")
    return 0


def run_test(repo_path: str | Path = ".") -> int:
    """Run the project's configured test and lint commands."""
    try:
        config = load_project_config(repo_path)
    except ProjectConfigError as error:
        print("OpenPandora could not read this project's config.")
        print(error)
        return 1

    results = run_project_commands(
        (
            ("Tests", config.test_command),
            ("Lint", config.lint_command),
        ),
        repo_path,
    )

    print("OpenPandora project commands")
    for result in results:
        _print_command_result(result)

    if all(result.passed for result in results):
        print("All configured commands passed.")
        return 0

    print("One or more configured commands failed.")
    return 1


def run_review(
    repo_path: str | Path = ".",
    since_ref: str | None = None,
) -> int:
    """Review the branch using local checks and configured commands."""
    try:
        request = _build_review_request(repo_path, since_ref)
    except (GitCommandError, LearnedRulesError, ProjectConfigError) as error:
        _print_check_error(error)
        return 1

    provider_text, provider_error = _request_provider_text(request)
    result = build_review(request, provider_text, provider_error)
    print(build_review_report(request, result), end="")
    return 1 if result.has_issues else 0


def run_improve(
    repo_path: str | Path = ".",
    since_ref: str | None = None,
    dry_run: bool = True,
    apply_changes: bool = False,
) -> int:
    """Show a safe improvement plan without editing files."""
    try:
        request = _build_review_request(repo_path, since_ref)
    except (GitCommandError, LearnedRulesError, ProjectConfigError) as error:
        _print_check_error(error)
        return 1

    if apply_changes:
        return _run_improve_apply(request, repo_path)

    provider_text, provider_error = _request_provider_text(request)
    result = build_review(request, provider_text, provider_error)
    print(build_improve_plan(result), end="")
    return 1 if result.has_issues else 0


def run_fix_pr(
    repo_path: str | Path = ".",
    since_ref: str | None = None,
    create: bool = False,
) -> int:
    """Prepare or create a fix PR from a provider patch."""
    try:
        request = _build_review_request(repo_path, since_ref)
    except (GitCommandError, LearnedRulesError, ProjectConfigError) as error:
        _print_check_error(error)
        return 1

    source_branch = request.context.branch_name
    if is_openpandora_fix_branch(source_branch):
        print("OpenPandora loop protection")
        print(f"This branch was created by OpenPandora: {source_branch}")
        print("Checks can still run, but no new fix PR was opened from this branch.")
        return 0

    review_result = build_review(request)
    if not review_result.has_issues:
        print("OpenPandora did not find anything that needs a fix PR.")
        return 0

    try:
        attempt_plan = plan_fix_attempt(source_branch, repo_path)
    except GitChangeError as error:
        _print_check_error(error)
        return 1

    if attempt_plan is None:
        print("OpenPandora fix attempt limit reached")
        print(f"It already tried 4 fix PRs for this branch: {source_branch}")
        print("It stopped before calling the AI provider again.")
        return 0

    provider_text, provider_error = _request_provider_fix_text(request)
    if provider_error:
        _print_check_error(ProviderReviewError(provider_error))
        return 1

    patch_text = extract_unified_diff(provider_text or "")
    if patch_text is None:
        print("OpenPandora could not find a usable patch in the provider response.")
        return 1

    fix_branch = attempt_plan.branch_name

    try:
        if has_worktree_changes(repo_path):
            raise GitChangeError(
                "OpenPandora needs a clean worktree before creating a fix PR."
            )
        apply_unified_diff(patch_text, repo_path, check_only=True)
    except (GitChangeError, PatchError) as error:
        _print_check_error(error)
        return 1

    if not create:
        print("OpenPandora fix PR dry run")
        print("No files were changed and no pull request was opened.")
        print(f"Base branch: {source_branch}")
        print(f"Fix branch: {fix_branch}")
        print(f"Fix attempt: {attempt_plan.attempt_number}/{attempt_plan.max_attempts}")
        print("Provider patch passed Git's apply check.")
        return 0

    try:
        create_fix_branch(fix_branch, repo_path)
        apply_unified_diff(patch_text, repo_path)
    except (GitChangeError, PatchError) as error:
        _print_check_error(error)
        return 1

    if run_test(repo_path) != 0:
        print("OpenPandora did not commit or open a PR because verification failed.")
        return 1

    try:
        commit_hash = commit_all_changes("fix: address OpenPandora QA", repo_path)
        push_branch(fix_branch, repo_path)
        repo = detect_github_repo(repo_path)
        body = build_pr_body(request.context, request.findings, request.learned_rules)
        plan = build_pull_request_plan(
            repo=repo,
            title=f"fix: address OpenPandora QA for {source_branch}",
            body=body,
            head=fix_branch,
            base=source_branch,
        )
        result = create_pull_request(plan)
        record_fix(
            request.context,
            repo_path,
            fix_branch=fix_branch,
            commit_hash=commit_hash,
            pull_request_url=result.url,
        )
    except (GitChangeError, GitHubPullRequestError) as error:
        _print_check_error(error)
        return 1

    print(f"Created fix pull request: {result.url}")
    return 0


def _run_improve_apply(request: ReviewRequest, repo_path: str | Path = ".") -> int:
    provider_text, provider_error = _request_provider_fix_text(request)
    if provider_error:
        _print_check_error(ProviderReviewError(provider_error))
        return 1

    patch_text = extract_unified_diff(provider_text or "")
    if patch_text is None:
        print("OpenPandora could not find a usable patch in the provider response.")
        return 1

    try:
        result = apply_unified_diff(patch_text, repo_path)
    except PatchError as error:
        _print_check_error(error)
        return 1

    print(f"OpenPandora {result.message.lower()}")
    return run_test(repo_path)


def _request_provider_text(
    request: ReviewRequest,
) -> tuple[str | None, str | None]:
    try:
        provider_review = request_provider_review(request)
    except ProviderReviewError as error:
        return None, str(error)

    if provider_review is None:
        return None, None

    return provider_review.text, None


def _request_provider_fix_text(
    request: ReviewRequest,
) -> tuple[str | None, str | None]:
    try:
        provider_review = request_provider_fix(request)
    except ProviderReviewError as error:
        return None, str(error)

    return provider_review.text, None


def _build_review_request(
    repo_path: str | Path = ".",
    since_ref: str | None = None,
) -> ReviewRequest:
    config = load_project_config(repo_path)
    base_ref = since_ref or config.base_ref
    context = collect_repo_context(
        repo_path,
        since_ref=base_ref,
        include_worktree=True,
    )
    learned_rules = load_learned_rules(repo_path)
    findings = run_local_checks(context, repo_path)
    file_context = collect_file_context(context.changed_files, repo_path)
    command_results = run_project_commands(
        (
            ("Tests", config.test_command),
            ("Lint", config.lint_command),
        ),
        repo_path,
    )
    return ReviewRequest(
        provider=config.provider or "local",
        context=context,
        findings=findings,
        learned_rules=learned_rules,
        command_results=command_results,
        file_context=file_context,
    )


def _print_command_result(result: CommandResult) -> None:
    status = "passed" if result.passed else f"failed with exit {result.return_code}"
    print(f"- {result.name}: {status}")
    print(f"  Command: {result.command}")
    if result.passed:
        return

    output = _trim_command_output(result.stdout, result.stderr)
    if output:
        print("  Output:")
        for line in output.splitlines():
            print(f"    {line}")


def _trim_command_output(stdout: str, stderr: str, max_characters: int = 1800) -> str:
    output = "\n".join(part.strip() for part in (stdout, stderr) if part.strip())
    if len(output) <= max_characters:
        return output
    return output[:max_characters].rstrip() + "\n... output truncated ..."


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
    check_parser.add_argument(
        "--since",
        metavar="REF",
        help="Compare changes against a base ref, such as main.",
    )
    check_parser.set_defaults(command_handler=run_check)

    providers_parser = subparsers.add_parser(
        "providers",
        help="Show available AI provider auth options.",
    )
    providers_parser.add_argument(
        "action",
        nargs="?",
        choices=("list", "select"),
        default="list",
        help="Use 'select' to save a provider choice.",
    )
    providers_parser.add_argument(
        "provider",
        nargs="?",
        choices=("openai", "anthropic", "local"),
        help="Provider to select.",
    )
    providers_parser.set_defaults(command_handler=run_providers)

    pr_body_parser = subparsers.add_parser(
        "pr-body",
        help="Print a GitHub-ready QA summary without opening a PR.",
    )
    pr_body_parser.add_argument(
        "--since",
        metavar="REF",
        help="Compare changes against a base ref, such as main.",
    )
    pr_body_parser.set_defaults(command_handler=run_pr_body)

    pr_create_parser = subparsers.add_parser(
        "pr-create",
        help="Prepare or create a GitHub pull request for this branch.",
    )
    pr_create_parser.add_argument(
        "--since",
        metavar="REF",
        help="Use this base ref for the pull request.",
    )
    pr_create_parser.add_argument(
        "--create",
        action="store_true",
        help="Actually create the pull request with GITHUB_TOKEN.",
    )
    pr_create_parser.set_defaults(command_handler=run_pr_create)

    init_parser = subparsers.add_parser(
        "init",
        help="Create starter OpenPandora project files.",
    )
    init_parser.set_defaults(command_handler=run_init)

    history_parser = subparsers.add_parser(
        "history",
        help="Show recorded OpenPandora findings and fixes.",
    )
    history_parser.set_defaults(command_handler=run_history)

    test_parser = subparsers.add_parser(
        "test",
        help="Run this project's configured test and lint commands.",
    )
    test_parser.set_defaults(command_handler=run_test)

    review_parser = subparsers.add_parser(
        "review",
        help="Review this branch with checks and configured commands.",
    )
    review_parser.add_argument(
        "--since",
        metavar="REF",
        help="Compare changes against a base ref, such as main.",
    )
    review_parser.set_defaults(command_handler=run_review)

    improve_parser = subparsers.add_parser(
        "improve",
        help="Show a safe improvement plan without editing files.",
    )
    improve_parser.add_argument(
        "--since",
        metavar="REF",
        help="Compare changes against a base ref, such as main.",
    )
    improve_parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Show proposed next steps without changing files.",
    )
    improve_parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply a provider patch to the current worktree.",
    )
    improve_parser.set_defaults(command_handler=run_improve)

    fix_pr_parser = subparsers.add_parser(
        "fix-pr",
        help="Create a fix branch and PR from a provider patch.",
    )
    fix_pr_parser.add_argument(
        "--since",
        metavar="REF",
        help="Compare changes against a base ref, such as main.",
    )
    fix_pr_parser.add_argument(
        "--create",
        action="store_true",
        help="Actually push the fix branch and create the PR.",
    )
    fix_pr_parser.set_defaults(command_handler=run_fix_pr)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the OpenPandora command line interface."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "check":
        return args.command_handler(json_output=args.json, since_ref=args.since)
    if args.command == "providers":
        return args.command_handler(action=args.action, provider_name=args.provider)
    if args.command == "pr-body":
        return args.command_handler(since_ref=args.since)
    if args.command == "pr-create":
        return args.command_handler(since_ref=args.since, create=args.create)
    if args.command == "review":
        return args.command_handler(since_ref=args.since)
    if args.command == "improve":
        return args.command_handler(
            since_ref=args.since,
            dry_run=args.dry_run,
            apply_changes=args.apply,
        )
    if args.command == "fix-pr":
        return args.command_handler(since_ref=args.since, create=args.create)
    return args.command_handler()
