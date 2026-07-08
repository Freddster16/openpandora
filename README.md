# OpenPandora

OpenPandora is a sleeping QA agent for Git projects. Install it once, choose
OpenAI auth, model, and reasoning level, then Git can wake it from any repo on
your computer.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/Freddster16/openpandora/main/install.sh | sh
```

The installer downloads the latest `openpandora.pyz`, installs the
`openpandora` command to `~/.local/bin`, starts setup, and installs
computer-wide Git wake hooks.

Check the install with `openpandora --version`.

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

Use Up/Down or `j`/`k` to move through setup choices, then press Enter or Space.

If you choose OpenAI account sign-in and Codex CLI is missing, setup installs it
first, then continues sign-in.

OpenPandora saves only non-secret preferences and remembers them after computer
restarts. To change the model, reasoning level, or auth method later:

```bash
openpandora setup
```

## Asleep By Default

Setup installs one global Git hooks path for this computer. OpenPandora does not
run in the background; it stays quiet until a commit or push from any repo wakes
it. If it finds a safe fix, it creates a branch and GitHub PR. If it finds
nothing, it prints:

```text
OpenPandora wake: nothing found.
```

PR creation needs `GITHUB_TOKEN`. API key auth also needs `OPENAI_API_KEY`.
OpenAI account auth uses your saved Codex ChatGPT login.

## Learning

OpenPandora keeps local history and learned rules in `.openpandora/`. Repeated
findings become editable rules, and you can teach preferences directly:

```bash
openpandora learn "Keep README changes short and focused."
```

## Useful Commands

```bash
openpandora check
openpandora test
openpandora review --since main
openpandora improve --dry-run --since main
openpandora fix-pr --since main --create
openpandora learn "Prefer small, focused changes."
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
