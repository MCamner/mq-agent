# MCP Integration

mq-agent integrates with [mq-mcp](https://github.com/MCamner/mq-mcp) to discover and route local tools.

## Architecture

```text
user command
  ↓
mq-agent CLI
  ↓
MCPBridge (HTTP)
  ↓
mq-mcp server on :8765
  ↓
PSIGEL / repo tools / shell tools
```

mq-agent never directly executes arbitrary shell. Every call goes through the safety gate before reaching mq-mcp.

## Start mq-mcp

```bash
uv --directory ~/mq-mcp/mq-mcp run python server.py
```

Verify it is running:

```bash
mq-agent mcp status
```

## Discover tools

```bash
mq-agent mcp tools              # list all tools with safety class
mq-agent mcp tools --json       # machine-readable output
mq-agent tools --mcp            # built-in + MCP tools combined
mq-agent tools --describe read_repo_file   # single tool detail
```

## Run a tool

```bash
# Read-only — no flags needed
mq-agent run-tool read_repo_file --arg path=README.md

# Write-capable or subprocess — requires --approve
mq-agent run-tool update_repo_file --arg path=README.md --arg old=x --arg new=y --approve

# Dangerous — requires --dangerous
mq-agent run-tool remove_device --arg Id=42 --dangerous

# Dry-run any tool
mq-agent run-tool git_status --dry-run
```

## JSON output

All MCP commands support `--json`:

```bash
mq-agent mcp status --json
mq-agent mcp tools --json
mq-agent run-tool git_status --json
```

## When mq-mcp is unavailable

mq-agent fails closed. `run-tool` exits with a clear error:

```text
mq-mcp is not reachable at http://localhost:8765

Start mq-mcp with:
  uv --directory ~/mq-mcp/mq-mcp run python server.py
```

`mq-agent tools --describe <name>` still works when mq-mcp is down — it infers the safety class from the tool name.

## Safety

See [TOOL_ROUTING.md](TOOL_ROUTING.md) for the full safety classification reference.
