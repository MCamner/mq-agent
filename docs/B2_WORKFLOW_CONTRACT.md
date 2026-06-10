# mq-agent B2 Workflow Contract

**Version:** 1.0  
**Phase:** 3 (mq-agent bridge)  
**Status:** Active

---

## Purpose

This contract defines how `mq-agent` orchestrates the B2 prompt OS workflow.
It describes the four-stage pipeline, the tools it owns, and what it delegates
to `mq-mcp` (read-only).

---

## Workflow: plan → compose → review → output

```
topic/context
     │
     ▼
 [plan]     b2_route(topic)         → prompt_id (e.g. "02.11")
     │
     ▼
 [compose]  b2_get_prompt(id)       → prompt content (markdown)
     │
     ▼
 [review]   mq-mcp.review_repo()    → review findings (read-only, best-effort)
     │
     ▼
 [output]   b2_log_run(...)         → ~/.b2tui_history.jsonl
```

---

## Stages

### 1. Plan — `b2_route`

- Input: free-text topic or context string
- Output: prompt_id string (e.g. `"02.11"`)
- Logic: keyword match against 7 route categories; falls back to `implementation`
- Owner: `mq_agent/tools/b2tui_tools.py`

### 2. Compose — `b2_get_prompt`

- Input: prompt_id
- Output: full markdown content of the B2 prompt file
- Source: `~/mqobsidian/_prompts/saved-prompts-md-export/`
- Owner: `mq_agent/tools/b2tui_tools.py` (read-only filesystem access)

### 3. Review — `mq-mcp` (optional)

- Input: repo context, prompt content
- Output: structured review findings
- Boundary: **read-only** — mq-agent calls `review_repo` via `MCPBridge.call_tool()`,
  it never writes or mutates mq-mcp state
- Degradation: if mq-mcp is offline, this step is skipped without error

### 4. Output — `b2_log_run`

- Input: prompt_id, context, review result preview
- Output: appended JSONL line in `~/.b2tui_history.jsonl`
- Owner: `mq_agent/tools/b2tui_tools.py`

---

## CLI surface

```
mq-agent b2 run "topic"           # full workflow
mq-agent b2 run "topic" --route review  # force a specific route
mq-agent b2 route "topic"         # show routing decision only
mq-agent b2 prompt 02.11          # print prompt content
mq-agent b2 list                  # list all prompts
mq-agent b2 history               # recent runs
```

## Task-based invocation

```
mq-agent task run tasks/b2_workflow.yaml
```

The YAML workflow (`tasks/b2_workflow.yaml`) is the declarative form of the
same pipeline, usable in swarm and automated contexts.

---

## Boundaries

| Concern | Owner | Boundary |
|---|---|---|
| Prompt library | `mq_agent/tools/b2tui_tools.py` | read-only filesystem |
| Route logic | `mq_agent/tools/b2tui_tools.py` | pure function, no I/O |
| History write | `mq_agent/tools/b2tui_tools.py` | append-only JSONL |
| Review logic | `mq-mcp` | mq-agent is caller only |
| Review write | `mq-mcp` internal | mq-agent never writes to mq-mcp |

---

## History schema

Each `b2_log_run` call appends one JSONL line:

```json
{
  "timestamp": "2026-06-09T12:00:00+00:00",
  "prompt_id": "02.11",
  "prompt_name": "Integration Architecture Blueprint",
  "category": "Architecture",
  "context": "design a microservice gateway",
  "result_preview": "...",
  "source": "mq-agent"
}
```

`source` is `"mq-agent"` for runs from this workflow; `"b2tui"` for direct
b2tui CLI runs. This allows history to be filtered by origin.
