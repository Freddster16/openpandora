import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from openpandora.command_runner import CommandResult
from openpandora.file_context import FileContext
from openpandora.findings import Finding, Severity
from openpandora.git_context import RepoContext
from openpandora.learned_rules import LearnedRule
from openpandora.provider_clients import (
    ANTHROPIC_MESSAGES_URL,
    OPENAI_RESPONSES_URL,
    ProviderReviewError,
    build_provider_fix_prompt,
    build_provider_prompt,
    request_anthropic_review,
    request_local_fix,
    request_local_review,
    request_openai_account_review,
    request_openai_review,
    request_provider_fix,
    request_provider_review,
)
from openpandora.review import ReviewRequest


def test_request_provider_review_returns_none_for_local_provider():
    request = ReviewRequest(
        provider="local",
        context=RepoContext(
            branch_name="feature/demo",
            current_commit="abc123def4567890",
            changed_files=(),
        ),
        findings=(),
    )

    assert request_provider_review(request, environment={}) is None


def test_request_local_review_runs_configured_command():
    review = request_local_review(
        "Review this.",
        environment={
            "OPENPANDORA_LOCAL_COMMAND": (
                f"{sys.executable} -c "
                "'import sys; print(\"local:\" + sys.stdin.read()[:6])'"
            )
        },
    )

    assert review is not None
    assert review.provider == "local"
    assert review.text == "local:Review"


def test_request_local_fix_requires_command():
    with pytest.raises(ProviderReviewError, match="OPENPANDORA_LOCAL_COMMAND"):
        request_local_fix("Fix this.", environment={})


def test_request_local_fix_runs_configured_command():
    review = request_local_fix(
        "Fix this.",
        environment={
            "OPENPANDORA_LOCAL_COMMAND": (
                f"{sys.executable} -c 'import sys; print(\"```diff\\npatch\\n```\")'"
            )
        },
    )

    assert review.provider == "local"
    assert "patch" in review.text


def test_request_local_review_reports_failed_command():
    with pytest.raises(ProviderReviewError, match="failed with exit 7"):
        request_local_review(
            "Review this.",
            environment={
                "OPENPANDORA_LOCAL_COMMAND": (
                    f"{sys.executable} -c 'import sys; sys.exit(7)'"
                )
            },
        )


def test_request_provider_review_explains_unconnected_provider():
    request = ReviewRequest(
        provider="unknown",
        context=RepoContext(
            branch_name="feature/demo",
            current_commit="abc123def4567890",
            changed_files=(),
        ),
        findings=(),
    )

    with pytest.raises(ProviderReviewError, match="not connected yet"):
        request_provider_review(request, environment={})


def test_request_provider_fix_explains_unconnected_provider():
    request = ReviewRequest(
        provider="unknown",
        context=RepoContext(
            branch_name="feature/demo",
            current_commit="abc123def4567890",
            changed_files=(),
        ),
        findings=(),
    )

    with pytest.raises(ProviderReviewError, match="cannot create fix patches"):
        request_provider_fix(request, environment={})


def test_request_openai_review_requires_api_key():
    with pytest.raises(ProviderReviewError, match="OPENAI_API_KEY"):
        request_openai_review("Review this.", environment={})


def test_build_provider_prompt_includes_learned_rules():
    request = ReviewRequest(
        provider="openai",
        context=RepoContext(
            branch_name="feature/demo",
            current_commit="abc123def4567890",
            changed_files=("README.md",),
        ),
        findings=(),
        learned_rules=(
            LearnedRule(
                title="Keep README minimal",
                message="Keep README changes short and focused.",
            ),
        ),
    )

    prompt = build_provider_prompt(request)

    assert "Learned user/project rules:" in prompt
    assert "Keep README minimal: Keep README changes short and focused." in prompt


def test_build_provider_fix_prompt_includes_learned_rules():
    request = ReviewRequest(
        provider="openai",
        context=RepoContext(
            branch_name="feature/demo",
            current_commit="abc123def4567890",
            changed_files=("README.md",),
        ),
        findings=(),
        learned_rules=(
            LearnedRule(
                title="Keep README minimal",
                message="Keep README changes short and focused.",
            ),
        ),
    )

    prompt = build_provider_fix_prompt(request)

    assert "Learned user/project rules:" in prompt
    assert "Keep README minimal: Keep README changes short and focused." in prompt


def test_request_openai_account_review_uses_codex_without_api_key():
    captured = {}

    def fake_runner(arguments, **kwargs):
        captured["arguments"] = arguments
        captured["input"] = kwargs["input"]
        output_path = Path(arguments[arguments.index("--output-last-message") + 1])
        captured["output_path"] = output_path
        output_path.write_text("Account review.")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    review = request_openai_account_review(
        "Review this.",
        model="gpt-5",
        reasoning="high",
        environment={"OPENPANDORA_CODEX_COMMAND": "codex-test"},
        runner=fake_runner,
    )

    assert review.provider == "openai"
    assert review.model == "gpt-5"
    assert review.text == "Account review."
    assert captured["arguments"][:2] == ["codex-test", "exec"]
    assert "--ignore-user-config" in captured["arguments"]
    assert "--ignore-rules" in captured["arguments"]
    assert "--model" in captured["arguments"]
    assert "gpt-5" in captured["arguments"]
    assert 'model_reasoning_effort="high"' in captured["arguments"]
    assert captured["input"] == "Review this."
    assert not captured["output_path"].exists()


def test_request_openai_account_review_missing_codex_points_to_setup():
    def missing_runner(arguments, **kwargs):
        raise FileNotFoundError

    with pytest.raises(ProviderReviewError, match="openpandora setup"):
        request_openai_account_review(
            "Review this.",
            environment={"OPENPANDORA_CODEX_COMMAND": "missing-codex"},
            runner=missing_runner,
        )


def test_request_provider_review_uses_account_auth_when_oauth_is_selected(
    monkeypatch,
):
    captured = {}

    def fake_account_review(prompt, **kwargs):
        captured["prompt"] = prompt
        captured["kwargs"] = kwargs
        return SimpleNamespace(provider="openai", model=kwargs["model"], text="ok")

    monkeypatch.setattr(
        "openpandora.provider_clients.request_openai_account_review",
        fake_account_review,
    )
    request = ReviewRequest(
        provider="openai",
        auth_method="oauth",
        model="gpt-5",
        reasoning="medium",
        context=RepoContext(
            branch_name="feature/demo",
            current_commit="abc123def4567890",
            changed_files=(),
        ),
        findings=(),
    )

    review = request_provider_review(request, environment={})

    assert review.text == "ok"
    assert captured["kwargs"]["model"] == "gpt-5"
    assert captured["kwargs"]["reasoning"] == "medium"


def test_request_anthropic_review_requires_api_key():
    with pytest.raises(ProviderReviewError, match="ANTHROPIC_API_KEY"):
        request_anthropic_review("Review this.", environment={})


def test_request_openai_review_posts_prompt_without_printing_key():
    captured = {}

    def fake_opener(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["authorization"] = request.get_header("Authorization")
        captured["payload"] = json.loads(request.data.decode())
        return FakeResponse({"output_text": "Looks good."})

    review = request_openai_review(
        "Review this.",
        environment={"OPENAI_API_KEY": "secret-key", "OPENPANDORA_OPENAI_MODEL": "m"},
        opener=fake_opener,
    )

    assert review.provider == "openai"
    assert review.model == "m"
    assert review.text == "Looks good."
    assert captured["url"] == OPENAI_RESPONSES_URL
    assert captured["timeout"] == 60
    assert captured["authorization"] == "Bearer secret-key"
    assert captured["payload"]["model"] == "m"
    assert captured["payload"]["input"] == "Review this."
    assert captured["payload"]["store"] is False


def test_request_openai_review_uses_configured_model_and_reasoning():
    captured = {}

    def fake_opener(request, timeout):
        captured["payload"] = json.loads(request.data.decode())
        return FakeResponse({"output_text": "Looks good."})

    review = request_openai_review(
        "Review this.",
        model="gpt-5",
        reasoning="high",
        environment={
            "OPENAI_API_KEY": "secret-key",
            "OPENPANDORA_OPENAI_MODEL": "env-model",
        },
        opener=fake_opener,
    )

    assert review.model == "gpt-5"
    assert captured["payload"]["model"] == "gpt-5"
    assert captured["payload"]["reasoning"] == {"effort": "high"}


def test_request_openai_review_reads_nested_response_text():
    def fake_opener(request, timeout):
        return FakeResponse(
            {
                "output": [
                    {
                        "content": [
                            {
                                "type": "output_text",
                                "text": "Nested review.",
                            }
                        ]
                    }
                ]
            }
        )

    review = request_openai_review(
        "Review this.",
        environment={"OPENAI_API_KEY": "secret-key"},
        opener=fake_opener,
    )

    assert review.text == "Nested review."


def test_request_anthropic_review_posts_expected_payload():
    captured = {}

    def fake_opener(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["headers"] = {
            name.lower(): value for name, value in request.header_items()
        }
        captured["payload"] = json.loads(request.data.decode())
        return FakeResponse(
            {
                "content": [
                    {
                        "type": "text",
                        "text": "Anthropic review.",
                    }
                ]
            }
        )

    review = request_anthropic_review(
        "Review this.",
        environment={
            "ANTHROPIC_API_KEY": "secret-key",
            "OPENPANDORA_ANTHROPIC_MODEL": "claude-test",
        },
        opener=fake_opener,
    )

    assert review.provider == "anthropic"
    assert review.model == "claude-test"
    assert review.text == "Anthropic review."
    assert captured["url"] == ANTHROPIC_MESSAGES_URL
    assert captured["timeout"] == 60
    assert captured["headers"]["x-api-key"] == "secret-key"
    assert captured["headers"]["anthropic-version"] == "2023-06-01"
    assert captured["payload"]["model"] == "claude-test"
    assert captured["payload"]["messages"][0]["content"] == "Review this."
    assert captured["payload"]["max_tokens"] == 1200


def test_request_anthropic_review_uses_configured_model():
    captured = {}

    def fake_opener(request, timeout):
        captured["payload"] = json.loads(request.data.decode())
        return FakeResponse(
            {
                "content": [
                    {
                        "type": "text",
                        "text": "Anthropic review.",
                    }
                ]
            }
        )

    review = request_anthropic_review(
        "Review this.",
        model="claude-sonnet-4-5",
        environment={
            "ANTHROPIC_API_KEY": "secret-key",
            "OPENPANDORA_ANTHROPIC_MODEL": "env-model",
        },
        opener=fake_opener,
    )

    assert review.model == "claude-sonnet-4-5"
    assert captured["payload"]["model"] == "claude-sonnet-4-5"


def test_request_provider_fix_supports_anthropic():
    def fake_opener(request, timeout):
        return FakeResponse(
            {
                "content": [
                    {
                        "type": "text",
                        "text": "```diff\npatch\n```",
                    }
                ]
            }
        )

    request = ReviewRequest(
        provider="anthropic",
        context=RepoContext(
            branch_name="feature/demo",
            current_commit="abc123def4567890",
            changed_files=("README.md",),
        ),
        findings=(Finding(title="Fix docs", message="Docs need a fix."),),
        file_context=(FileContext("README.md", "# demo"),),
    )

    review = request_provider_fix(
        request,
        environment={"ANTHROPIC_API_KEY": "secret-key"},
        opener=fake_opener,
    )

    assert review.provider == "anthropic"
    assert "patch" in review.text


def test_build_provider_prompt_uses_evidence_without_raw_diff_lines():
    secret_value = "sk-" + "abcdefghijklmnopqrstuvwxyz123456"
    request = ReviewRequest(
        provider="openai",
        model="gpt-5",
        reasoning="high",
        context=RepoContext(
            branch_name="feature/demo",
            current_commit="abc123def4567890",
            changed_files=("config.py",),
        ),
        findings=(
            Finding(
                title="Possible secret in code",
                message="This added line looks like it may contain a secret.",
                severity=Severity.ERROR,
                file_path="config.py",
                line_number=2,
                suggestion="Load it from an environment variable.",
            ),
        ),
        command_results=(
            CommandResult(
                "Tests",
                "python -m pytest",
                1,
                f"OPENAI_API_KEY={secret_value}",
                "failed",
            ),
        ),
    )

    prompt = build_provider_prompt(request)

    assert "config.py" in prompt
    assert "Possible secret in code" in prompt
    assert "Requested model: gpt-5" in prompt
    assert "Reasoning level: high" in prompt
    assert "failed (1)" in prompt
    assert "[redacted sensitive-looking line]" in prompt
    assert secret_value not in prompt


def test_build_provider_prompt_includes_redacted_file_context():
    request = ReviewRequest(
        provider="openai",
        context=RepoContext(
            branch_name="feature/demo",
            current_commit="abc123def4567890",
            changed_files=("src/demo.py",),
        ),
        findings=(),
        file_context=(FileContext("src/demo.py", "print('hello')"),),
    )

    prompt = build_provider_prompt(request)

    assert "Redacted file context:" in prompt
    assert "File: src/demo.py" in prompt
    assert "print('hello')" in prompt


def test_build_provider_fix_prompt_requests_unified_diff():
    secret_value = "ghp_" + "a" * 32
    request = ReviewRequest(
        provider="openai",
        context=RepoContext(
            branch_name="feature/demo",
            current_commit="abc123def4567890",
            changed_files=("src/demo.py",),
            base_ref="main",
        ),
        findings=(
            Finding(
                title="Add a focused test",
                message="Source changed without a test.",
                suggestion="Add tests/test_demo.py.",
            ),
        ),
        file_context=(FileContext("src/demo.py", "print('hello')"),),
        command_results=(
            CommandResult(
                "Tests",
                "python -m pytest",
                1,
                "",
                f"token={secret_value}",
            ),
        ),
    )

    prompt = build_provider_fix_prompt(request)

    assert "unified diff" in prompt
    assert "NO_PATCH" in prompt
    assert "src/demo.py" in prompt
    assert "print('hello')" in prompt
    assert "Add tests/test_demo.py." in prompt
    assert "Failed commands:" in prompt
    assert "[redacted sensitive-looking line]" in prompt
    assert secret_value not in prompt


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return json.dumps(self.payload).encode()
