# Integrations

mq-agent is the orchestration layer for the mq ecosystem. It routes goals to the right tools, agents and services.

## mqlaunch

**Role:** Command surface and menu entry point.

mqlaunch is the top-level CLI that users interact with. It delegates tasks to mq-agent for orchestration. mq-agent should be callable directly or via mqlaunch.

**Status:** Planned integration. mq-agent currently runs standalone.

---

## mq-hal

**Role:** Reasoning and local assistant layer.

mq-hal provides local AI reasoning capabilities. The planned integration lets mq-agent use mq-hal as a fallback planner when OpenAI is not available, or as a local-first reasoning layer for faster, cheaper planning on simple tasks.

**Status:** Planned for v0.4.0.

---

## mq-mcp

**Role:** Tool execution and local bridge.

mq-mcp exposes tools via the Model Context Protocol over HTTP. mq-agent connects to mq-mcp via `mq_agent/tools/mcp_bridge.py`.

When mq-mcp is running locally on `:8765`, `mcp_call` can route tool calls to it:

```python
from mq_agent.tools.mcp_bridge import MCPBridge

bridge = MCPBridge("http://localhost:8765")
result = bridge.call_tool("your_tool", {"arg": "value"})
```

Check availability:

```bash
mq-agent doctor   # shows mq-mcp (optional) status
```

**Status:** Bridge implemented. Full tool discovery and routing planned for v0.3.0.

---

## repo-signal

**Role:** Repository intelligence, scoring and release readiness.

repo-signal analyses repositories and produces structured health scores and release readiness signals. mq-agent will integrate repo-signal output into:

- `mq-agent audit` — health score per repo
- `mq-agent release-check` — release readiness score with blocking criteria
- `mq-agent repo-summary` — signal-enriched summary

**Status:** Planned for v0.2.0. This is the next milestone.

---

## OpenAI

**Role:** Planning and verification backbone.

mq-agent uses two OpenAI models:

| Model         | Role                                  |
|---------------|---------------------------------------|
| `gpt-4o`      | Planner — goal decomposition          |
| `gpt-4o-mini` | Verifier — per-step result checking   |

Both use structured JSON output mode. Prompts live in `prompts/planner.md` and `prompts/verifier.md`.

Requires `OPENAI_API_KEY` in environment.

---

## Future

- **Semantic memory** — OpenAI vector stores for cross-session repo knowledge
- **Local model support** — Ollama or similar for offline planning
