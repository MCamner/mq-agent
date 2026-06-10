# mq-mcp Runtime Contract

**Version:** 1.0  
**Phase:** 3 (mq-agent bridge)  
**Status:** Active

---

## Purpose

This contract defines the boundary between `mq-agent` and `mq-mcp`.
It specifies what mq-agent is allowed to call, what it is not allowed to do,
and how the boundary is enforced.

---

## Boundary: mq-agent is a read-only caller

`mq-agent` treats `mq-mcp` as a **read-only review oracle**.

It MAY:

- Call `GET /health` to check availability
- Call `GET /tools` to discover available tools
- Call review tools via the MCP tool-call protocol (`POST /call`)
- Read tool contracts via `GET /tool-contracts`

It MUST NOT:

- Write, mutate, or delete any mq-mcp state
- Call write-side tools (e.g. `learn_store`, `learn_promote`)
- Pass mq-mcp credentials or secrets to other systems
- Start or stop the mq-mcp server on behalf of workflows (only the operator may do this)

---

## Allowed tool calls from mq-agent

| Tool | Endpoint | Direction |
|---|---|---|
| `review_repo` | `POST /call` | mq-agent → mq-mcp (read) |
| `review_diff` | `POST /call` | mq-agent → mq-mcp (read) |
| `review_file` | `POST /call` | mq-agent → mq-mcp (read) |
| `learn_status` | `POST /call` | mq-agent → mq-mcp (read) |
| `learn_search` | `POST /call` | mq-agent → mq-mcp (read) |
| `learn_explain` | `POST /call` | mq-agent → mq-mcp (read) |

Any tool that **stores, promotes, or mutates** review patterns is outside this boundary.
Those are operator-level tools called directly by the user, not by mq-agent.

---

## Degradation

mq-mcp is optional for the B2 workflow:

- If `GET /health` fails → review pass is skipped, workflow continues
- If a review tool call fails → error is surfaced to the user, not silently swallowed
- If mq-mcp is unavailable → mq-agent logs the skip in the run history entry

---

## Transport

- Protocol: HTTP (not stdio MCP) — `MCPBridge` connects to `http://localhost:8765`
- Timeout: 2s for health check, 30s for tool calls
- Auth: none (local-only server, not exposed externally)

---

## Caller identity

Runs from the B2 workflow set `"source": "mq-agent"` in the history log.
This allows post-hoc filtering of runs that went through the mq-mcp review pass
vs. direct b2tui calls.

---

## Upgrade path

When `mq-mcp` exposes a structured context endpoint (planned Phase 4+),
`mq-agent` may call it to retrieve project-specific prompt context.
That call will remain read-only under this contract.
