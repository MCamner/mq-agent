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

## Orchestration contract

The formal boundary between mq-agent and mq-mcp is defined in
[mq-mcp/docs/ORCHESTRATION_CONTRACT.md](https://github.com/MCamner/mq-mcp/blob/main/docs/ORCHESTRATION_CONTRACT.md).

Key rules for mq-agent:

- Class A/B tools may be auto-invoked without user confirmation
- Class C (write files) and Class D (subprocess/open apps) require explicit user approval
- mq-agent must never reimplement review logic, architecture reasoning, or semantic retrieval
- mq-agent must not assume mq-mcp maintains session state between calls
- mq-agent must not construct filesystem paths outside of tool arguments
- Tool chains that together produce a git commit or push are prohibited

Verify contract compliance at any time:

```bash
mq-agent run-tool validate_orchestration_contract
```

## Safety classes

mq-mcp serves real safety classes via `/tools` and `/tool-contracts`.
mq-agent uses them to enforce its safety gate — no guessing from name
prefixes when the server is up.

| Class | Examples                          | Gate behaviour         |
|-------|-----------------------------------|------------------------|
| A     | `read_repo_file`, `git_status`    | No flags required      |
| B     | `repo_signal_analyze`, `get_wifi_info` | No flags required |
| C     | `update_repo_file`, `edit_image`  | Requires `--approve`   |
| D     | `open_in_app`, `run_tests`        | Requires `--approve`   |
| —     | `remove_*`                        | Requires `--dangerous` |

## Tool contracts endpoint

mq-mcp exposes machine-readable contracts at `GET /tool-contracts`:

```bash
curl http://localhost:8765/tool-contracts | jq '.tool_count'
curl http://localhost:8765/tool-contracts | jq '.tools[] | select(.class == "C")'
```

## Example local workflow

```bash
# 1. Start mq-mcp
uv --directory ~/mq-mcp/mq-mcp run python server.py &

# 2. Verify it is up and serving all 66 tools
mq-agent mcp status --json | jq '.servers["mq-mcp"]'

# 3. Inspect a tool's safety class
mq-agent tools --describe read_repo_file

# 4. Dry-run a read tool (no flags needed)
mq-agent run-tool read_repo_file --arg path=README.md --dry-run

# 5. Run a write tool with approval
mq-agent run-tool edit_image --arg relative_path=img.jpg \
    --arg action=resize --arg value=800 --approve

# 6. Stop mq-mcp when done
mq-agent mcp stop
```

## Troubleshooting

**Port already in use**

```text
ERROR: [Errno 48] Address already in use
```

Find and kill the existing process:

```bash
lsof -ti :8765 | xargs kill -9
```

Or start on a different port:

```bash
MQ_MCP_PORT=8766 uv run python server.py
MQ_MCP_ENDPOINT=http://localhost:8766 mq-agent mcp status
```

**mq-agent cannot reach mq-mcp**

```bash
mq-agent mcp status --json   # shows endpoint and reachability
curl http://localhost:8765/health   # direct health check
```

**Wrong Python environment**

Always use `uv run` inside the mq-mcp directory — system Python lacks
the required packages:

```bash
uv --directory ~/mq-mcp/mq-mcp run python server.py
```

**Tool safety class shows `unknown`**

mq-mcp serves safety classes from `docs/tool_contracts.json`. If that
file is missing or stale, regenerate it:

```bash
cd ~/mq-mcp && python3 scripts/generate_tool_contracts.py
```

## Safety

See [TOOL_ROUTING.md](TOOL_ROUTING.md) for the full safety classification
reference.
