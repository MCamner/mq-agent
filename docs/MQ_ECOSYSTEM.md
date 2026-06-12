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
mqobsidian        Second brain vault (durable memory: truth notes, reviews, learn, decisions)
atlas-one         Prompt and interaction layer
```

Division of labour across the stack: **mqlaunch launches, mq-agent
orchestrates, mq-mcp thinks and runs, repo-signal measures, mqobsidian
remembers.**

See [MQ_CONTROL_PLANE.md](MQ_CONTROL_PLANE.md) for the control-plane map that
ties signal, review, learn, memory and release into one operator flow.

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
        └── mq-image-analyze — visual architecture observations and OCR
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
| `mqlaunch` | Active | 19-item agent menu + 6 prompt commands |
| `mq-mcp` | Active | HTTP bridge at `:8765`; 66 tools, safety classes A–D |
| `mq-hal` | Active | `hal_repo_report` via mq-mcp bridge |
| `mq-image-analyze` | Active | HTTP bridge at `:8766`; `observe_architecture`, `image_ocr` visual context |
| `mqobsidian` | Active | Standard export structure (`mq-agent brain structure`); truth notes, reviews and learn notes via `--brain` / `truth-export`; gated by `mq-agent stack brain-gate` |

## mqlaunch integration

`mq-agent` is fully wired into `mqlaunch` via a dedicated menu module and prompt commands.
See [COMMAND_SURFACE.md](COMMAND_SURFACE.md) for the canonical command-count reference.

**Menu** — press `g` or type `agent` at the mqlaunch prompt, then choose 1–19:

```text
mqlaunch → g → Agent menu
  1  score .          2  signal .
  3  repo-summary .   4  tools
  5  audit .          6  signal .
  7  release-check    8  fix-ci
  9  doctor           10 tui
  11 mcp status       12 mcp tools
  17 demo flow        18 stack sweep
  19 stack loop plan
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

## mq-image-analyze bridge

When `mq-image-analyze` is running as an MCP server on `:8766`, `mq-agent`
routes visual perception tools through `run-tool`:

```bash
mq-image mcp --transport sse

mq-agent run-tool observe_architecture --arg image_path=docs/arch.png --json
mq-agent run-tool image_ocr --arg image_path=docs/diagram.png --json
```

`mq-agent` only delegates and safety-gates the call. The returned
`visual_architecture_observation.v1` or `image_ocr.v1` payload can then be
passed to mq-mcp review workflows as structured context.

## Design principles

- Each tool owns one layer of the stack
- Tools call each other over well-defined interfaces (HTTP, CLI, Python API)
- mq-agent is the orchestrator — it delegates, not duplicates
- Safety is enforced at the orchestrator level, not in individual tools
