# mq-agent Architecture

mq-agent is a terminal-native workflow orchestration runtime. It coordinates
safe local execution, repo intelligence, MCP tools, and semantic memory into one
operator-driven surface.

## Module map

```text
mq_agent/
  main.py              — CLI entry point (Typer); delegates to core, agents, tools
  config.py            — MqAgentConfig: load/save ~/.mq-agent/config.json
  cli/
    render.py          — Rich rendering helpers (print_steps, print_swarm_result, …)
  core/
    state.py           — AgentState, PlanStep, StepStatus, SafetyMode
    planner.py         — Planner: goal → PlanStep list (OpenAI)
    executor.py        — Executor: runs PlanStep list through tool registry + SafetyGate
    verification.py    — Verifier: assesses step output (OpenAI)
    task_runner.py     — declarative YAML task execution (StepResult, no AI)
    swarm.py           — SwarmRunner: coordinates specialist agents via AgentManifest
    safety.py          — SafetyGate: enforces safety mode per step
    config.py          — MCP server registry (add/remove/get servers)
    diagnostics.py     — run_checks(): environment health checks for doctor command
    memory.py          — Memory: conversation context store
  agents/
    audit_agent.py     — AuditAgent: read-only repo audit
    ci_agent.py        — CIAgent: CI failure diagnosis
    docs_agent.py      — DocsAgent: documentation audit
    release_agent.py   — ReleaseAgent: release readiness checks
    signal_agent.py    — SignalAgent: full repo-signal assessment
    swarm_registry.py  — built-in swarm configs (audit, release-check, ci)
  tools/
    __init__.py        — TOOL_REGISTRY: all registered callable tools
    repo_tools.py      — file I/O, repo summary, task chaining (run_task_tool)
    git_tools.py       — git status, log, diff, branch, remote
    shell_tools.py     — run_command, which
    signal_tools.py    — repo-signal integration (optional, degrades gracefully)
    browser_tools.py   — read-only URL fetch, inspect, summarize, verify-release
    mcp_bridge.py      — MultiMCPBridge: routes calls to MCP servers
    mcp_registry.py    — MCPToolSpec, safety class classification
  mcp/
    manager.py         — start/stop mq-mcp background process
  memory/
    semantic.py        — semantic memory build/refresh/status/doctor
  tui/
    app.py             — Textual TUI dashboard (command launcher)
```

## Orchestration runtime modes

mq-agent has two parallel orchestration modes. They co-exist and do not replace each other.

### AI-backed planner loop

Used by `audit`, `plan`, `signal`, `fix-ci`, `release-check`, `docs-audit`:

```text
AgentState (goal, safety_mode, working_dir)
  → Planner.create_plan()     [OpenAI]  → list[PlanStep]
  → Executor.run_plan()       [tools]   → AgentState (steps with results)
  → Verifier.verify_plan()    [OpenAI]  → verification summary
```

Step model: `PlanStep` (core/state.py) — holds index, tool, args, status, result, verified.

### Declarative task runner

Used by `mq-agent task run`, and via `run_task` tool from YAML workflows and swarm agents:

```text
tasks/*.yaml
  → load_task()        → Task (name, steps, version)
  → run_task()         → list[StepResult]
```

Step model: `StepResult` (core/task_runner.py) — holds step name, tool, status, output string.

`{{step:name}}` templates in YAML args are resolved from prior step output at runtime.

### Specialist orchestration

Used by `mq-agent swarm *`. Coordinates multiple agents through `AgentManifest` declarations:

```text
swarm config (YAML or built-in)
  → SwarmRunner.run()
      → dispatches each AgentManifest in order
      → each agent calls task_runner or built-in agent class
      → collects AgentResult per agent
  → SwarmResult (passed, failed_agents, elapsed_s)
```

`SwarmRunner` is a separate runtime from the Executor loop. It does not use `AgentState`
or `PlanStep`. It coordinates agents, not steps within a single plan.

## Configuration

Runtime configuration is loaded from `~/.mq-agent/config.json`:

```json
{
  "safety_mode": "suggest",
  "model": "gpt-4o",
  "dry_run": false,
  "working_dir": "."
}
```

Priority order: CLI flags > `MQ_AGENT_MODEL` env var > config.json > built-in defaults.

`MqAgentConfig` (mq_agent/config.py) owns load/save. `Planner` reads `effective_model()`
from config at init time.

MCP server endpoints are stored separately in `~/.mq-agent/config.json` under
`mcp_servers` and managed by `mq_agent/core/config.py`.

## Safety model

Four modes, applied per step by `SafetyGate`:

| Mode | Behavior |
|---|---|
| `read-only` | Only tools in `SAFE_TOOLS`; continues past failures |
| `suggest` | All tools allowed; stops on failure; write ops shown, not run |
| `execute` | All tools allowed; stops on failure; write ops run |
| `dangerous` | No safety checks; continues past failures |

Write-capable operations always require `--approve` at the CLI level. Dry-run is
the default for task workflows.

## Boundaries

### CLI (main.py)

Owns command parsing, output formatting, and Typer app composition. Delegates all
business logic to core, agents, or tools. Rendering helpers live in `cli/render.py`.

Must not contain orchestration logic. Must not be imported by core modules.

### Planner

Creates plans from goals. Must not execute tools, enforce safety, or mutate files.

### Executor

Runs `PlanStep` objects through the tool registry. Must not create plans or verify output.

### Task Runner

Executes YAML task files via `TOOL_REGISTRY`. Must not duplicate Executor logic.
Template resolution (`{{step:name}}`) is intentional string substitution — not dynamic evaluation.

### SwarmRunner

Coordinates specialist agents declared via `AgentManifest`. Is not a replacement
for Executor. Must not grow new autonomous behavior.

### Tool Registry

Single source of truth for callable tools. All tools must accept `**kwargs` only —
no positional-only parameters. Safety classification is explicit in `core/safety.py`
and `tools/mcp_registry.py`.

### Browser tools

Read-only by design. No credential handling, no form submission, no autonomous
browser control. Registered in `TOOL_REGISTRY` — usable in task YAML workflows.

## Validation

```bash
uv run pytest -v                          # 237 tests
uv run ruff check mq_agent/
uv run mypy mq_agent/ --ignore-missing-imports
mq-agent doctor
mq-agent task list
mq-agent swarm plan audit --json
mq-agent task run repo-audit --dry-run
```
