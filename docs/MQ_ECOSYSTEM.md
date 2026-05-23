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
| `mqlaunch` | Active | `g` key → agent menu in mqlaunch |
| `mq-mcp` | Bridge ready | HTTP bridge at `:8765` |
| `mq-hal` | Planned | `mq-agent brief --hal` |

## mqlaunch integration

`mq-agent` is accessible from `mqlaunch` via the `g` key or by typing `agent`:

```
mqlaunch → g → Agent menu
mqlaunch → agent score    (runs mq-agent score . directly)
mqlaunch → agent audit    (runs mq-agent audit . directly)
mqlaunch → agent doctor   (runs mq-agent doctor directly)
```

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
