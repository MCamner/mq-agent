# Command Reference

## All commands

| Command | Safety mode | Needs API key | Description |
|---------|-------------|---------------|-------------|
| `mq-agent doctor` | read-only | no | Check environment and dependencies |
| `mq-agent score .` | read-only | no | README score + publish checklist |
| `mq-agent repo-summary .` | read-only | no | Concise repo overview |
| `mq-agent tools` | read-only | no | List registered tools |
| `mq-agent tools --describe <name>` | read-only | no | Show tool metadata and safety class |
| `mq-agent tools --mcp` | read-only | no | Include discovered MCP tools |
| `mq-agent audit .` | read-only | yes | Full repo audit with AI verification |
| `mq-agent signal .` | read-only | yes | repo-signal assessment + AI improvement plan |
| `mq-agent plan "goal"` | suggest | yes | Generate a plan for a goal |
| `mq-agent release-plan` | suggest | yes | Show the standard release plan |
| `mq-agent release-check` | suggest | yes | Validate release readiness |
| `mq-agent release-check --approve` | execute | yes | Run release checks with execution |
| `mq-agent fix-ci` | suggest | yes | Diagnose CI failures |
| `mq-agent run "cmd" --approve` | execute | no | Run a shell command safely |
| `mq-agent tui` | read-only | no | Launch Textual dashboard |

## MCP commands

These commands inspect and invoke the local `mq-mcp` tool server. The server is not required for `--describe`, `--dry-run`, or safety classification.

| Command | Needs mq-mcp | Description |
|---------|-------------|-------------|
| `mq-agent mcp status` | no | Check mq-mcp reachability and tool counts by safety class |
| `mq-agent mcp tools` | no | List all MCP tools with safety class and description |
| `mq-agent run-tool <name>` | yes | Run a specific MCP tool through safety gates |
| `mq-agent run-tool <name> --dry-run` | no | Preview tool call without contacting mq-mcp |
| `mq-agent run-tool <name> --arg k=v` | yes | Pass argument to MCP tool |
| `mq-agent run-tool <name> --approve` | yes | Run write-capable or subprocess tool |
| `mq-agent run-tool <name> --dangerous` | yes | Run dangerous tool (delete/remove class) |

## mqlaunch bridge

`mq-agent` is accessible from `mqlaunch` without typing the full command.

**Menu** — press `g` or type `agent` at the mqlaunch prompt:

| Option | Command |
|--------|---------|
| 1 | `mq-agent score .` |
| 2 | `mq-agent signal .` |
| 3 | `mq-agent repo-summary .` |
| 4 | `mq-agent tools` |
| 5 | `mq-agent audit .` |
| 6 | `mq-agent signal .` |
| 7 | `mq-agent release-check` |
| 8 | `mq-agent fix-ci` |
| 9 | `mq-agent doctor` |
| 10 | `mq-agent tui` |
| 11 | `mq-agent mcp status` |
| 12 | `mq-agent mcp tools` |

**Prompt commands** — type directly at the mqlaunch prompt:

```bash
agent score           # mq-agent score .
agent audit           # mq-agent audit .
agent doctor          # mq-agent doctor
agent release-check   # mq-agent release-check
agent mcp-status      # mq-agent mcp status
agent mcp-tools       # mq-agent mcp tools
```

See [MQLAUNCH_INTEGRATION.md](MQLAUNCH_INTEGRATION.md) for the full bridge architecture.

## Flags

All commands support:

```bash
--dry-run     # Show plan only, no execution
--json        # Machine-readable JSON output
```

`release-check` and `run` also support:

```bash
--approve     # Allow write/execute operations
```

`run-tool` additionally supports:

```bash
--arg key=value   # Pass argument to the MCP tool
--approve         # Run write-capable or subprocess tools
--dangerous       # Run dangerous tools (delete/remove class)
--dry-run         # Preview call without contacting mq-mcp
--json            # Output result as JSON
```

## Examples

```bash
# No API key required
mq-agent doctor
mq-agent score .
mq-agent repo-summary .

# API key required
mq-agent audit .
mq-agent signal .
mq-agent release-check --dry-run

# Safe shell execution
mq-agent run "pytest" --approve
mq-agent run "git status"          # read commands don't need --approve

# MCP tool inspection and execution
mq-agent mcp status --json
mq-agent mcp tools
mq-agent tools --describe read_repo_file --json
mq-agent run-tool read_repo_file --arg path=README.md
mq-agent run-tool update_repo_file --arg path=f.py --arg old=x --arg new=y --approve

# JSON output for scripting
mq-agent audit . --json | jq '.steps[] | select(.status == "failed")'
mq-agent score . --json
mq-agent mcp status --json | jq '.tools.read_only'
```

## Safety modes

| Mode | What it allows |
|------|----------------|
| `read-only` | Only reading tools — git, file reads, repo analysis |
| `suggest` | Full planning, no execution |
| `execute` | Runs steps after safety gate check |
| `dangerous` | No restrictions — use with explicit intent |

Commands that write or execute require either `--approve` or an explicit safety mode upgrade.
