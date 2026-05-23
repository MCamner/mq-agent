# mq-agent

[![Tests](https://github.com/MCamner/mq-agent/actions/workflows/tests.yml/badge.svg)](https://github.com/MCamner/mq-agent/actions)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![Status](https://img.shields.io/badge/status-v0.2.3-green)](https://mcamner.github.io/mq-agent/)
[![Docs](https://img.shields.io/badge/docs-GitHub%20Pages-blue)](https://mcamner.github.io/mq-agent/)

Terminal-native AI agent orchestrator for the mq ecosystem.

## 30 second demo

```bash
mq-agent doctor                    # check environment
mq-agent score .                   # README + publish score (no API key)
mq-agent audit . --dry-run         # repo audit plan
mq-agent release-check --dry-run   # release readiness plan
```

```mermaid
flowchart TD
    A[mqlaunch] --> B[mq-agent]
    B --> C[mq-hal\nreasoning]
    B --> D[mq-mcp\ntool layer]
    B --> E[repo-signal\nrepo intel]
    B --> F[Planner]
    B --> G[Executor]
    B --> H[Verifier]
    B --> I[Memory]
    B --> J[Safety]
```

## Why

Most AI coding tools either wrap a model around shell commands or hide execution behind a chat UI.

mq-agent is different: it treats agent work as a controlled terminal workflow with explicit planning, tool routing, verification, memory and safety gates. Every action is traceable, every operation is gated, and the model never runs unsupervised.

## Use cases

mq-agent is useful when you want to:

- audit a repository before publishing
- generate a release readiness plan with explicit approval gates
- score README and publish quality without an API key
- inspect and fix CI failures with AI-generated steps
- run safe terminal workflows where the model cannot act without permission
- combine repo-signal, mq-mcp and mq-hal into one local agent workflow

## What it is

Not an AI wrapper script. An actual orchestrator with:

| Layer        | Responsibility               |
|--------------|------------------------------|
| **Planner**  | Decomposes goals into steps  |
| **Executor** | Runs steps through tools     |
| **Verifier** | Checks each result with AI   |
| **Memory**   | Session + persistent state   |
| **Safety**   | Enforces operation modes     |

## Quick start

```bash
# Install
uv pip install -e ".[dev,signal]"

# Check environment
mq-agent doctor

# Score a repo (no API key needed)
mq-agent score .

# Full AI-backed repo assessment
export OPENAI_API_KEY=sk-...
mq-agent signal .

# Read-only audit
mq-agent audit .
```

## Install

### Local development

```bash
uv pip install -e ".[dev,signal]"
```

### From GitHub

```bash
pipx install git+https://github.com/MCamner/mq-agent.git
```

### PyPI (planned)

```bash
pipx install mq-agent   # coming soon
```

Requires `OPENAI_API_KEY` for AI commands. `score`, `doctor`, `repo-summary` and `tools` work without it.

## Demo

```text
$ mq-agent score .
╭──────────────────────── README Score ─────────────────────────╮
│ README score: 100/100  [██████████]                           │
│ ✓ title  ✓ install  ✓ usage  ✓ examples  ✓ badges            │
│ ✓ license  ✓ roadmap  ✓ contributing  (none missing)          │
╰───────────────────────────────────────────────────────────────╯
╭──────────────────── Publish Checklist ────────────────────────╮
│ Publish checklist: 16/16  [PASS]                              │
│ Repo looks publish-ready from the static checklist.           │
╰───────────────────────────────────────────────────────────────╯
```

See [docs/DEMO.md](docs/DEMO.md) for the full end-to-end walkthrough.

## CLI

```bash
mq-agent audit .                   # Read-only repo audit
mq-agent release-plan              # Show release plan
mq-agent release-check             # Validate release readiness (suggest mode)
mq-agent release-check --approve   # Execute checks
mq-agent repo-summary .            # Quick repo overview
mq-agent run "pytest" --approve    # Safe shell execution
mq-agent fix-ci                    # Diagnose CI failures
mq-agent doctor                    # Check environment
mq-agent tools                     # List registered tools
mq-agent tui                       # Launch Textual dashboard

# All commands support --dry-run and --json
mq-agent audit . --dry-run
mq-agent audit . --json
```

## Safety modes

```text
read-only   → only read tools allowed
suggest     → plan shown, nothing executed (default for most commands)
execute     → runs after safety check (requires --approve for destructive ops)
dangerous   → no restrictions (requires explicit flag)
```

## Architecture

```text
mq_agent/
├── core/
│   ├── state.py          # AgentState, PlanStep, SafetyMode, StepStatus
│   ├── planner.py        # OpenAI-backed plan generation
│   ├── executor.py       # Tool routing + safety enforcement
│   ├── verification.py   # OpenAI-backed result verification
│   ├── memory.py         # Session + persistent memory
│   └── safety.py         # Safety gate (mode enforcement)
├── tools/
│   ├── git_tools.py      # git_status, git_log, git_diff, git_branch, git_remote
│   ├── shell_tools.py    # run_command (blocked pattern list)
│   ├── repo_tools.py     # repo_summary, list_files, read_file, find_files
│   ├── signal_tools.py   # repo_scan, repo_readme_score, repo_publish_checklist, repo_analyze
│   └── mcp_bridge.py     # HTTP bridge to mq-mcp
├── agents/
│   ├── audit_agent.py    # Repo audit (read-only)
│   ├── release_agent.py  # Release validation
│   ├── ci_agent.py       # CI failure diagnosis
│   ├── docs_agent.py     # Documentation audit
│   └── signal_agent.py   # repo-signal static scan + AI improvement plan
├── tui/
│   └── app.py            # Textual dashboard
├── prompts/
│   ├── planner.md        # System prompt for Planner
│   └── verifier.md       # System prompt for Verifier
└── tasks/
    ├── release.yaml      # Declarative release task
    ├── audit.yaml        # Declarative audit task
    └── fix_ci.yaml       # Declarative CI fix task
```

## Proof

- 37 tests pass — `uv run pytest -v` — no OpenAI calls required
- `mq-agent score .` — 100/100 README, 16/16 publish checklist [PASS]
- `mq-agent doctor` — all required checks pass
- `mq-agent audit . --dry-run` — safe, read-only plan generation
- `mq-agent signal . --dry-run` — repo-signal assessment without execution
- Safety modes documented and enforced — dangerous patterns blocked at tool level
- `--dry-run` and `--json` supported on all commands

```bash
uv run pytest tests/ -v
```

## Docs

- [Command reference](docs/COMMANDS.md)
- [Safety contract](docs/SAFETY_CONTRACT.md)
- [mq ecosystem](docs/MQ_ECOSYSTEM.md)
- [Skills](SKILLS.md)
- [Examples](docs/EXAMPLES.md)
- [Safety](docs/SAFETY.md)
- [Roadmap](docs/ROADMAP.md)
- [Release checklist](docs/RELEASE_CHECKLIST.md)
- [Contributing](CONTRIBUTING.md)
- [Changelog](CHANGELOG.md)

## v0.2.3 status

- [x] Planner (OpenAI gpt-4o, structured JSON output)
- [x] Executor (tool registry, dry-run, safety gate)
- [x] Verifier (OpenAI gpt-4o-mini, per-step verification)
- [x] Memory (session + persistent JSON)
- [x] Safety (read-only / suggest / execute / dangerous)
- [x] Git tools
- [x] Shell tools (blocked pattern list)
- [x] Repo tools
- [x] MCP bridge (mq-mcp over HTTP)
- [x] Audit agent, Release agent, CI agent, Docs agent
- [x] Signal agent (repo-signal + AI improvement plan)
- [x] Textual TUI
- [x] JSON output and dry-run on all commands
- [x] `mq-agent doctor` — full environment check
- [x] `mq-agent signal` — scored repo assessment with AI plan
- [x] `mq-agent score` — instant README + publish checklist (no API key)
- [x] python-dotenv auto-load from `.env`
- [x] Skills definitions (`SKILLS.md` + `skills/`)
- [x] Command reference, safety contract, ecosystem docs
- [x] GitHub Pages live at mcamner.github.io/mq-agent
- [x] 11 GitHub topics, MIT license, issue templates

## Roadmap

- Autonomous looping agents
- Browser control
- Multi-agent swarms
- Semantic repository memory
- mqlaunch integration

See [docs/ROADMAP.md](docs/ROADMAP.md) for details.

## Notes

Do not commit API keys, local secrets, or private environment files.
