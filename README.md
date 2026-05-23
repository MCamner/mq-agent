# mq-agent

Terminal-native AI agent orchestrator for the mq ecosystem.

```text
                 ┌─────────────────┐
                 │   mqlaunch      │
                 │ command surface │
                 └────────┬────────┘
                          │
                          ▼
                 ┌─────────────────┐
                 │    mq-agent     │
                 │ orchestration   │
                 └────────┬────────┘
                          │
        ┌─────────────────┼─────────────────┐
        ▼                 ▼                 ▼
 ┌────────────┐   ┌────────────┐   ┌────────────┐
 │   mq-hal   │   │   mq-mcp   │   │repo-signal│
 │ reasoning  │   │ tool layer │   │repo intel │
 └────────────┘   └────────────┘   └────────────┘
```

## What it is

Not an AI wrapper script. An actual orchestrator with:

| Layer        | Responsibility               |
|--------------|------------------------------|
| **Planner**  | Decomposes goals into steps  |
| **Executor** | Runs steps through tools     |
| **Verifier** | Checks each result with AI   |
| **Memory**   | Session + persistent state   |
| **Safety**   | Enforces operation modes     |

## Install

```bash
./scripts/install.sh
# or
uv pip install -e ".[dev]"
```

Requires `OPENAI_API_KEY` in environment.

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
│   └── mcp_bridge.py     # HTTP bridge to mq-mcp
├── agents/
│   ├── audit_agent.py    # Repo audit (read-only)
│   ├── release_agent.py  # Release validation
│   ├── ci_agent.py       # CI failure diagnosis
│   └── docs_agent.py     # Documentation audit
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

## Tests

```bash
pytest tests/ -v
```

26 tests, no OpenAI calls required.

## v0.1.0 status

- [x] Planner (OpenAI gpt-4o, structured JSON output)
- [x] Executor (tool registry, dry-run, safety gate)
- [x] Verifier (OpenAI gpt-4o-mini, per-step verification)
- [x] Memory (session + persistent JSON)
- [x] Safety (read-only / suggest / execute / dangerous)
- [x] Git tools
- [x] Shell tools (blocked pattern list)
- [x] Repo tools
- [x] MCP bridge (mq-mcp over HTTP)
- [x] Audit agent
- [x] Release agent
- [x] CI agent
- [x] Textual TUI
- [x] JSON output on all commands
- [x] Dry-run on all commands
- [x] `mq-agent doctor`

## Not in v0.1.0

- Autonomous looping agents
- Browser control
- Multi-agent swarms
- repo-signal integration (next milestone)

## Notes

Do not commit API keys, local secrets, or private environment files.
