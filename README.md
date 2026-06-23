# OpenPandora

OpenPandora is a beginner-friendly QA agent for code commits.

The goal is simple: before a developer pushes code, they can run one local
command and get calm, readable feedback. In GitHub Actions, OpenPandora will
eventually inspect pushed commits and open a pull request with a safe proposed
fix when it finds a clear issue.

This project is still early. Today it has a working Python package, a local
`openpandora check` command, Git context collection, a small QA finding model,
and a readable learned-rules loader.

## Install for Development

OpenPandora needs Python 3.11 or newer.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Run

```bash
openpandora check
```

The current command reads the branch, current commit, and files changed in the
current commit. The first check set is intentionally empty, so a healthy run
prints:

```text
No issues found.
```

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

Rules are only loaded right now. They are not auto-applied or silently enforced.

## GitHub Action

The workflow in `.github/workflows/openpandora.yml` runs on pushes to branches
other than `main`. It installs the package and runs:

```bash
openpandora check
```

Future versions will add provider selection, AI review, and pull request
creation.

## Test

```bash
pytest
ruff check .
ruff format .
```

## Current Architecture

- `src/openpandora/cli.py` handles the command line interface.
- `src/openpandora/git_context.py` reads branch, commit, and changed files.
- `src/openpandora/checks.py` is the home for deterministic local QA checks.
- `src/openpandora/findings.py` defines the shape of QA results.
- `src/openpandora/learned_rules.py` loads readable user-controlled rules.
- `tests/` mirrors the source files with focused pytest coverage.
