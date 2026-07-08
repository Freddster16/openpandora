import json
import subprocess

import pytest

from openpandora.github_pull_requests import (
    GITHUB_API_URL,
    GitHubPullRequestError,
    GitHubRepo,
    build_pull_request_plan,
    create_pull_request,
    parse_github_remote,
)


@pytest.mark.parametrize(
    ("remote_url", "repo"),
    [
        (
            "git@github.com:Freddster16/openpandora.git",
            GitHubRepo("Freddster16", "openpandora"),
        ),
        (
            "https://github.com/Freddster16/openpandora.git",
            GitHubRepo("Freddster16", "openpandora"),
        ),
        (
            "ssh://git@github.com/Freddster16/openpandora.git",
            GitHubRepo("Freddster16", "openpandora"),
        ),
        (
            "https://github.com/Freddster16/openpandora.tool.git",
            GitHubRepo("Freddster16", "openpandora.tool"),
        ),
    ],
)
def test_parse_github_remote_accepts_common_formats(remote_url, repo):
    assert parse_github_remote(remote_url) == repo


def test_parse_github_remote_rejects_non_github_remote():
    with pytest.raises(GitHubPullRequestError, match="GitHub remotes"):
        parse_github_remote("git@example.com:owner/repo.git")


def test_parse_github_remote_rejects_api_path_characters():
    with pytest.raises(GitHubPullRequestError, match="GitHub remotes"):
        parse_github_remote("https://github.com/owner/repo?bad=true.git")


def test_build_pull_request_plan_requires_title():
    with pytest.raises(GitHubPullRequestError, match="title"):
        build_pull_request_plan(
            repo=GitHubRepo("owner", "repo"),
            title="",
            body="body",
            head="feature/demo",
            base="main",
        )


def test_create_pull_request_requires_token():
    plan = build_pull_request_plan(
        repo=GitHubRepo("owner", "repo"),
        title="OpenPandora QA",
        body="body",
        head="feature/demo",
        base="main",
    )

    with pytest.raises(GitHubPullRequestError, match="GITHUB_TOKEN"):
        create_pull_request(plan, environment={})


def test_create_pull_request_posts_expected_payload():
    captured = {}
    plan = build_pull_request_plan(
        repo=GitHubRepo("owner", "repo"),
        title="OpenPandora QA",
        body="body",
        head="feature/demo",
        base="main",
    )

    def fake_opener(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["authorization"] = request.get_header("Authorization")
        captured["payload"] = json.loads(request.data.decode())
        return FakeResponse(
            {"html_url": "https://github.com/owner/repo/pull/1", "number": 1}
        )

    result = create_pull_request(
        plan,
        environment={"GITHUB_TOKEN": "token"},
        opener=fake_opener,
    )

    assert result.url == "https://github.com/owner/repo/pull/1"
    assert result.number == 1
    assert captured["url"] == f"{GITHUB_API_URL}/repos/owner/repo/pulls"
    assert captured["timeout"] == 60
    assert captured["authorization"] == "Bearer token"
    assert captured["payload"]["title"] == "OpenPandora QA"
    assert captured["payload"]["head"] == "feature/demo"
    assert captured["payload"]["base"] == "main"
    assert captured["payload"]["draft"] is False


def test_create_pull_request_falls_back_to_authenticated_gh_ready_for_review():
    captured = {}
    plan = build_pull_request_plan(
        repo=GitHubRepo("owner", "repo"),
        title="OpenPandora QA",
        body="body",
        head="openpandora/fix-feature-demo",
        base="feature/demo",
    )

    def fake_runner(arguments, **kwargs):
        captured["arguments"] = arguments
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(
            arguments,
            0,
            stdout="https://github.com/owner/repo/pull/2\n",
            stderr="",
        )

    result = create_pull_request(plan, environment={}, runner=fake_runner)

    assert result.url == "https://github.com/owner/repo/pull/2"
    assert result.number == 2
    assert captured["arguments"] == [
        "gh",
        "pr",
        "create",
        "--repo",
        "owner/repo",
        "--title",
        "OpenPandora QA",
        "--body",
        "body",
        "--head",
        "openpandora/fix-feature-demo",
        "--base",
        "feature/demo",
    ]
    assert captured["kwargs"]["env"] == {}


def test_create_pull_request_can_explicitly_create_draft_with_gh():
    captured = {}
    plan = build_pull_request_plan(
        repo=GitHubRepo("owner", "repo"),
        title="OpenPandora QA",
        body="body",
        head="openpandora/fix-feature-demo",
        base="feature/demo",
        draft=True,
    )

    def fake_runner(arguments, **kwargs):
        captured["arguments"] = arguments
        return subprocess.CompletedProcess(
            arguments,
            0,
            stdout="https://github.com/owner/repo/pull/3\n",
            stderr="",
        )

    result = create_pull_request(plan, environment={}, runner=fake_runner)

    assert result.url == "https://github.com/owner/repo/pull/3"
    assert "--draft" in captured["arguments"]


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return json.dumps(self.payload).encode()
