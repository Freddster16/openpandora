# OpenPandora

OpenPandora is a beginner-friendly QA agent for code commits.

It gives calm, readable feedback before code is pushed, and it is being built
toward a GitHub workflow that can review a pushed commit and open a pull request
with a safe proposed fix when it finds a clear issue.

## What Works Today

OpenPandora currently includes:

- a Python package for Python 3.11 or newer
- an `openpandora check` command for local commit checks
- a GitHub Action that runs the local check on pushed branches except `main`
- deterministic checks for missing tests and possible secrets
- JSON output for automation
- user-editable learned rules loaded from `.openpandora/rules.json`
- provider setup status for planned AI review integrations

Automatic AI review and pull request creation are planned, but not active yet.

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

A small curl-based installer is planned for releases, but this repository does
not ship one yet.

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

The JSON output includes:

- status
- branch
- commit
- changed files
- learned rules
- findings

## Current Checks

OpenPandora currently checks for:

- source changes under `src/` without a matching change under `tests/`
- secret-looking strings, including API keys, tokens, passwords, and secrets

The checks are intentionally simple and local. They are meant to catch obvious
mistakes while staying understandable for new developers.

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

## Provider Setup

OpenPandora is designed so users can choose an AI provider later. The current
version does not call any provider yet, but it can show planned auth options:

```bash
openpandora providers
```

Current provider options:

- OpenAI with `OPENAI_API_KEY`
- Anthropic with `ANTHROPIC_API_KEY`
- Local or self-hosted review, reserved for later

The command checks whether an environment variable exists, but it never prints
the secret value.

## GitHub Action

The workflow at `.github/workflows/openpandora.yml` runs on pushes to branches
other than `main`.

It currently:

- checks out the code
- installs Python 3.11
- installs OpenPandora with development tools
- runs `openpandora check`

Future versions will add provider selection, AI review, and pull request
creation.

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

## Project Map

- `src/openpandora/cli.py` handles the command line interface.
- `src/openpandora/git_context.py` reads branch, commit, and changed files.
- `src/openpandora/checks.py` contains deterministic local QA checks.
- `src/openpandora/findings.py` defines QA result objects.
- `src/openpandora/learned_rules.py` loads readable user-controlled rules.
- `src/openpandora/providers.py` describes provider auth options.
- `tests/` mirrors the source files with focused pytest coverage.

## Roadmap

Next planned steps:

- package release builds
- a beginner-readable curl installer
- AI provider selection
- AI-assisted review of pushed commits
- pull request creation with proposed fixes
- clearer self-improvement workflows for learned rules
