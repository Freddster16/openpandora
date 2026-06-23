# OpenPandora

OpenPandora is a QA agent for code changes.

It gives calm, readable feedback before code is pushed. On pushed branches, its
GitHub workflow can review the branch, ask a selected provider for a safe patch,
and open a pull request with the proposed fix when it finds a clear issue.

## What Works Today

OpenPandora currently includes:

- a Python package for Python 3.11 or newer
- an `openpandora check` command for local commit checks
- an `openpandora test` command for configured project test/lint commands
- an `openpandora review` command that summarizes checks and command results
- an `openpandora improve --dry-run` command that explains safe next steps
- a GitHub Action that runs the local check on pushed branches except `main`
- deterministic checks for missing tests and possible secrets
- JSON output for automation
- user-editable learned rules loaded from `.openpandora/rules.json`
- user-editable config loaded from `.openpandora/config.json`
- local review without any API key
- optional OpenAI review when `OPENAI_API_KEY` is set
- optional Anthropic review when `ANTHROPIC_API_KEY` is set
- optional local/self-hosted review through `OPENPANDORA_LOCAL_COMMAND`
- safe provider patch application with `openpandora improve --apply`
- fix branch and pull request creation with `openpandora fix-pr --create`
- a small release zipapp builder
- a readable curl installer script

Automatic fix PR creation is wired into the GitHub Action when checks fail and
a selected provider can return a valid patch.

## Install For Development

From the project folder:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

To install only the app without development tools:

```bash
python -m pip install -e .
```

For a released version, users can install with:

```bash
curl -fsSL https://raw.githubusercontent.com/Freddster16/openpandora/main/install.sh | sh
```

The installer downloads the latest `openpandora.pyz` release asset, checks for
Python 3.11 or newer, and writes a small wrapper at:

```text
~/.local/bin/openpandora
```

The downloaded app is stored under `~/.local/share/openpandora/`.

To build that release asset:

```bash
python scripts/build_release.py
```

To publish a release, push a version tag:

```bash
git tag v0.1.0
git push origin v0.1.0
```

The release workflow runs tests, builds `dist/openpandora.pyz`, verifies it, and
uploads it to the GitHub release. The installer downloads that asset.

## Check Your Latest Commit

Run:

```bash
openpandora check
```

OpenPandora reads the current branch, the current commit, and the files changed
in that commit. If everything looks okay, it prints:

```text
OpenPandora check
Branch: feature/demo
Commit: abc123def456
Changed files: 1
No issues found.
```

If it finds something, it explains the issue and suggests a next step:

```text
Found 1 issue(s):
- [warning] Add a focused test
  Source code changed, but this commit does not include a matching test change.
  Suggestion: Add or update a pytest test for: src/openpandora/cli.py
```

For scripts and automation, use JSON output:

```bash
openpandora check --json
```

To compare a branch against another ref, such as `main`, run:

```bash
openpandora check --since main
```

To prepare a GitHub-ready QA summary without opening a pull request:

```bash
openpandora pr-body --since main
```

To preview a pull request without opening one:

```bash
openpandora pr-create --since main
```

This prints the repository, base branch, head branch, and title. It does not
contact GitHub unless `--create` is provided. Real PR creation also requires
`GITHUB_TOKEN`.

## Run Project Tests

Run:

```bash
openpandora test
```

OpenPandora loads `.openpandora/config.json` and runs the configured test and
lint commands. If no config exists yet, it uses:

```text
python -m pytest
ruff check .
```

When OpenPandora is installed inside a virtual environment, the `python`
command is resolved to the same Python executable running OpenPandora. This
helps the command work even on machines where plain `python` is not on PATH.

## Review And Improve

To review the branch against `main`, run:

```bash
openpandora review --since main
```

The review includes:

- deterministic OpenPandora findings
- configured test/lint command results
- loaded learned rules
- small redacted context from changed text files
- optional provider review text
- suggested next steps

If `.openpandora/config.json` selects `openai` and `OPENAI_API_KEY` is set,
OpenPandora sends a concise review prompt to OpenAI. The prompt includes changed
file names, OpenPandora findings, command results, and limited redacted file
context so it can propose exact patches.

If the config selects `anthropic`, OpenPandora uses `ANTHROPIC_API_KEY`.
If the config selects `local`, set `OPENPANDORA_LOCAL_COMMAND` to a command that
reads the prompt from stdin and writes review or patch text to stdout.

To see what OpenPandora would improve without editing files:

```bash
openpandora improve --dry-run --since main
```

This command never changes files. It prints a safe improvement plan first.

To apply a provider patch to the current worktree:

```bash
openpandora improve --apply --since main
```

OpenPandora only applies the patch after Git confirms the unified diff can be
applied. It then reruns the configured project commands.

To preview a fix pull request:

```bash
openpandora fix-pr --since main
```

To actually create a fix branch, push it, and open a PR:

```bash
openpandora fix-pr --since main --create
```

This requires a clean worktree, `GITHUB_TOKEN`, and a selected provider that can
return a valid unified diff. Manual PR creation is also available through
`openpandora pr-create --create`.

The JSON output includes:

- status
- branch
- commit
- base ref, when `--since` is used
- changed files
- learned rules
- findings

## Current Checks

OpenPandora currently checks for:

- source changes under `src/` without a matching change under `tests/`
- secret-looking strings in added lines, including API keys, tokens, passwords,
  and secrets

The checks are intentionally simple and local. They are meant to catch obvious
mistakes while keeping the feedback clear and actionable.

## Learned Rules

OpenPandora can load user-editable learned rules from:

```text
.openpandora/rules.json
```

Example:

```json
{
  "rules": [
    {
      "title": "Prefer focused tests",
      "message": "Add a small test with each behavior change.",
      "severity": "warning"
    }
  ]
}
```

Today, learned rules are loaded and shown in `openpandora check` output. They
are not auto-applied or silently enforced. This keeps the user in control while
the learning system grows.

When OpenPandora finds issues or creates a fix PR, it records a readable history
event in:

```text
.openpandora/history.jsonl
```

To view recent history:

```bash
openpandora history
```

History is not the same as a learned rule. OpenPandora records what happened,
but it does not silently add or enforce new learned rules.

To create a starter rules file:

```bash
openpandora init
```

`openpandora init` also creates `.openpandora/config.json` when it is missing:

```json
{
  "base_ref": "main",
  "commands": {
    "test": "python -m pytest",
    "lint": "ruff check ."
  }
}
```

## Provider Setup

OpenPandora lets users choose an AI provider while keeping keys outside the
repo:

```bash
openpandora providers
```

Current provider options:

- OpenAI with `OPENAI_API_KEY` for provider review
- Anthropic with `ANTHROPIC_API_KEY` for provider review
- Local or self-hosted review with `OPENPANDORA_LOCAL_COMMAND`

The command checks whether an environment variable exists, but it never prints
the secret value.

To save a provider choice without storing any API keys:

```bash
openpandora providers select openai
```

For CI, users can avoid committing a provider choice by setting:

```text
OPENPANDORA_PROVIDER=openai
```

Supported values are `openai`, `anthropic`, and `local`.

## GitHub Action

The workflow at `.github/workflows/openpandora.yml` runs on pushes to branches
other than `main`.

It currently:

- checks out the code
- installs Python 3.11
- installs OpenPandora with development tools
- runs `openpandora check --since main`
- runs `openpandora test`
- tries `openpandora fix-pr --since main --create` if either command fails

The fix PR step needs `GITHUB_TOKEN` plus a configured provider key, such as
`OPENAI_API_KEY` or `ANTHROPIC_API_KEY`. It also needs
`.openpandora/config.json` or `OPENPANDORA_PROVIDER` to select a provider that
can create patches.
For local or self-hosted models, set `OPENPANDORA_LOCAL_COMMAND` instead of a
provider key.

In GitHub Actions, set `OPENPANDORA_PROVIDER` and `OPENPANDORA_LOCAL_COMMAND`
as repository variables, and provider keys as repository secrets.

The workflow at `.github/workflows/release.yml` runs when a `v*` tag is pushed
and publishes the `openpandora.pyz` asset used by the installer.

## Development Commands

Run the test suite:

```bash
pytest
```

Check formatting and lint rules:

```bash
ruff check .
ruff format .
```

Build the release zipapp:

```bash
python scripts/build_release.py
```

## Project Map

- `src/openpandora/cli.py` handles the command line interface.
- `src/openpandora/command_runner.py` runs configured local commands.
- `src/openpandora/project_config.py` loads editable project settings.
- `src/openpandora/provider_clients.py` calls selected AI providers.
- `src/openpandora/file_context.py` collects limited redacted file context.
- `src/openpandora/patches.py` extracts and applies provider unified diffs.
- `src/openpandora/git_changes.py` creates fix branches and commits.
- `src/openpandora/github_pull_requests.py` prepares and creates GitHub PRs.
- `src/openpandora/git_context.py` reads branch, commit, and changed files.
- `src/openpandora/checks.py` contains deterministic local QA checks.
- `src/openpandora/findings.py` defines QA result objects.
- `src/openpandora/learned_rules.py` loads readable user-controlled rules.
- `src/openpandora/history.py` records findings and fixes as JSON Lines.
- `src/openpandora/review.py` builds local review reports.
- `src/openpandora/improve.py` builds dry-run improvement plans.
- `src/openpandora/providers.py` describes provider auth options.
- `src/openpandora/project_init.py` creates starter project config files.
- `src/openpandora/pull_requests.py` prepares GitHub-ready QA text.
- `scripts/build_release.py` builds the release zipapp.
- `install.sh` downloads the latest release zipapp onto PATH.
- `.github/workflows/release.yml` publishes release zipapps on version tags.
- `tests/` mirrors the source files with focused pytest coverage.
