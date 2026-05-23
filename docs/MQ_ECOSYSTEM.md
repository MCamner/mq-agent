# mq ecosystem

mq-agent is one part of a broader set of local, terminal-native tools built around the `mq` namespace.

## Components

```
mqlaunch      Terminal command surface and menu launcher
mq-agent      AI agent orchestrator (this repo)
mq-hal        Local reasoning and assistant layer (Ollama)
mq-mcp        Local tool bridge (MCP protocol)
repo-signal   Repository quality intelligence
```

## How they fit together

```
mqlaunch
  └── launches any mq tool from a terminal menu

mq-agent
  ├── Planner    — GPT-4o structured plan generation
  ├── Executor   — tool routing through safety gate
  ├── Verifier   — GPT-4o-mini result verification
  ├── Memory     — session + persistent state
  └── Safety     — four-mode safety gate

mq-mcp
  └── HTTP bridge to local tools
      mq-agent calls mq-mcp for low-level operations

repo-signal
  └── repo quality analysis
      mq-agent calls repo-signal for scoring and assessment

mq-hal
  └── local model via Ollama
      future: mq-agent delegates reasoning to mq-hal
```

## Integration status

| Integration | Status | How |
|-------------|--------|-----|
| `repo-signal` | Active | `mq-agent signal .` / `mq-agent score .` |
| `mqlaunch` | Active | 12-item agent menu + 6 prompt commands |
| `mq-mcp` | Active | HTTP bridge at `:8765`; safety classification offline |
| `mq-hal` | Planned | `mq-agent brief --hal` |

## mqlaunch integration

`mq-agent` is fully wired into `mqlaunch` via a dedicated menu module and prompt commands.
See [COMMAND_SURFACE.md](COMMAND_SURFACE.md) for the canonical command-count reference.

**Menu** — press `g` or type `agent` at the mqlaunch prompt, then choose 1–12:

```
mqlaunch → g → Agent menu
  1  score .          2  signal .
  3  repo-summary .   4  tools
  5  audit .          6  signal .
  7  release-check    8  fix-ci
  9  doctor           10 tui
  11 mcp status       12 mcp tools
```

**Direct prompt commands:**

```
mqlaunch → agent score          # mq-agent score .
mqlaunch → agent audit          # mq-agent audit .
mqlaunch → agent doctor         # mq-agent doctor
mqlaunch → agent release-check  # mq-agent release-check
mqlaunch → agent mcp-status     # mq-agent mcp status
mqlaunch → agent mcp-tools      # mq-agent mcp tools
```

See [MQLAUNCH_INTEGRATION.md](MQLAUNCH_INTEGRATION.md) for the full bridge spec.

## mq-mcp bridge

When `mq-mcp` is running on `:8765`, `mq-agent` can route tool calls through it:

```bash
# Start mq-mcp
mq-mcp serve

# mq-agent detects it automatically
mq-agent doctor   # shows mq-mcp: ✓ OK
```

## Design principles

- Each tool owns one layer of the stack
- Tools call each other over well-defined interfaces (HTTP, CLI, Python API)
- mq-agent is the orchestrator — it delegates, not duplicates
- Safety is enforced at the orchestrator level, not in individual tools
