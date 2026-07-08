# OpenPandora

OpenPandora is a sleeping QA agent for Git projects. Install it once, choose
OpenAI auth, model, and reasoning level, then let Git wake it on commits or
pushes.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/Freddster16/openpandora/main/install.sh | sh
```

The installer downloads the latest `openpandora.pyz`, installs the
`openpandora` command to `~/.local/bin`, and starts setup in interactive
terminals.

If the command is not found after install, add this to your shell:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

## Setup

```bash
openpandora setup
```

Setup asks for:

- OpenAI account sign-in or `OPENAI_API_KEY`
- OpenAI model
- reasoning level
- whether wake mode should create fix PRs

OpenPandora saves only non-secret preferences and remembers them after computer
restarts. To change the model, reasoning level, or auth method later:

```bash
openpandora setup
```

## Sleep Mode

Run this inside a Git repo:

```bash
openpandora sleep --create-pr
```

OpenPandora installs repo-local Git hooks. It stays quiet until a commit or push
wakes it. If it finds a safe fix, it creates a branch and GitHub PR. If it finds
nothing, it prints:

```text
OpenPandora wake: nothing found.
```

PR creation needs `GITHUB_TOKEN`. API key auth also needs `OPENAI_API_KEY`.
OpenAI account auth uses your saved Codex ChatGPT login.

## Useful Commands

```bash
openpandora check
openpandora test
openpandora review --since main
openpandora improve --dry-run --since main
openpandora fix-pr --since main --create
```

## Develop

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
pytest
ruff check .
```
