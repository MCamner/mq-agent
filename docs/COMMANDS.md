# Command Reference

## All commands

| Command | Safety mode | Needs API key | Description |
|---------|-------------|---------------|-------------|
| `mq-agent doctor` | read-only | no | Check environment and dependencies |
| `mq-agent score .` | read-only | no | README score + publish checklist |
| `mq-agent repo-summary .` | read-only | no | Concise repo overview |
| `mq-agent tools` | read-only | no | List registered tools |
| `mq-agent audit .` | read-only | yes | Full repo audit with AI verification |
| `mq-agent signal .` | read-only | yes | repo-signal assessment + AI improvement plan |
| `mq-agent plan "goal"` | suggest | yes | Generate a plan for a goal |
| `mq-agent release-plan` | suggest | yes | Show the standard release plan |
| `mq-agent release-check` | suggest | yes | Validate release readiness |
| `mq-agent release-check --approve` | execute | yes | Run release checks with execution |
| `mq-agent fix-ci` | suggest | yes | Diagnose CI failures |
| `mq-agent run "cmd" --approve` | execute | no | Run a shell command safely |
| `mq-agent tui` | read-only | no | Launch Textual dashboard |

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

# JSON output for scripting
mq-agent audit . --json | jq '.steps[] | select(.status == "failed")'
mq-agent score . --json
```

## Safety modes

| Mode | What it allows |
|------|----------------|
| `read-only` | Only reading tools — git, file reads, repo analysis |
| `suggest` | Full planning, no execution |
| `execute` | Runs steps after safety gate check |
| `dangerous` | No restrictions — use with explicit intent |

Commands that write or execute require either `--approve` or an explicit safety mode upgrade.
