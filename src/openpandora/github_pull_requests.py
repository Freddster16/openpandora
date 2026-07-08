"""Prepare and create GitHub pull requests for OpenPandora fixes."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

GITHUB_API_VERSION = "2022-11-28"
GITHUB_API_URL = "https://api.github.com"
GITHUB_NAME = r"[A-Za-z0-9][A-Za-z0-9_.-]*"
GITHUB_REMOTE_PATTERN = re.compile(
    r"(?:git@github\.com:|https://github\.com/|ssh://git@github\.com/)"
    rf"(?P<owner>{GITHUB_NAME})/(?P<repo>{GITHUB_NAME})/?$"
)


class GitHubPullRequestError(RuntimeError):
    """Raised when OpenPandora cannot prepare or create a GitHub PR."""


@dataclass(frozen=True)
class GitHubRepo:
    """Describe a GitHub repository parsed from a remote URL."""

    owner: str
    name: str


@dataclass(frozen=True)
class PullRequestPlan:
    """Describe the PR OpenPandora intends to create."""

    repo: GitHubRepo
    title: str
    body: str
    head: str
    base: str
    draft: bool = False


@dataclass(frozen=True)
class PullRequestResult:
    """Describe a pull request created on GitHub."""

    url: str
    number: int | None = None


def detect_github_repo(repo_path: str | Path = ".") -> GitHubRepo:
    """Read origin and return the GitHub repo it points to."""
    result = subprocess.run(
        ["git", "config", "--get", "remote.origin.url"],
        cwd=Path(repo_path),
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise GitHubPullRequestError("Could not read git remote 'origin'.")

    return parse_github_remote(result.stdout.strip())


def parse_github_remote(remote_url: str) -> GitHubRepo:
    """Parse common GitHub remote URL formats."""
    match = GITHUB_REMOTE_PATTERN.match(remote_url)
    if not match:
        raise GitHubPullRequestError(
            "OpenPandora only knows how to create PRs for GitHub remotes."
        )
    repo_name = match.group("repo")
    if repo_name.endswith(".git"):
        repo_name = repo_name.removesuffix(".git")
    return GitHubRepo(owner=match.group("owner"), name=repo_name)


def build_pull_request_plan(
    *,
    repo: GitHubRepo,
    title: str,
    body: str,
    head: str,
    base: str,
    draft: bool = False,
) -> PullRequestPlan:
    """Prepare PR fields before making a network request."""
    if not title.strip():
        raise GitHubPullRequestError("Pull request title is required.")
    if not head.strip():
        raise GitHubPullRequestError("Pull request head branch is required.")
    if not base.strip():
        raise GitHubPullRequestError("Pull request base branch is required.")
    return PullRequestPlan(
        repo=repo,
        title=title,
        body=body,
        head=head,
        base=base,
        draft=draft,
    )


def create_pull_request(
    plan: PullRequestPlan,
    environment: Mapping[str, str] | None = None,
    opener: Callable[..., Any] | None = None,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> PullRequestResult:
    """Create a GitHub pull request using GITHUB_TOKEN or an authenticated gh CLI."""
    current_environment = os.environ if environment is None else environment
    token = current_environment.get("GITHUB_TOKEN")
    if not token:
        return _create_pull_request_with_gh(plan, current_environment, runner)

    payload = json.dumps(
        {
            "title": plan.title,
            "body": plan.body,
            "head": plan.head,
            "base": plan.base,
            "draft": plan.draft,
        }
    ).encode()
    request = urllib.request.Request(
        f"{GITHUB_API_URL}/repos/{plan.repo.owner}/{plan.repo.name}/pulls",
        data=payload,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
        },
        method="POST",
    )
    urlopen = urllib.request.urlopen if opener is None else opener

    try:
        with urlopen(request, timeout=60) as response:
            data = json.loads(response.read().decode())
    except urllib.error.HTTPError as error:
        detail = error.read().decode(errors="replace")
        raise GitHubPullRequestError(
            f"GitHub PR creation failed with HTTP {error.code}: {detail}"
        ) from error
    except urllib.error.URLError as error:
        raise GitHubPullRequestError(
            f"GitHub PR creation failed: {error.reason}"
        ) from error

    url = data.get("html_url")
    if not isinstance(url, str):
        raise GitHubPullRequestError("GitHub did not return a pull request URL.")

    number = data.get("number")
    return PullRequestResult(
        url=url,
        number=number if isinstance(number, int) else None,
    )


def _create_pull_request_with_gh(
    plan: PullRequestPlan,
    environment: Mapping[str, str],
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> PullRequestResult:
    gh_runner = subprocess.run if runner is None else runner
    if runner is None and not shutil.which("gh", path=environment.get("PATH", "")):
        raise GitHubPullRequestError(
            "GITHUB_TOKEN or an authenticated GitHub CLI is required to create a PR."
        )

    arguments = [
        "gh",
        "pr",
        "create",
        "--repo",
        f"{plan.repo.owner}/{plan.repo.name}",
        "--title",
        plan.title,
        "--body",
        plan.body,
        "--head",
        plan.head,
        "--base",
        plan.base,
    ]
    if plan.draft:
        arguments.append("--draft")

    try:
        result = gh_runner(
            arguments,
            text=True,
            capture_output=True,
            check=False,
            timeout=60,
            env=dict(environment),
        )
    except FileNotFoundError as error:
        raise GitHubPullRequestError(
            "GITHUB_TOKEN or an authenticated GitHub CLI is required to create a PR."
        ) from error
    except subprocess.TimeoutExpired as error:
        raise GitHubPullRequestError("GitHub PR creation with gh timed out.") from error

    if result.returncode != 0:
        reason = result.stderr.strip() or result.stdout.strip() or "unknown gh error"
        raise GitHubPullRequestError(f"GitHub PR creation with gh failed: {reason}")

    url = _extract_pull_request_url(result.stdout)
    if url is None:
        raise GitHubPullRequestError("GitHub CLI did not return a pull request URL.")

    return PullRequestResult(url=url, number=_extract_pull_request_number(url))


def _extract_pull_request_url(output: str) -> str | None:
    match = re.search(r"https://github\.com/[^\s]+/[^\s]+/pull/\d+", output)
    return match.group(0) if match else None


def _extract_pull_request_number(url: str) -> int | None:
    _, separator, number_text = url.rpartition("/pull/")
    if not separator or not number_text.isdigit():
        return None
    return int(number_text)
