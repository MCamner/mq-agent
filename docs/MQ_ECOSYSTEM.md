# mq ecosystem

mq-agent is one part of a broader set of local, terminal-native tools built around the `mq` namespace.

## Components

```text
mqlaunch          Terminal command surface and menu launcher (human entrypoint)
mq-agent          AI agent orchestrator (this repo)
mq-mcp            Central AI cognition runtime (review, architecture, semantic memory)
repo-signal       Repository intelligence and preprocessing layer
mq-hal            Runtime observability and operator status layer
mq-image-analyze  Visual cognition layer (diagram, screenshot, infra topology)
atlas-one         Prompt and interaction layer
```

## Layered architecture

```text
macos-scripts / mqlaunch   — human terminal entrypoint
        │
        ▼
    mq-agent                — orchestration: plans, routes, gates, verifies
        │
        ▼
    mq-mcp (v1.3.0)         — central cognition runtime
        │
        ├── review engine         (review_file, review_diff, review_repo)
        ├── architecture memory   (list/get/record_architecture_decision)
        ├── repo context builder  (build_repo_context, callgraph)
        ├── orchestration contract (validate_orchestration_contract)
        ├── 66 tools across safety classes A–D
        │
        ├── repo-signal     — repo intelligence packs (future: callgraph, symbols)
        ├── mq-hal          — runtime health and observability summaries
        └── mq-image-analyze — visual architecture observations (future)
```

The boundary between mq-agent and mq-mcp is defined in
[mq-mcp/docs/ORCHESTRATION_CONTRACT.md](https://github.com/MCamner/mq-mcp/blob/main/docs/ORCHESTRATION_CONTRACT.md).

Key rule: **mq-agent orchestrates. mq-mcp executes and reviews.**
mq-agent must not reimplement review logic, architecture reasoning, or semantic retrieval.
Learn extraction follows the same boundary: mq-mcp owns extraction, validation
and storage approval; mq-agent only exposes read-only learn status/search/explain.

## Integration status

| Integration | Status | How |
|-------------|--------|-----|
| `repo-signal` | Active | `mq-agent signal .` / `mq-agent score .` |
| `mqlaunch` | Active | 12-item agent menu + 6 prompt commands |
| `mq-mcp` | Active | HTTP bridge at `:8765`; 66 tools, safety classes A–D |
| `mq-hal` | Active | `hal_repo_report` via mq-mcp bridge |
| `mq-image-analyze` | Planned | visual architecture observations as review context |

## mqlaunch integration

`mq-agent` is fully wired into `mqlaunch` via a dedicated menu module and prompt commands.
See [COMMAND_SURFACE.md](COMMAND_SURFACE.md) for the canonical command-count reference.

**Menu** — press `g` or type `agent` at the mqlaunch prompt, then choose 1–12:

```text
mqlaunch → g → Agent menu
  1  score .          2  signal .
  3  repo-summary .   4  tools
  5  audit .          6  signal .
  7  release-check    8  fix-ci
  9  doctor           10 tui
  11 mcp status       12 mcp tools
```

**Direct prompt commands:**

```text
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
