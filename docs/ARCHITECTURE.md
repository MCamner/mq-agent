# mq-agent Architecture

mq-agent is an existing orchestration runtime. Its current architecture should be
stabilized before adding more browser automation, agent autonomy, or new
multi-agent behavior.

## Current Flow

```text
User
  |
  v
mq-agent CLI / mqlaunch / TUI
  |
  +--> command handlers in mq_agent/main.py
        |
        +--> agents/* for AI-backed workflows
        |     |
        |     +--> Planner -> Executor -> Verifier
        |
        +--> core/task_runner.py for YAML task workflows
        |
        +--> tools/TOOL_REGISTRY for built-in tools
        |
        +--> tools/mcp_bridge.py for mq-mcp tools
        |
        +--> memory/semantic.py for repo memory commands
```

## Stabilization Rules

v0.6.1 is a stabilization checkpoint, not a rewrite.

- Do not rewrite Planner, Executor, Verifier, or Task Runner.
- Do not rewrite the TUI.
- Do not change the mqlaunch layout.
- Do not duplicate task runner logic.
- Do not add new autonomous browser execution.
- Do not add new multi-agent behavior until the current boundaries are locked.
- Preserve current CLI commands and flags.
- Add tests before changing command behavior.

## Boundaries

### CLI

`mq_agent/main.py` owns command parsing, user-facing output, and Typer app
composition. It lazily imports agents, core helpers, and tools inside command
handlers so import-time side effects stay low.

Current coupling:

- CLI commands know which agent or helper implements each workflow.
- CLI rendering and command orchestration live in the same file.
- Several commands expose `--json`; tests should lock those schemas before
  refactors.

### Planner

`mq_agent/core/planner.py` turns an `AgentState` and available tool names into
`PlanStep` objects through an OpenAI chat completion.

Boundary:

- Planner should only create plans.
- Planner should not execute tools, enforce safety, or mutate files.

Current coupling:

- Planner depends on the prompt file path and OpenAI response shape.
- Tool availability is passed as names, not structured capability metadata.

### Executor

`mq_agent/core/executor.py` runs `PlanStep` objects through a provided tool
registry and a `SafetyGate`.

Boundary:

- Executor owns step status transitions during execution.
- Executor should not create plans or verify semantic correctness.

Current coupling:

- Executor assumes tool args map directly to callable keyword arguments.
- Dry-run output is string-based and used by tests/docs.

### Verifier

`mq_agent/core/verification.py` verifies step output through an OpenAI chat
completion, with direct handling for failed, skipped, and pending steps.

Boundary:

- Verifier should only assess results.
- Verifier should not rerun tools or mutate state beyond verification fields.

Current coupling:

- Verification is model-backed for successful steps.
- Failure and skip handling are deterministic and should remain testable
  without API calls.

### Task Runner

`mq_agent/core/task_runner.py` loads YAML tasks, resolves `{{step:name}}`
templates, and executes steps via `TOOL_REGISTRY`.

Boundary:

- Task runner owns declarative YAML workflow execution.
- CLI and tools should call the task runner instead of duplicating YAML logic.

Current coupling:

- `run_task()` imports `mq_agent.tools.TOOL_REGISTRY` at execution time.
- Task lookup by filename stem or internal `name:` is implemented in the CLI.
- Template resolution is intentionally simple string substitution.

### Tool Registry

`mq_agent/tools/__init__.py` is the built-in tool registry.

Boundary:

- Built-in tools should be registered once.
- Safety classification should stay explicit in `core/safety.py` and
  `tools/mcp_registry.py`.

Current coupling:

- `SafetyGate` has a separate `SAFE_TOOLS` list for read-only execution.
- Tool registry names are used by Planner, Executor, Task Runner, docs, and
  task YAML files.

### Memory

`mq_agent/memory/semantic.py` owns semantic memory diagnostics and upload calls.

Boundary:

- Memory commands should stay explicit and approval-gated.
- Memory build/refresh should not upload silently.

Current coupling:

- Semantic memory shells out to `repo-signal`.
- Environment variables define vector store state.

### MCP Bridge

`mq_agent/tools/mcp_bridge.py` routes calls to configured MCP servers and
returns tool specs through `mcp_registry`.

Boundary:

- MCP bridge owns reachability, listing, description, and tool calls.
- CLI owns user-facing safety gates for `run-tool`.

Current coupling:

- `MultiMCPBridge` reads configured servers at construction time.
- A module-level default bridge exists for `mcp_call`.
- Unknown tool names fall back to name-based classification.

### TUI

`mq_agent/tui/app.py` is a Textual dashboard that shells out to the installed
`mq-agent` command.

Boundary:

- TUI is a command launcher and output viewer.
- TUI should not reimplement CLI command logic.

Current coupling:

- TUI command list must stay synchronized with the CLI command surface.
- TUI depends on `mq-agent` being available on `PATH`.

## Current Coupling Risks

- Command behavior is spread across CLI handlers, docs, task YAML, and tests.
- Read-only safety for built-in tools is separate from tool registration.
- Browser tools are registered in `TOOL_REGISTRY`, but browser safety is mostly
  enforced inside browser tool helpers rather than in `SafetyGate`.
- Task lookup logic lives in the CLI while task execution lives in
  `core/task_runner.py`.
- TUI command options can drift from `docs/COMMAND_SURFACE.md`.
- Swarm workflows call agent classes directly and should not grow new behavior
  until current contracts are locked.

## Stabilization Test Targets

Tests should lock:

- CLI commands that do not require API keys.
- Dry-run output for task workflows.
- Tool registry names used by YAML tasks.
- Swarm plan behavior without API calls.
- TUI command list entries.
- Safety mode decisions for built-in tools.

## Validation

Primary validation:

```bash
uv run pytest -v
mq-agent doctor
mq-agent task list
mq-agent release-check --dry-run
```

Notes:

- `mq-agent release-check --dry-run` currently uses the AI-backed release agent
  and requires `OPENAI_API_KEY`.
- `mq-agent doctor` reports optional integrations separately from required
  checks.
