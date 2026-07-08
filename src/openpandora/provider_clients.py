"""Call selected AI providers without storing secrets."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import tempfile
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openpandora.review import ReviewRequest

OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_OPENAI_MODEL = "gpt-5-mini"
DEFAULT_ANTHROPIC_MODEL = "claude-opus-4-8"
ANTHROPIC_VERSION = "2023-06-01"
LOCAL_COMMAND_ENV_VAR = "OPENPANDORA_LOCAL_COMMAND"
CODEX_COMMAND_ENV_VAR = "OPENPANDORA_CODEX_COMMAND"


class ProviderReviewError(RuntimeError):
    """Raised when a selected provider cannot produce a review."""


@dataclass(frozen=True)
class ProviderReview:
    """Describe text returned by an AI provider."""

    provider: str
    model: str
    text: str


def request_provider_review(
    request: ReviewRequest,
    environment: Mapping[str, str] | None = None,
    opener: Callable[..., Any] | None = None,
) -> ProviderReview | None:
    """Ask the selected provider for review text when one is configured."""
    if request.provider == "local":
        return request_local_review(
            build_provider_prompt(request),
            environment=environment,
        )
    if request.provider == "openai":
        if request.auth_method == "oauth":
            return request_openai_account_review(
                build_provider_prompt(request),
                model=request.model,
                reasoning=request.reasoning,
                environment=environment,
            )
        return request_openai_review(
            build_provider_prompt(request),
            model=request.model,
            reasoning=request.reasoning,
            environment=environment,
            opener=opener,
        )
    if request.provider == "anthropic":
        return request_anthropic_review(
            build_provider_prompt(request),
            model=request.model,
            environment=environment,
            opener=opener,
        )
    raise ProviderReviewError(
        f"{request.provider} review is not connected yet. "
        "Use 'openpandora providers select local' or select openai."
    )


def request_provider_fix(
    request: ReviewRequest,
    environment: Mapping[str, str] | None = None,
    opener: Callable[..., Any] | None = None,
) -> ProviderReview:
    """Ask the selected provider for a small unified diff fix."""
    if request.provider == "openai":
        if request.auth_method == "oauth":
            return request_openai_account_review(
                build_provider_fix_prompt(request),
                model=request.model,
                reasoning=request.reasoning,
                environment=environment,
            )
        return request_openai_review(
            build_provider_fix_prompt(request),
            model=request.model,
            reasoning=request.reasoning,
            environment=environment,
            opener=opener,
        )
    if request.provider == "anthropic":
        return request_anthropic_review(
            build_provider_fix_prompt(request),
            model=request.model,
            environment=environment,
            opener=opener,
        )
    if request.provider == "local":
        return request_local_fix(
            build_provider_fix_prompt(request),
            environment=environment,
        )
    raise ProviderReviewError(
        f"{request.provider} cannot create fix patches yet. "
        "Select openai and set OPENAI_API_KEY."
    )


def request_openai_review(
    prompt: str,
    model: str | None = None,
    reasoning: str | None = None,
    environment: Mapping[str, str] | None = None,
    opener: Callable[..., Any] | None = None,
) -> ProviderReview:
    """Request a concise review from OpenAI's Responses API."""
    current_environment = os.environ if environment is None else environment
    api_key = current_environment.get("OPENAI_API_KEY")
    if not api_key:
        raise ProviderReviewError("OpenAI is selected, but OPENAI_API_KEY is not set.")

    selected_model = (
        model
        or current_environment.get("OPENPANDORA_OPENAI_MODEL")
        or DEFAULT_OPENAI_MODEL
    )
    payload_data: dict[str, Any] = {
        "model": selected_model,
        "input": prompt,
        "store": False,
    }
    if reasoning:
        payload_data["reasoning"] = {"effort": reasoning}
    payload = json.dumps(payload_data).encode()
    request = urllib.request.Request(
        OPENAI_RESPONSES_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    urlopen = urllib.request.urlopen if opener is None else opener

    try:
        with urlopen(request, timeout=60) as response:
            data = json.loads(response.read().decode())
    except urllib.error.HTTPError as error:
        detail = error.read().decode(errors="replace")
        raise ProviderReviewError(
            f"OpenAI review failed with HTTP {error.code}: {detail}"
        ) from error
    except urllib.error.URLError as error:
        raise ProviderReviewError(f"OpenAI review failed: {error.reason}") from error

    text = _extract_openai_text(data)
    if not text:
        raise ProviderReviewError("OpenAI returned no review text.")

    return ProviderReview(provider="openai", model=selected_model, text=text)


def request_openai_account_review(
    prompt: str,
    model: str | None = None,
    reasoning: str | None = None,
    environment: Mapping[str, str] | None = None,
    runner: Callable[..., Any] | None = None,
) -> ProviderReview:
    """Request review text through Codex's cached OpenAI account auth."""
    current_environment = os.environ if environment is None else environment
    command = current_environment.get(CODEX_COMMAND_ENV_VAR, "codex")
    selected_model = (
        model
        or current_environment.get("OPENPANDORA_OPENAI_MODEL")
        or DEFAULT_OPENAI_MODEL
    )
    run = subprocess.run if runner is None else runner

    with tempfile.NamedTemporaryFile(delete=False) as output_file:
        output_path = output_file.name

    arguments = [
        command,
        "exec",
        "--ephemeral",
        "--ignore-user-config",
        "--ignore-rules",
        "--sandbox",
        "read-only",
        "--ask-for-approval",
        "never",
        "--color",
        "never",
        "--output-last-message",
        output_path,
        "--model",
        selected_model,
    ]
    if reasoning:
        arguments.extend(["--config", f'model_reasoning_effort="{reasoning}"'])
    arguments.append("-")

    try:
        result = run(
            arguments,
            input=prompt,
            text=True,
            capture_output=True,
            check=False,
            timeout=300,
        )
    except FileNotFoundError as error:
        Path(output_path).unlink(missing_ok=True)
        raise ProviderReviewError(
            "OpenAI account auth needs the Codex CLI. Run 'openpandora setup "
            "--reset' and choose API key auth, or install Codex and sign in."
        ) from error
    except subprocess.TimeoutExpired as error:
        Path(output_path).unlink(missing_ok=True)
        raise ProviderReviewError("OpenAI account review timed out.") from error

    output_text = Path(output_path).read_text().strip()
    Path(output_path).unlink(missing_ok=True)

    if result.returncode != 0:
        reason = result.stderr.strip() or result.stdout.strip()
        raise ProviderReviewError(
            f"OpenAI account review failed with exit {result.returncode}: {reason}"
        )

    text = output_text or result.stdout.strip()
    if not text:
        raise ProviderReviewError("OpenAI account review returned no text.")

    return ProviderReview(provider="openai", model=selected_model, text=text)


def request_anthropic_review(
    prompt: str,
    model: str | None = None,
    environment: Mapping[str, str] | None = None,
    opener: Callable[..., Any] | None = None,
) -> ProviderReview:
    """Request a concise review from Anthropic's Messages API."""
    current_environment = os.environ if environment is None else environment
    api_key = current_environment.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ProviderReviewError(
            "Anthropic is selected, but ANTHROPIC_API_KEY is not set."
        )

    selected_model = (
        model
        or current_environment.get("OPENPANDORA_ANTHROPIC_MODEL")
        or DEFAULT_ANTHROPIC_MODEL
    )
    payload = json.dumps(
        {
            "model": selected_model,
            "max_tokens": 1200,
            "messages": [{"role": "user", "content": prompt}],
        }
    ).encode()
    request = urllib.request.Request(
        ANTHROPIC_MESSAGES_URL,
        data=payload,
        headers={
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
            "x-api-key": api_key,
        },
        method="POST",
    )
    urlopen = urllib.request.urlopen if opener is None else opener

    try:
        with urlopen(request, timeout=60) as response:
            data = json.loads(response.read().decode())
    except urllib.error.HTTPError as error:
        detail = error.read().decode(errors="replace")
        raise ProviderReviewError(
            f"Anthropic review failed with HTTP {error.code}: {detail}"
        ) from error
    except urllib.error.URLError as error:
        raise ProviderReviewError(f"Anthropic review failed: {error.reason}") from error

    text = _extract_anthropic_text(data)
    if not text:
        raise ProviderReviewError("Anthropic returned no review text.")

    return ProviderReview(provider="anthropic", model=selected_model, text=text)


def request_local_review(
    prompt: str,
    environment: Mapping[str, str] | None = None,
) -> ProviderReview | None:
    """Request a review from a local command when configured."""
    current_environment = os.environ if environment is None else environment
    command = current_environment.get(LOCAL_COMMAND_ENV_VAR)
    if not command:
        return None
    return _request_local_command(prompt, command)


def request_local_fix(
    prompt: str,
    environment: Mapping[str, str] | None = None,
) -> ProviderReview:
    """Request a patch from a local command when configured."""
    current_environment = os.environ if environment is None else environment
    command = current_environment.get(LOCAL_COMMAND_ENV_VAR)
    if not command:
        raise ProviderReviewError(
            "Local patch creation needs OPENPANDORA_LOCAL_COMMAND."
        )
    return _request_local_command(prompt, command)


def build_provider_prompt(request: ReviewRequest) -> str:
    """Build a provider prompt from findings without sending raw code."""
    lines = [
        "You are OpenPandora, a careful QA assistant for beginner developers.",
        "Review the evidence and suggest small, safe next steps.",
        "Do not invent files, do not ask for secrets, and keep the answer concise.",
        "",
        f"Branch: {request.context.branch_name}",
        f"Commit: {request.context.current_commit[:12]}",
    ]
    if request.model:
        lines.append(f"Requested model: {request.model}")
    if request.reasoning:
        lines.append(f"Reasoning level: {request.reasoning}")
    if request.context.base_ref:
        lines.append(f"Compared with: {request.context.base_ref}")

    lines.extend(["", "Changed files:"])
    if request.context.changed_files:
        lines.extend(f"- {file_path}" for file_path in request.context.changed_files)
    else:
        lines.append("- None")

    _append_file_context(lines, request)

    lines.extend(["", "OpenPandora findings:"])
    if request.findings:
        for finding in request.findings:
            location = f" at {finding.location}" if finding.location else ""
            lines.append(f"- [{finding.severity}] {finding.title}{location}")
            lines.append(f"  {finding.message}")
            if finding.suggestion:
                lines.append(f"  Suggestion: {finding.suggestion}")
    else:
        lines.append("- None")

    lines.extend(["", "Command results:"])
    if request.command_results:
        for result in request.command_results:
            status = "passed" if result.passed else f"failed ({result.return_code})"
            lines.append(f"- {result.name}: {status} - {result.command}")
            if not result.passed:
                output = "\n".join(
                    part.strip() for part in (result.stdout, result.stderr) if part
                )
                if output:
                    lines.append(f"  Output: {output[:1000]}")
    else:
        lines.append("- Not run")

    lines.extend(["", "Return sections: Summary, Suggested next steps, Tests."])
    return "\n".join(lines)


def build_provider_fix_prompt(request: ReviewRequest) -> str:
    """Build a provider prompt for a small patch proposal."""
    lines = [
        "You are OpenPandora, a careful QA assistant for beginner developers.",
        "Create the smallest safe fix as a unified diff.",
        "Return only one fenced diff block. Do not include prose outside the diff.",
        "If you cannot make a safe exact patch, return NO_PATCH.",
        "",
        f"Branch: {request.context.branch_name}",
        f"Commit: {request.context.current_commit[:12]}",
    ]
    if request.model:
        lines.append(f"Requested model: {request.model}")
    if request.reasoning:
        lines.append(f"Reasoning level: {request.reasoning}")
    if request.context.base_ref:
        lines.append(f"Compared with: {request.context.base_ref}")

    lines.extend(["", "Changed files:"])
    if request.context.changed_files:
        lines.extend(f"- {file_path}" for file_path in request.context.changed_files)
    else:
        lines.append("- None")

    lines.extend(["", "Findings to fix:"])
    if request.findings:
        for finding in request.findings:
            location = f" at {finding.location}" if finding.location else ""
            lines.append(f"- [{finding.severity}] {finding.title}{location}")
            lines.append(f"  {finding.message}")
            if finding.suggestion:
                lines.append(f"  Suggestion: {finding.suggestion}")
    else:
        lines.append("- None")

    _append_file_context(lines, request)

    lines.extend(["", "Failed commands:"])
    failed_results = tuple(
        result for result in request.command_results if not result.passed
    )
    if failed_results:
        for result in failed_results:
            lines.append(f"- {result.name}: {result.command}")
            output = "\n".join(
                part.strip() for part in (result.stdout, result.stderr) if part
            )
            if output:
                lines.append(f"  Output: {output[:2000]}")
    else:
        lines.append("- None")

    return "\n".join(lines)


def _append_file_context(lines: list[str], request: ReviewRequest) -> None:
    lines.extend(["", "Redacted file context:"])
    if not request.file_context:
        lines.append("- None")
        return

    for file_context in request.file_context:
        suffix = " (truncated)" if file_context.truncated else ""
        lines.append(f"File: {file_context.file_path}{suffix}")
        lines.append("```")
        lines.append(file_context.content)
        lines.append("```")


def _extract_openai_text(data: Mapping[str, Any]) -> str:
    output_text = data.get("output_text")
    if isinstance(output_text, str):
        return output_text.strip()

    text_parts: list[str] = []
    for item in data.get("output", []):
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if not isinstance(content, dict):
                continue
            if content.get("type") == "output_text" and isinstance(
                content.get("text"), str
            ):
                text_parts.append(content["text"])
    return "\n".join(text_parts).strip()


def _extract_anthropic_text(data: Mapping[str, Any]) -> str:
    text_parts: list[str] = []
    for content in data.get("content", []):
        if not isinstance(content, dict):
            continue
        if content.get("type") == "text" and isinstance(content.get("text"), str):
            text_parts.append(content["text"])
    return "\n".join(text_parts).strip()


def _request_local_command(prompt: str, command: str) -> ProviderReview:
    arguments = shlex.split(command)
    if not arguments:
        raise ProviderReviewError("OPENPANDORA_LOCAL_COMMAND is empty.")

    try:
        result = subprocess.run(
            arguments,
            input=prompt,
            text=True,
            capture_output=True,
            check=False,
            timeout=120,
        )
    except FileNotFoundError as error:
        raise ProviderReviewError(
            f"Local provider command not found: {arguments[0]}"
        ) from error
    except subprocess.TimeoutExpired as error:
        raise ProviderReviewError("Local provider command timed out.") from error

    if result.returncode != 0:
        reason = result.stderr.strip() or result.stdout.strip()
        raise ProviderReviewError(
            f"Local provider command failed with exit {result.returncode}: {reason}"
        )

    text = result.stdout.strip()
    if not text:
        raise ProviderReviewError("Local provider command returned no text.")

    return ProviderReview(provider="local", model=command, text=text)
