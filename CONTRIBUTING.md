# Contributing

## Setup

```bash
git clone https://github.com/MCamner/mq-agent.git
cd mq-agent
uv pip install -e ".[dev]"
```

Verify everything works:

```bash
pytest tests/ -v
mq-agent doctor
```

## Branch and PR flow

`main` is protected. Do not plan work around pushing directly to `main`.

```bash
git switch -c feat/my-change
pytest tests/ -v
git push -u origin feat/my-change
gh pr create --base main --head feat/my-change
```

Keep release-prep changes on a branch too. Tag releases only after the release
PR has merged and CI is green on `main`.

## Running tests

```bash
pytest tests/ -v
```

Tests do not require `OPENAI_API_KEY` — the 26 unit tests mock all external calls.

## Linting and type checking

```bash
ruff check mq_agent/
mypy mq_agent/ --ignore-missing-imports
```

## Rules

- No secrets in commits (no `.env`, no API keys, no tokens)
- Add tests for every new tool registered in `TOOL_REGISTRY`
- Keep commands safe by default — `suggest` mode unless `--approve` is passed
- Prefer `--dry-run` behavior for any new command that writes or executes
- New tools must be added to `SAFE_TOOLS` in `safety.py` if they are read-only
- Destructive tools must trigger the `DESTRUCTIVE_PATTERNS` check

## Adding a new tool

1. Implement in `mq_agent/tools/your_tool.py`
2. Register in `mq_agent/tools/__init__.py` `TOOL_REGISTRY`
3. If read-only, add to `SAFE_TOOLS` in `mq_agent/core/safety.py`
4. Write at least one test in `tests/test_tools.py`

## Adding a new agent

1. Create `mq_agent/agents/your_agent.py`
2. Use `Planner`, `Executor`, `Verifier` from `mq_agent.core`
3. Export from `mq_agent/agents/__init__.py`
4. Wire a CLI command in `mq_agent/main.py`

## Commit style

```
feat: add X
fix: correct Y
docs: update Z
refactor: simplify W
test: cover V
```
