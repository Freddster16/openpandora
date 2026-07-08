"""Command line interface for OpenPandora."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from openpandora import __version__
from openpandora.checks import run_local_checks
from openpandora.command_runner import CommandResult, run_project_commands
from openpandora.file_context import collect_file_context
from openpandora.findings import Finding, Severity
from openpandora.git_changes import (
    GitChangeError,
    commit_all_changes,
    create_fix_branch,
    has_worktree_changes,
    is_openpandora_fix_branch,
    plan_fix_attempt,
    push_branch,
    switch_branch,
)
from openpandora.git_context import GitCommandError, collect_repo_context
from openpandora.github_pull_requests import (
    GitHubPullRequestError,
    build_pull_request_plan,
    create_pull_request,
    detect_github_repo,
)
from openpandora.history import load_history, record_findings, record_fix
from openpandora.hooks import HOOK_COMMAND_ENV_VAR, HookError, install_git_hooks
from openpandora.improve import build_improve_plan
from openpandora.learned_rules import (
    LearnedRule,
    LearnedRulesError,
    LearnedRulesWrite,
    add_learned_rule,
    learn_from_history,
    load_learned_rules,
)
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
from openpandora.setup_wizard import safe_run_setup_wizard


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
    try:
        history_write, learning_write = _record_findings_and_learn(
            context,
            findings,
            repo_path,
        )
        if learning_write:
            learned_rules = load_learned_rules(repo_path)
    except LearnedRulesError as error:
        if json_output:
            print(json.dumps(_error_payload(error), indent=2))
            return 1
        _print_check_error(error)
        return 1

    if json_output:
        print(
            json.dumps(
                _success_payload(
                    context,
                    learned_rules,
                    findings,
                    learning_write,
                ),
                indent=2,
            )
        )
        return 1 if findings else 0

    print("OpenPandora check")
    print(f"Branch: {context.branch_name}")
    print(f"Commit: {context.current_commit[:12]}")
    if context.base_ref:
        print(f"Compared with: {context.base_ref}")
    print(f"Changed files: {len(context.changed_files)}")
    if learned_rules:
        print(f"Loaded learned rules: {len(learned_rules)}")
        print("Learning is active for reviews and provider prompts.")
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
    if learning_write:
        print(
            f"Learned {len(learning_write.added_rules)} new rule(s) in "
            f"{learning_write.path}."
        )

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


def _success_payload(
    context,
    learned_rules,
    findings,
    learning_write: LearnedRulesWrite | None = None,
) -> dict:
    status = "failed" if findings else "passed"
    return {
        "status": status,
        "branch": context.branch_name,
        "commit": context.current_commit,
        "base_ref": context.base_ref,
        "changed_files": list(context.changed_files),
        "learned_rules": [_rule_payload(rule) for rule in learned_rules],
        "learned_rule_updates": (
            [_rule_payload(rule) for rule in learning_write.added_rules]
            if learning_write
            else []
        ),
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
    auth_method: str | None = None,
    model: str | None = None,
    reasoning: str | None = None,
    global_config: bool = False,
) -> int:
    """Show provider auth options without exposing secret values."""
    if action == "select":
        if provider_name is None:
            print("Choose a provider: openai, anthropic, or local.")
            return 1
        provider_config = select_provider(
            provider_name,
            repo_path,
            auth_method=auth_method,
            model=model,
            reasoning=reasoning,
            global_config=global_config,
        )
        print(f"Selected {provider_config.provider} for AI review.")
        print(f"Saved choice to {provider_config.config_path}.")
        if provider_config.auth_method:
            print(f"Auth method: {provider_config.auth_method}")
        if provider_config.model:
            print(f"Model: {provider_config.model}")
        if provider_config.reasoning:
            print(f"Reasoning: {provider_config.reasoning}")
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


def run_setup(
    repo_path: str | Path = ".",
    global_config: bool = True,
    reset: bool = False,
    if_needed: bool = False,
) -> int:
    """Run first-time terminal setup."""
    result = safe_run_setup_wizard(
        repo_path,
        global_config=global_config,
        reset=reset,
        skip_existing=if_needed,
        executable=_setup_executable(),
    )
    return 0 if result else 1


def _setup_executable() -> str:
    return os.environ.get(HOOK_COMMAND_ENV_VAR) or "openpandora"


def run_learn(
    rule_text: str,
    repo_path: str | Path = ".",
    *,
    title: str | None = None,
    severity: str = Severity.INFO.value,
) -> int:
    """Remember a local user preference or project constraint."""
    try:
        result = add_learned_rule(
            repo_path,
            message=rule_text,
            title=title,
            severity=Severity(severity),
        )
    except (LearnedRulesError, ValueError) as error:
        _print_check_error(error)
        return 1

    if result is None:
        print("OpenPandora already knows that rule.")
        return 0

    print(f"Learned rule saved to {result.path}.")
    for rule in result.added_rules:
        print(f"- [{rule.severity}] {rule.title}")
    print("OpenPandora will include it in future checks, reviews, and fixes.")
    return 0


def run_sleep(repo_path: str | Path = ".", create_pr: bool = False) -> int:
    """Install Git hooks that wake OpenPandora only for this repository."""
    try:
        config = load_project_config(repo_path)
        result = install_git_hooks(
            repo_path,
            create_pr=create_pr or config.auto_create_pr,
        )
    except (HookError, ProjectConfigError) as error:
        _print_check_error(error)
        return 1

    print("OpenPandora is sleeping for this Git repo.")
    print("It will wake on Git commit and push events from your terminal or IDE.")
    print(f"Hooks installed in {result.hooks_dir}.")
    if result.create_pr:
        print("When it finds a safe fix, it will try to create a branch and PR.")
    else:
        print("Automatic PR creation is off. Use --create-pr to enable it.")
    return 0


def run_wake(
    repo_path: str | Path = ".",
    event: str = "manual",
    since_ref: str | None = None,
    create_pr: bool = False,
    stdin_text: str | None = None,
) -> int:
    """Wake from a Git hook, check the change, and optionally open a fix PR."""
    try:
        config = load_project_config(repo_path)
        compare_ref = since_ref or _wake_compare_ref(
            event,
            repo_path,
            config.base_ref,
            stdin_text,
        )
        request = _build_review_request(repo_path, compare_ref)
    except (GitCommandError, LearnedRulesError, ProjectConfigError) as error:
        _print_check_error(error)
        return 1

    review_result = build_review(request)

    print(f"OpenPandora woke up for {event}.")
    if compare_ref:
        print(f"Compared with: {compare_ref}")

    if not review_result.has_issues:
        print("OpenPandora wake: nothing found.")
        return 0

    should_create_pr = create_pr or config.auto_create_pr
    if should_create_pr:
        return run_fix_pr(repo_path, since_ref=compare_ref, create=True)

    try:
        _history_write, learning_write = _record_findings_and_learn(
            request.context,
            request.findings,
            repo_path,
        )
    except LearnedRulesError as error:
        _print_check_error(error)
        return 1

    if learning_write:
        print(
            f"Learned {len(learning_write.added_rules)} new rule(s) in "
            f"{learning_write.path}."
        )

    print("OpenPandora found something to review.")
    print("Run openpandora review for details, or wake with --create-pr.")
    return 1


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


def _record_findings_and_learn(
    context,
    findings: tuple[Finding, ...],
    repo_path: str | Path,
):
    history_write = record_findings(context, findings, repo_path)
    if history_write is None:
        return None, None
    return history_write, learn_from_history(repo_path)


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
        switch_branch(source_branch, repo_path)
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
        auth_method=config.auth_method,
        model=config.model,
        reasoning=config.reasoning,
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


def _wake_compare_ref(
    event: str,
    repo_path: str | Path,
    default_ref: str,
    stdin_text: str | None,
) -> str | None:
    if event == "push":
        hook_input = stdin_text
        if hook_input is None and not sys.stdin.isatty():
            hook_input = sys.stdin.read()
        return (
            _pre_push_compare_ref(hook_input or "")
            or _existing_ref("HEAD~1", repo_path)
            or default_ref
        )
    if event == "commit":
        return _existing_ref("HEAD~1", repo_path) or default_ref
    return default_ref


def _pre_push_compare_ref(hook_input: str) -> str | None:
    zero_sha = "0" * 40
    for line in hook_input.splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        remote_sha = parts[3]
        if remote_sha and remote_sha != zero_sha:
            return remote_sha
    return None


def _existing_ref(ref: str, repo_path: str | Path) -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", ref],
        cwd=Path(repo_path),
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode == 0:
        return ref
    return None


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
    providers_parser.add_argument(
        "--auth-method",
        choices=("oauth", "environment", "none"),
        help="Auth method to save without storing credentials.",
    )
    providers_parser.add_argument(
        "--model",
        help="Model id to save for provider calls.",
    )
    providers_parser.add_argument(
        "--reasoning",
        choices=("low", "medium", "high"),
        help="Reasoning level to save for provider calls.",
    )
    providers_parser.add_argument(
        "--global",
        dest="global_config",
        action="store_true",
        help="Save the provider choice to the per-user config.",
    )
    providers_parser.set_defaults(command_handler=run_providers)

    setup_parser = subparsers.add_parser(
        "setup",
        help="Set or change provider, model, and reasoning setup.",
    )
    setup_scope = setup_parser.add_mutually_exclusive_group()
    setup_scope.add_argument(
        "--global",
        dest="global_config",
        action="store_true",
        default=True,
        help="Save setup to the per-user config.",
    )
    setup_scope.add_argument(
        "--project",
        dest="global_config",
        action="store_false",
        help="Save setup to this project's .openpandora/config.json.",
    )
    setup_parser.add_argument(
        "--reset",
        action="store_true",
        help="Ask setup questions again. Plain 'openpandora setup' does this too.",
    )
    setup_parser.add_argument(
        "--if-needed",
        action="store_true",
        help="Skip setup when a complete OpenAI setup is already saved.",
    )
    setup_parser.set_defaults(command_handler=run_setup)

    sleep_parser = subparsers.add_parser(
        "sleep",
        help="Install Git hooks so OpenPandora wakes on commit and push.",
    )
    sleep_parser.add_argument(
        "--create-pr",
        action="store_true",
        help="Let wake hooks create fix branches and pull requests.",
    )
    sleep_parser.set_defaults(command_handler=run_sleep)

    wake_parser = subparsers.add_parser(
        "wake",
        help="Run the QA wake flow used by OpenPandora Git hooks.",
    )
    wake_parser.add_argument(
        "--event",
        choices=("manual", "commit", "push"),
        default="manual",
        help="Git event that woke OpenPandora.",
    )
    wake_parser.add_argument(
        "--since",
        metavar="REF",
        help="Compare changes against a specific ref.",
    )
    wake_parser.add_argument(
        "--create-pr",
        action="store_true",
        help="Create a fix branch and GitHub PR when a safe patch is available.",
    )
    wake_parser.set_defaults(command_handler=run_wake)

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

    learn_parser = subparsers.add_parser(
        "learn",
        help="Remember a local user preference for future reviews.",
    )
    learn_parser.add_argument(
        "rule",
        nargs="+",
        help="Preference or constraint to remember.",
    )
    learn_parser.add_argument(
        "--title",
        help="Short name for the learned rule.",
    )
    learn_parser.add_argument(
        "--severity",
        choices=("info", "warning", "error"),
        default="info",
        help="How strongly OpenPandora should treat this rule.",
    )
    learn_parser.set_defaults(command_handler=run_learn)

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
        return args.command_handler(
            action=args.action,
            provider_name=args.provider,
            auth_method=args.auth_method,
            model=args.model,
            reasoning=args.reasoning,
            global_config=args.global_config,
        )
    if args.command == "setup":
        return args.command_handler(
            global_config=args.global_config,
            reset=args.reset,
            if_needed=args.if_needed,
        )
    if args.command == "sleep":
        return args.command_handler(create_pr=args.create_pr)
    if args.command == "wake":
        return args.command_handler(
            event=args.event,
            since_ref=args.since,
            create_pr=args.create_pr,
        )
    if args.command == "pr-body":
        return args.command_handler(since_ref=args.since)
    if args.command == "pr-create":
        return args.command_handler(since_ref=args.since, create=args.create)
    if args.command == "learn":
        return args.command_handler(
            " ".join(args.rule),
            title=args.title,
            severity=args.severity,
        )
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
