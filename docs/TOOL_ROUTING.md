# Tool Routing and Safety Classification

mq-agent classifies every MCP tool before routing it. Unknown or unsafe tools are blocked.

## Safety classes

| Class | Behavior | Flag required |
|---|---|---|
| `read-only` | Allowed in all modes | none |
| `write-capable` | Blocked until approved | `--approve` |
| `subprocess` | Blocked until approved | `--approve` |
| `dangerous` | Blocked until dangerous mode | `--dangerous` |
| `unknown` | Always blocked | cannot run |

## Name-prefix classification

When the mq-mcp server does not return explicit metadata, mq-agent infers the class from the tool name prefix:

| Prefix | Class |
|---|---|
| `read_`, `list_`, `get_`, `search_`, `find_`, `scan_`, `git_` | `read-only` |
| `update_`, `write_`, `set_`, `create_`, `edit_`, `new_` | `write-capable` |
| `delete_`, `remove_` | `dangerous` |
| `run_`, `validate_`, `execute_`, `invoke_`, `open_`, `launch_` | `subprocess` |
| anything else | `unknown` |

When the server returns explicit `safety_class` metadata, that wins over name inference.

## Routing rules

```text
unknown        → always blocked, no flag overrides this
dangerous      → requires --dangerous
write-capable  → requires --approve (or --dangerous)
subprocess     → requires --approve (or --dangerous)
read-only      → allowed without flags
```

## Dry-run

Any tool can be previewed without execution:

```bash
mq-agent run-tool update_repo_file --arg path=README.md --arg old=x --arg new=y --approve --dry-run
```

The dry-run output shows the tool name, resolved args, and safety class — but does not contact mq-mcp.

## Examples

```bash
# Read-only — runs immediately
mq-agent run-tool read_repo_file --arg path=README.md

# Write-capable — blocked without --approve
mq-agent run-tool update_repo_file --arg path=README.md --arg old=x --arg new=y
# → Blocked: tool 'update_repo_file' is classified write-capable. Add --approve to run it.

mq-agent run-tool update_repo_file --arg path=README.md --arg old=x --arg new=y --approve

# Unknown tool — always blocked
mq-agent run-tool mystery_tool
# → Blocked: tool 'mystery_tool' has unknown safety class.

# Dangerous — blocked without --dangerous
mq-agent run-tool remove_device --arg Id=42
# → Blocked: tool 'remove_device' is classified dangerous. Add --dangerous to run it.
```
