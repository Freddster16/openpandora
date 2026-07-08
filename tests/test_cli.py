import json
from types import SimpleNamespace

import pytest

from openpandora import __version__, cli
from openpandora.cli import main, run_check
from openpandora.command_runner import CommandResult
from openpandora.findings import Finding, Severity
from openpandora.git_changes import FixAttemptPlan
from openpandora.git_context import GitCommandError, RepoContext
from openpandora.github_pull_requests import GitHubRepo, PullRequestResult
from openpandora.learned_rules import LearnedRule
from openpandora.patches import PatchResult
from openpandora.project_config import ProjectConfig
from openpandora.review import ReviewRequest

PATCH_TEXT = """diff --git a/demo.txt b/demo.txt
--- a/demo.txt
+++ b/demo.txt
@@ -1 +1 @@
-hello
+hello world
"""


def test_check_command_reports_no_issues(monkeypatch, capsys):
    context = RepoContext(
        branch_name="feature/demo",
        current_commit="abc123def4567890",
        changed_files=("src/openpandora/cli.py",),
    )
    monkeypatch.setattr(
        cli,
        "collect_repo_context",
        lambda repo_path=".", since_ref=None, include_worktree=False: context,
    )
    monkeypatch.setattr(cli, "load_learned_rules", lambda repo_path=".": ())
    monkeypatch.setattr(cli, "run_local_checks", lambda repo_context, repo_path=".": ())

    assert main(["check"]) == 0

    output = capsys.readouterr().out
    assert "OpenPandora check" in output
    assert "Branch: feature/demo" in output
    assert "Commit: abc123def456" in output
    assert "Changed files: 1" in output
    assert "No issues found." in output


def test_check_command_accepts_since_ref(monkeypatch, capsys):
    captured_since_refs = []
    context = RepoContext(
        branch_name="feature/demo",
        current_commit="abc123def4567890",
        changed_files=("src/openpandora/cli.py", "tests/test_cli.py"),
        base_ref="main",
    )

    def collect_context(repo_path=".", since_ref=None, include_worktree=False):
        captured_since_refs.append(since_ref)
        return context

    monkeypatch.setattr(cli, "collect_repo_context", collect_context)
    monkeypatch.setattr(cli, "load_learned_rules", lambda repo_path=".": ())
    monkeypatch.setattr(cli, "run_local_checks", lambda repo_context, repo_path=".": ())

    assert main(["check", "--since", "main"]) == 0

    output = capsys.readouterr().out
    assert captured_since_refs == ["main"]
    assert "Compared with: main" in output


def test_check_command_shows_loaded_learned_rules(monkeypatch, capsys):
    context = RepoContext(
        branch_name="feature/demo",
        current_commit="abc123def4567890",
        changed_files=("README.md",),
    )
    rules = (
        LearnedRule(
            title="Prefer focused tests",
            message="Add a small test with each behavior change.",
            severity=Severity.WARNING,
        ),
    )
    monkeypatch.setattr(
        cli,
        "collect_repo_context",
        lambda repo_path=".", since_ref=None, include_worktree=False: context,
    )
    monkeypatch.setattr(cli, "load_learned_rules", lambda repo_path=".": rules)
    monkeypatch.setattr(cli, "run_local_checks", lambda repo_context, repo_path=".": ())

    assert main(["check"]) == 0

    output = capsys.readouterr().out
    assert "Loaded learned rules: 1" in output
    assert "Learning is active for reviews and provider prompts." in output
    assert "[warning] Prefer focused tests" in output


def test_check_command_can_print_json_results(monkeypatch, capsys):
    context = RepoContext(
        branch_name="feature/demo",
        current_commit="abc123def4567890",
        changed_files=("README.md",),
    )
    rules = (
        LearnedRule(
            title="Prefer focused tests",
            message="Add a small test with each behavior change.",
        ),
    )
    monkeypatch.setattr(
        cli,
        "collect_repo_context",
        lambda repo_path=".", since_ref=None, include_worktree=False: context,
    )
    monkeypatch.setattr(cli, "load_learned_rules", lambda repo_path=".": rules)
    monkeypatch.setattr(cli, "run_local_checks", lambda repo_context, repo_path=".": ())

    assert main(["check", "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "passed"
    assert payload["branch"] == "feature/demo"
    assert payload["commit"] == "abc123def4567890"
    assert payload["base_ref"] is None
    assert payload["changed_files"] == ["README.md"]
    assert payload["learned_rules"][0]["title"] == "Prefer focused tests"
    assert payload["findings"] == []


def test_check_command_reports_findings(monkeypatch, capsys):
    context = RepoContext(
        branch_name="feature/demo",
        current_commit="abc123def4567890",
        changed_files=("src/openpandora/cli.py",),
    )
    finding = Finding(
        title="Add a test",
        message="This change should include a focused test.",
        severity=Severity.ERROR,
        file_path="src/openpandora/cli.py",
        line_number=10,
        suggestion="Add a pytest case for the new behavior.",
    )
    monkeypatch.setattr(
        cli,
        "collect_repo_context",
        lambda repo_path=".", since_ref=None, include_worktree=False: context,
    )
    monkeypatch.setattr(cli, "load_learned_rules", lambda repo_path=".": ())
    monkeypatch.setattr(
        cli, "run_local_checks", lambda repo_context, repo_path=".": (finding,)
    )
    monkeypatch.setattr(
        cli,
        "record_findings",
        lambda repo_context, findings, repo_path=".": SimpleNamespace(
            path=".openpandora/history.jsonl"
        ),
    )

    assert main(["check"]) == 1

    output = capsys.readouterr().out
    assert "Found 1 issue(s):" in output
    assert "[error] Add a test (src/openpandora/cli.py:10)" in output
    assert "Suggestion: Add a pytest case for the new behavior." in output
    assert "Recorded this finding history" in output


def test_check_command_reports_newly_learned_rules(monkeypatch, capsys):
    context = RepoContext(
        branch_name="feature/demo",
        current_commit="abc123def4567890",
        changed_files=("src/openpandora/cli.py",),
    )
    finding = Finding(
        title="Add a test",
        message="This change should include a focused test.",
        severity=Severity.WARNING,
        file_path="src/openpandora/cli.py",
    )
    learned_rule = LearnedRule(
        title="Learned: Add a test",
        message="Add a pytest case.",
    )
    monkeypatch.setattr(
        cli,
        "collect_repo_context",
        lambda repo_path=".", since_ref=None, include_worktree=False: context,
    )
    monkeypatch.setattr(
        cli,
        "load_learned_rules",
        lambda repo_path=".": (learned_rule,),
    )
    monkeypatch.setattr(
        cli, "run_local_checks", lambda repo_context, repo_path=".": (finding,)
    )
    monkeypatch.setattr(
        cli,
        "_record_findings_and_learn",
        lambda repo_context, findings, repo_path=".": (
            SimpleNamespace(path=".openpandora/history.jsonl"),
            SimpleNamespace(
                path=".openpandora/rules.json",
                added_rules=(learned_rule,),
            ),
        ),
    )

    assert main(["check"]) == 1

    output = capsys.readouterr().out
    assert "Loaded learned rules: 1" in output
    assert "Learned 1 new rule(s)" in output


def test_check_command_can_print_json_findings(monkeypatch, capsys):
    context = RepoContext(
        branch_name="feature/demo",
        current_commit="abc123def4567890",
        changed_files=("src/openpandora/cli.py",),
    )
    finding = Finding(
        title="Add a test",
        message="This change should include a focused test.",
        severity=Severity.ERROR,
        file_path="src/openpandora/cli.py",
        line_number=10,
    )
    monkeypatch.setattr(
        cli,
        "collect_repo_context",
        lambda repo_path=".", since_ref=None, include_worktree=False: context,
    )
    monkeypatch.setattr(cli, "load_learned_rules", lambda repo_path=".": ())
    monkeypatch.setattr(
        cli, "run_local_checks", lambda repo_context, repo_path=".": (finding,)
    )
    monkeypatch.setattr(
        cli,
        "record_findings",
        lambda repo_context, findings, repo_path=".": SimpleNamespace(
            path=".openpandora/history.jsonl"
        ),
    )

    assert main(["check", "--json"]) == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "failed"
    assert payload["findings"][0]["severity"] == "error"
    assert payload["findings"][0]["location"] == "src/openpandora/cli.py:10"


def test_check_command_explains_non_git_directories(tmp_path, capsys):
    assert run_check(tmp_path) == 1

    output = capsys.readouterr().out
    assert "OpenPandora could not check this project." in output
    assert "OpenPandora needs to run inside a Git project." in output
    assert "Try: cd path/to/your/project" in output
    assert "Then run: openpandora check" in output
    assert "Git command failed" not in output


def test_check_command_can_print_json_errors(tmp_path, capsys):
    assert run_check(tmp_path, json_output=True) == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "error"
    assert payload["message"] == "OpenPandora needs to run inside a Git project."
    assert payload["next_step"] == "cd path/to/your/project && openpandora check"


def test_check_command_explains_other_git_errors(monkeypatch, capsys):
    def raise_git_error(repo_path=".", since_ref=None, include_worktree=False):
        raise GitCommandError("fatal: could not read HEAD")

    monkeypatch.setattr(cli, "collect_repo_context", raise_git_error)

    assert main(["check"]) == 1

    output = capsys.readouterr().out
    assert "OpenPandora could not check this project." in output
    assert "could not read HEAD" in output


def test_version_flag_shows_current_version(capsys):
    with pytest.raises(SystemExit) as error:
        main(["--version"])

    assert error.value.code == 0
    assert f"openpandora {__version__}" in capsys.readouterr().out


def test_help_lists_check_command(capsys):
    with pytest.raises(SystemExit) as error:
        main(["--help"])

    assert error.value.code == 0
    output = capsys.readouterr().out
    assert "Run beginner-friendly QA feedback for your code." in output
    assert "check" in output


def test_missing_command_exits_with_usage(capsys):
    with pytest.raises(SystemExit) as error:
        main([])

    assert error.value.code == 2
    error_output = capsys.readouterr().err
    assert "usage:" in error_output
    assert "the following arguments are required: command" in error_output


def test_init_command_creates_rules_template(tmp_path, capsys):
    assert cli.run_init(tmp_path) == 0

    output = capsys.readouterr().out
    assert "Created" in output
    assert "rules.json" in output
    assert "config.json" in output
    assert (tmp_path / ".openpandora" / "rules.json").exists()
    assert (tmp_path / ".openpandora" / "config.json").exists()


def test_init_command_does_not_overwrite_existing_rules(tmp_path, capsys):
    rules_dir = tmp_path / ".openpandora"
    rules_dir.mkdir()
    rules_path = rules_dir / "rules.json"
    rules_path.write_text('{"rules": []}\n')

    assert cli.run_init(tmp_path) == 0

    output = capsys.readouterr().out
    assert "already exists" in output
    assert "left it unchanged" in output
    assert rules_path.read_text() == '{"rules": []}\n'


def test_history_command_reports_empty_history(tmp_path, capsys):
    assert cli.run_history(tmp_path) == 0

    output = capsys.readouterr().out
    assert "OpenPandora history" in output
    assert "No history recorded yet." in output


def test_history_command_shows_recent_events(tmp_path, capsys):
    history_path = tmp_path / ".openpandora" / "history.jsonl"
    history_path.parent.mkdir()
    history_path.write_text(
        '{"type": "findings", "branch": "feature/demo", '
        '"created_at": "2026-01-01T00:00:00Z", "findings": [1]}\n'
        '{"type": "fix", "branch": "feature/demo", '
        '"created_at": "2026-01-02T00:00:00Z", '
        '"pull_request_url": "https://github.com/owner/repo/pull/1"}\n'
    )

    assert cli.run_history(tmp_path) == 0

    output = capsys.readouterr().out
    assert "findings on feature/demo" in output
    assert "Findings: 1" in output
    assert "fix on feature/demo" in output
    assert "https://github.com/owner/repo/pull/1" in output


def test_test_command_runs_configured_commands(monkeypatch, capsys):
    captured_commands = []

    def fake_run_project_commands(commands, repo_path="."):
        captured_commands.extend(commands)
        return (
            CommandResult("Tests", "python -m pytest", 0, "tests passed", ""),
            CommandResult("Lint", "ruff check .", 0, "lint passed", ""),
        )

    monkeypatch.setattr(cli, "run_project_commands", fake_run_project_commands)

    assert main(["test"]) == 0

    output = capsys.readouterr().out
    assert captured_commands == [
        ("Tests", "python -m pytest"),
        ("Lint", "ruff check ."),
    ]
    assert "OpenPandora project commands" in output
    assert "All configured commands passed." in output
    assert "tests passed" not in output


def test_test_command_returns_failure_when_a_command_fails(monkeypatch, capsys):
    def fake_run_project_commands(commands, repo_path="."):
        return (
            CommandResult("Tests", "python -m pytest", 1, "", "tests failed"),
            CommandResult("Lint", "ruff check .", 0, "", ""),
        )

    monkeypatch.setattr(cli, "run_project_commands", fake_run_project_commands)

    assert main(["test"]) == 1

    output = capsys.readouterr().out
    assert "Tests: failed with exit 1" in output
    assert "tests failed" in output
    assert "One or more configured commands failed." in output


def test_wake_reports_nothing_found(monkeypatch, capsys):
    request = ReviewRequest(
        provider="local",
        context=RepoContext(
            branch_name="feature/demo",
            current_commit="abc123def4567890",
            changed_files=(),
            base_ref="main",
        ),
        findings=(),
    )
    monkeypatch.setattr(
        cli, "load_project_config", lambda repo_path=".": ProjectConfig()
    )
    monkeypatch.setattr(
        cli,
        "_build_review_request",
        lambda repo_path=".", since_ref=None: request,
    )

    def fail_record_findings(repo_context, findings, repo_path="."):
        raise AssertionError("fix-pr wake should keep the worktree clean")

    monkeypatch.setattr(cli, "_record_findings_and_learn", fail_record_findings)

    assert cli.run_wake(event="manual", since_ref="main") == 0

    output = capsys.readouterr().out
    assert "OpenPandora woke up for manual." in output
    assert "OpenPandora wake: nothing found." in output


def test_wake_can_create_fix_pr_when_issue_is_found(monkeypatch, capsys):
    captured = {}
    finding = Finding(title="Add a focused test", message="Missing test.")
    request = ReviewRequest(
        provider="openai",
        context=RepoContext(
            branch_name="feature/demo",
            current_commit="abc123def4567890",
            changed_files=("src/demo.py",),
            base_ref="main",
        ),
        findings=(finding,),
    )
    monkeypatch.setattr(
        cli, "load_project_config", lambda repo_path=".": ProjectConfig()
    )
    monkeypatch.setattr(
        cli,
        "_build_review_request",
        lambda repo_path=".", since_ref=None: request,
    )
    monkeypatch.setattr(
        cli,
        "_record_findings_and_learn",
        lambda repo_context, findings, repo_path=".": (None, None),
    )

    def fake_run_fix_pr(repo_path=".", since_ref=None, create=False):
        captured["since_ref"] = since_ref
        captured["create"] = create
        return 0

    monkeypatch.setattr(cli, "run_fix_pr", fake_run_fix_pr)

    assert cli.run_wake(event="manual", since_ref="main") == 0

    assert captured == {"since_ref": "main", "create": True}
    assert "OpenPandora woke up for manual." in capsys.readouterr().out


def test_wake_records_findings_when_fix_prs_are_disabled(monkeypatch, capsys):
    captured = {}
    finding = Finding(title="Add a focused test", message="Missing test.")
    request = ReviewRequest(
        provider="openai",
        context=RepoContext(
            branch_name="feature/demo",
            current_commit="abc123def4567890",
            changed_files=("src/demo.py",),
            base_ref="main",
        ),
        findings=(finding,),
    )
    monkeypatch.setattr(
        cli,
        "load_project_config",
        lambda repo_path=".": ProjectConfig(auto_create_pr=False),
    )
    monkeypatch.setattr(
        cli,
        "_build_review_request",
        lambda repo_path=".", since_ref=None: request,
    )

    def fake_record_findings(repo_context, findings, repo_path="."):
        captured["findings"] = findings
        return (None, None)

    def fail_run_fix_pr(repo_path=".", since_ref=None, create=False):
        raise AssertionError("review-only wake should not create a fix PR")

    monkeypatch.setattr(cli, "_record_findings_and_learn", fake_record_findings)
    monkeypatch.setattr(cli, "run_fix_pr", fail_run_fix_pr)

    assert cli.run_wake(event="manual", since_ref="main") == 1

    output = capsys.readouterr().out
    assert captured["findings"] == (finding,)
    assert "OpenPandora found something to review." in output


def test_providers_command_lists_auth_options(monkeypatch, capsys):
    monkeypatch.setenv("OPENAI_API_KEY", "secret-value")

    assert main(["providers"]) == 0

    output = capsys.readouterr().out
    assert "OpenPandora provider setup" in output
    assert "OpenAI (openai): ready" in output
    assert "Anthropic (anthropic): needs setup" in output
    assert "API key env var: OPENAI_API_KEY" in output
    assert "environment" in output
    assert "secret-value" not in output


def test_providers_select_command_saves_choice(tmp_path, capsys):
    assert (
        cli.run_providers(action="select", provider_name="openai", repo_path=tmp_path)
        == 0
    )

    output = capsys.readouterr().out
    assert "Selected openai for AI review." in output
    assert "config.json" in output
    assert "did not store any API keys" in output
    assert (tmp_path / ".openpandora" / "config.json").exists()


def test_providers_select_command_requires_provider(capsys):
    assert cli.run_providers(action="select") == 1

    output = capsys.readouterr().out
    assert "Choose a provider" in output


def test_learn_command_saves_user_preference(tmp_path, capsys):
    assert (
        cli.run_learn(
            "Keep README changes short and focused.",
            repo_path=tmp_path,
            title="Keep README minimal",
        )
        == 0
    )

    output = capsys.readouterr().out
    assert "Learned rule saved" in output
    assert "Keep README minimal" in output
    assert (tmp_path / ".openpandora" / "rules.json").exists()


def test_learn_command_reports_duplicate_preference(tmp_path, capsys):
    kwargs = {
        "rule_text": "Keep README changes short and focused.",
        "repo_path": tmp_path,
        "title": "Keep README minimal",
    }

    assert cli.run_learn(**kwargs) == 0
    assert cli.run_learn(**kwargs) == 0

    output = capsys.readouterr().out
    assert "already knows" in output


def test_learn_command_parses_cli_arguments(monkeypatch):
    captured = {}

    def fake_run_learn(rule_text, **kwargs):
        captured["rule_text"] = rule_text
        captured.update(kwargs)
        return 0

    monkeypatch.setattr(cli, "run_learn", fake_run_learn)

    assert (
        main(
            [
                "learn",
                "Keep",
                "README",
                "minimal",
                "--title",
                "Docs style",
                "--severity",
                "warning",
            ]
        )
        == 0
    )

    assert captured["rule_text"] == "Keep README minimal"
    assert captured["title"] == "Docs style"
    assert captured["severity"] == "warning"


@pytest.mark.parametrize(
    ("arguments", "expected_if_needed"),
    ((["setup"], False), (["setup", "--if-needed"], True)),
)
def test_setup_command_forwards_if_needed(arguments, expected_if_needed, monkeypatch):
    captured = {}
    monkeypatch.setenv("OPENPANDORA_HOOK_COMMAND", "/tmp/openpandora")

    def fake_setup_wizard(repo_path=".", **kwargs):
        captured["repo_path"] = repo_path
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(cli, "safe_run_setup_wizard", fake_setup_wizard)

    assert main(arguments) == 0

    assert captured["repo_path"] == "."
    assert captured["global_config"] is True
    assert captured["reset"] is False
    assert captured["skip_existing"] is expected_if_needed
    assert captured["executable"] == "/tmp/openpandora"


def test_pr_body_command_prints_summary(monkeypatch, capsys):
    context = RepoContext(
        branch_name="feature/demo",
        current_commit="abc123def4567890",
        changed_files=("README.md",),
    )
    monkeypatch.setattr(
        cli,
        "collect_repo_context",
        lambda repo_path=".", since_ref=None, include_worktree=False: context,
    )
    monkeypatch.setattr(cli, "load_learned_rules", lambda repo_path=".": ())
    monkeypatch.setattr(cli, "run_local_checks", lambda repo_context, repo_path=".": ())

    assert main(["pr-body"]) == 0

    output = capsys.readouterr().out
    assert "# OpenPandora QA" in output
    assert "No findings." in output


def test_pr_body_command_accepts_since_ref(monkeypatch, capsys):
    captured_since_refs = []
    context = RepoContext(
        branch_name="feature/demo",
        current_commit="abc123def4567890",
        changed_files=("README.md",),
        base_ref="main",
    )

    def collect_context(repo_path=".", since_ref=None, include_worktree=False):
        captured_since_refs.append(since_ref)
        return context

    monkeypatch.setattr(cli, "collect_repo_context", collect_context)
    monkeypatch.setattr(cli, "load_learned_rules", lambda repo_path=".": ())
    monkeypatch.setattr(cli, "run_local_checks", lambda repo_context, repo_path=".": ())

    assert main(["pr-body", "--since", "main"]) == 0

    output = capsys.readouterr().out
    assert captured_since_refs == ["main"]
    assert "Compared with: `main`" in output


def test_pr_create_command_prints_dry_run(monkeypatch, capsys):
    context = RepoContext(
        branch_name="feature/demo",
        current_commit="abc123def4567890",
        changed_files=("README.md",),
        base_ref="main",
    )
    monkeypatch.setattr(
        cli,
        "collect_repo_context",
        lambda repo_path=".", since_ref=None, include_worktree=False: context,
    )
    monkeypatch.setattr(cli, "load_learned_rules", lambda repo_path=".": ())
    monkeypatch.setattr(cli, "run_local_checks", lambda repo_context, repo_path=".": ())
    monkeypatch.setattr(
        cli,
        "detect_github_repo",
        lambda repo_path=".": GitHubRepo("Freddster16", "openpandora"),
    )

    assert main(["pr-create", "--since", "main"]) == 0

    output = capsys.readouterr().out
    assert "OpenPandora pull request dry run" in output
    assert "No GitHub pull request was opened." in output
    assert "Repository: Freddster16/openpandora" in output
    assert "Base: main" in output
    assert "Head: feature/demo" in output


def test_review_command_prints_review(monkeypatch, capsys):
    captured_since_refs = []
    request = ReviewRequest(
        provider="local",
        context=RepoContext(
            branch_name="feature/demo",
            current_commit="abc123def4567890",
            changed_files=("README.md",),
            base_ref="main",
        ),
        findings=(),
        command_results=(
            CommandResult("Tests", "python -m pytest", 0, "", ""),
            CommandResult("Lint", "ruff check .", 0, "", ""),
        ),
    )

    def fake_build_review_request(repo_path=".", since_ref=None):
        captured_since_refs.append(since_ref)
        return request

    monkeypatch.setattr(cli, "_build_review_request", fake_build_review_request)
    monkeypatch.setattr(cli, "_request_provider_text", lambda request: (None, None))

    assert main(["review", "--since", "main"]) == 0

    output = capsys.readouterr().out
    assert captured_since_refs == ["main"]
    assert "OpenPandora review" in output
    assert "Provider: local" in output
    assert "No changes suggested." in output


def test_improve_command_prints_dry_run_plan(monkeypatch, capsys):
    request = ReviewRequest(
        provider="local",
        context=RepoContext(
            branch_name="feature/demo",
            current_commit="abc123def4567890",
            changed_files=("src/openpandora/cli.py",),
        ),
        findings=(
            Finding(
                title="Add a focused test",
                message="A source file changed without a matching test.",
                suggestion="Add tests/test_cli.py.",
            ),
        ),
    )

    monkeypatch.setattr(
        cli,
        "_build_review_request",
        lambda repo_path=".", since_ref=None: request,
    )
    monkeypatch.setattr(cli, "_request_provider_text", lambda request: (None, None))

    assert main(["improve", "--dry-run"]) == 1

    output = capsys.readouterr().out
    assert "OpenPandora improve dry run" in output
    assert "No files were changed." in output
    assert "Add tests/test_cli.py." in output


def test_improve_apply_uses_provider_patch(monkeypatch, capsys):
    request = ReviewRequest(
        provider="openai",
        context=RepoContext(
            branch_name="feature/demo",
            current_commit="abc123def4567890",
            changed_files=("demo.txt",),
        ),
        findings=(
            Finding(
                title="Fix demo",
                message="Demo needs a fix.",
            ),
        ),
    )
    applied_patches = []

    monkeypatch.setattr(
        cli,
        "_build_review_request",
        lambda repo_path=".", since_ref=None: request,
    )
    monkeypatch.setattr(
        cli,
        "_request_provider_fix_text",
        lambda review_request: (f"```diff\n{PATCH_TEXT}```", None),
    )
    monkeypatch.setattr(
        cli,
        "apply_unified_diff",
        lambda patch_text, repo_path=".": (
            applied_patches.append(patch_text)
            or PatchResult(applied=True, message="Patch applied.")
        ),
    )
    monkeypatch.setattr(cli, "run_test", lambda repo_path=".": 0)

    assert main(["improve", "--apply"]) == 0

    output = capsys.readouterr().out
    assert applied_patches == [PATCH_TEXT]
    assert "OpenPandora patch applied." in output


def test_fix_pr_command_prints_dry_run(monkeypatch, capsys):
    request = ReviewRequest(
        provider="openai",
        context=RepoContext(
            branch_name="feature/demo",
            current_commit="abc123def4567890",
            changed_files=("demo.txt",),
        ),
        findings=(Finding(title="Fix demo", message="Demo needs a fix."),),
    )

    monkeypatch.setattr(
        cli,
        "_build_review_request",
        lambda repo_path=".", since_ref=None: request,
    )
    monkeypatch.setattr(
        cli,
        "_request_provider_fix_text",
        lambda review_request: (PATCH_TEXT, None),
    )
    monkeypatch.setattr(
        cli,
        "plan_fix_attempt",
        lambda source_branch, repo_path=".": FixAttemptPlan(
            branch_name="openpandora/fix-feature-demo",
            attempt_number=1,
            max_attempts=4,
        ),
    )
    monkeypatch.setattr(cli, "has_worktree_changes", lambda repo_path=".": False)
    monkeypatch.setattr(
        cli,
        "apply_unified_diff",
        lambda patch_text, repo_path=".", check_only=False: PatchResult(
            applied=not check_only,
            message="Patch checked.",
        ),
    )

    assert main(["fix-pr"]) == 0

    output = capsys.readouterr().out
    assert "OpenPandora fix PR dry run" in output
    assert "Base branch: feature/demo" in output
    assert "Fix branch: openpandora/fix-feature-demo" in output
    assert "Fix attempt: 1/4" in output


def test_fix_pr_command_skips_generated_fix_branch(monkeypatch, capsys):
    request = ReviewRequest(
        provider="openai",
        context=RepoContext(
            branch_name="openpandora/fix-feature-demo",
            current_commit="abc123def4567890",
            changed_files=("demo.txt",),
        ),
        findings=(Finding(title="Fix demo", message="Demo needs a fix."),),
    )

    def fail_provider_call(review_request):
        raise AssertionError("provider should not be called on fix branches")

    monkeypatch.setattr(
        cli,
        "_build_review_request",
        lambda repo_path=".", since_ref=None: request,
    )
    monkeypatch.setattr(cli, "_request_provider_fix_text", fail_provider_call)

    assert main(["fix-pr"]) == 0

    output = capsys.readouterr().out
    assert "OpenPandora loop protection" in output
    assert "openpandora/fix-feature-demo" in output
    assert "no new fix PR was opened" in output


def test_fix_pr_command_stops_after_four_attempts(monkeypatch, capsys):
    request = ReviewRequest(
        provider="openai",
        context=RepoContext(
            branch_name="feature/demo",
            current_commit="abc123def4567890",
            changed_files=("demo.txt",),
        ),
        findings=(Finding(title="Fix demo", message="Demo needs a fix."),),
    )

    def fail_provider_call(review_request):
        raise AssertionError("provider should not be called after four attempts")

    monkeypatch.setattr(
        cli,
        "_build_review_request",
        lambda repo_path=".", since_ref=None: request,
    )
    monkeypatch.setattr(
        cli, "plan_fix_attempt", lambda source_branch, repo_path=".": None
    )
    monkeypatch.setattr(cli, "_request_provider_fix_text", fail_provider_call)

    assert main(["fix-pr"]) == 0

    output = capsys.readouterr().out
    assert "OpenPandora fix attempt limit reached" in output
    assert "already tried 4 fix PRs" in output
    assert "before calling the AI provider" in output


def test_fix_pr_create_pushes_branch_and_creates_pr(monkeypatch, capsys):
    request = ReviewRequest(
        provider="openai",
        context=RepoContext(
            branch_name="feature/demo",
            current_commit="abc123def4567890",
            changed_files=("demo.txt",),
        ),
        findings=(Finding(title="Fix demo", message="Demo needs a fix."),),
    )
    calls = []

    monkeypatch.setattr(
        cli,
        "_build_review_request",
        lambda repo_path=".", since_ref=None: request,
    )
    monkeypatch.setattr(
        cli,
        "_request_provider_fix_text",
        lambda review_request: (PATCH_TEXT, None),
    )
    monkeypatch.setattr(
        cli,
        "plan_fix_attempt",
        lambda source_branch, repo_path=".": FixAttemptPlan(
            branch_name="openpandora/fix-feature-demo",
            attempt_number=1,
            max_attempts=4,
        ),
    )
    monkeypatch.setattr(cli, "has_worktree_changes", lambda repo_path=".": False)
    monkeypatch.setattr(
        cli,
        "apply_unified_diff",
        lambda patch_text, repo_path=".", check_only=False: (
            calls.append(("apply", check_only))
            or PatchResult(applied=not check_only, message="Patch applied.")
        ),
    )
    monkeypatch.setattr(
        cli,
        "create_fix_branch",
        lambda branch_name, repo_path=".": (
            calls.append(("branch", branch_name)) or branch_name
        ),
    )
    monkeypatch.setattr(cli, "run_test", lambda repo_path=".": 0)
    monkeypatch.setattr(
        cli,
        "commit_all_changes",
        lambda message, repo_path=".": calls.append(("commit", message)) or "abc123",
    )
    monkeypatch.setattr(
        cli,
        "push_branch",
        lambda branch_name, repo_path=".": calls.append(("push", branch_name)),
    )
    monkeypatch.setattr(
        cli,
        "switch_branch",
        lambda branch_name, repo_path=".": calls.append(("switch", branch_name)),
    )
    monkeypatch.setattr(
        cli,
        "detect_github_repo",
        lambda repo_path=".": GitHubRepo("Freddster16", "openpandora"),
    )
    monkeypatch.setattr(
        cli,
        "create_pull_request",
        lambda plan: (
            calls.append(("pr", plan.head, plan.base, plan.body, plan.draft))
            or PullRequestResult("https://github.com/Freddster16/openpandora/pull/1")
        ),
    )
    monkeypatch.setattr(
        cli,
        "record_fix",
        lambda context, repo_path=".", **kwargs: calls.append(
            (
                "record_fix",
                kwargs["fix_branch"],
                kwargs["commit_hash"],
                kwargs["pull_request_url"],
            )
        ),
    )

    assert main(["fix-pr", "--create"]) == 0

    output = capsys.readouterr().out
    assert ("apply", True) in calls
    assert ("branch", "openpandora/fix-feature-demo") in calls
    assert ("apply", False) in calls
    assert ("push", "openpandora/fix-feature-demo") in calls
    pr_call = next(call for call in calls if call[0] == "pr")
    assert pr_call[:3] == ("pr", "openpandora/fix-feature-demo", "feature/demo")
    assert "This PR contains OpenPandora's proposed fix" in pr_call[3]
    assert pr_call[4] is False
    assert (
        "record_fix",
        "openpandora/fix-feature-demo",
        "abc123",
        "https://github.com/Freddster16/openpandora/pull/1",
    ) in calls
    assert ("switch", "feature/demo") in calls
    assert "Created fix pull request" in output
