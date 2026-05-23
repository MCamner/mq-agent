# Command Surface

This file is the canonical command-count reference for `mq-agent` v0.4.1.
README, release notes, GitHub Pages and integration docs should link here
instead of redefining command counts in prose.

## System Layers

```text
mqlaunch -> mq-agent -> mq-hal / mq-mcp / repo-signal
```

| Layer | Role |
|---|---|
| `mqlaunch` | Command surface and terminal entrypoint |
| `mq-agent` | Planning, safety gates, tool routing and verification |
| `repo-signal` | Repository quality and publish-readiness checks |
| `mq-mcp` | Local MCP tool layer |
| `mq-hal` | Reasoning, status and summaries |

## mq-agent Commands

| Command | Safety mode | Needs API key | Notes |
|---|---|---:|---|
| `mq-agent doctor` | read-only | no | Environment check |
| `mq-agent score .` | read-only | no | README score and publish checklist |
| `mq-agent repo-summary .` | read-only | no | Concise repository overview |
| `mq-agent tools` | read-only | no | List registered tools |
| `mq-agent tools --describe <name>` | read-only | no | Tool metadata and safety class |
| `mq-agent tools --mcp` | read-only | no | Include discovered MCP tools |
| `mq-agent audit .` | read-only | yes | AI-assisted repo audit |
| `mq-agent docs-audit .` | read-only | yes | Audit README, CHANGELOG, docstrings and /docs |
| `mq-agent signal .` | read-only | yes | repo-signal plus AI improvement plan |
| `mq-agent plan "goal"` | suggest | yes | Generate an execution plan |
| `mq-agent release-plan` | suggest | yes | Show the standard release plan |
| `mq-agent release-check` | suggest | yes | Validate release readiness |
| `mq-agent release-check --approve` | execute | yes | Execute release checks |
| `mq-agent fix-ci` | suggest | yes | Diagnose CI failures |
| `mq-agent run "cmd" --approve` | execute | no | Safe shell command execution |
| `mq-agent tui` | read-only | no | Textual dashboard |

## Memory Commands

| Command | Needs vector store | Notes |
|---|---:|---|
| `mq-agent memory status` | no | Reports vector store ID and repo-signal availability |
| `mq-agent memory build .` | no | Dry-run preview of semantic upload (safe default) |
| `mq-agent memory build . --no-dry-run` | yes | Upload semantic memory |
| `mq-agent memory refresh . --approve` | yes | Upload with explicit approval gate |

## MCP Commands

| Command | Needs mq-mcp | Notes |
|---|---:|---|
| `mq-agent mcp status` | no | Reachability and tool counts by safety class |
| `mq-agent mcp tools` | no | List MCP tools with safety classes |
| `mq-agent run-tool <name>` | yes | Execute a local MCP tool through safety gates |
| `mq-agent run-tool <name> --dry-run` | no | Preview without contacting mq-mcp |
| `mq-agent run-tool <name> --arg k=v` | yes | Pass tool arguments |
| `mq-agent run-tool <name> --approve` | yes | Allow write-capable or subprocess tools |
| `mq-agent run-tool <name> --dangerous` | yes | Allow dangerous delete/remove class tools |

## mqlaunch Agent Menu

The mqlaunch agent menu has exactly 12 items.

| Menu item | Runs |
|---:|---|
| 1 | `mq-agent score .` |
| 2 | `mq-agent signal .` |
| 3 | `mq-agent repo-summary .` |
| 4 | `mq-agent tools` |
| 5 | `mq-agent audit .` |
| 6 | `mq-agent signal .` |
| 7 | `mq-agent release-check` |
| 8 | `mq-agent fix-ci` |
| 9 | `mq-agent doctor` |
| 10 | `mq-agent tui` |
| 11 | `mq-agent mcp status` |
| 12 | `mq-agent mcp tools` |

## mqlaunch Direct Command Surface

`mqlaunch agent ...` exposes 6 direct subcommands plus the menu entrypoint.

| mqlaunch command | Runs |
|---|---|
| `mqlaunch agent` | Opens the mq-agent menu |
| `mqlaunch agent doctor` | `mq-agent doctor` |
| `mqlaunch agent score .` | `mq-agent score .` |
| `mqlaunch agent audit .` | `mq-agent audit .` |
| `mqlaunch agent release-check --dry-run` | `mq-agent release-check --dry-run` |
| `mqlaunch agent mcp-status` | `mq-agent mcp status` |
| `mqlaunch agent mcp-tools` | `mq-agent mcp tools` |

## mqlaunch Direct Prompt Commands

The mqlaunch top-level prompt exposes exactly 6 direct prompt commands.

| Prompt input | Runs |
|---|---|
| `agent score` | `mq-agent score .` |
| `agent audit` | `mq-agent audit .` |
| `agent doctor` | `mq-agent doctor` |
| `agent release-check` | `mq-agent release-check` |
| `agent mcp-status` | `mq-agent mcp status` |
| `agent mcp-tools` | `mq-agent mcp tools` |

## Smoke-Test Coverage

`scripts/smoke-mqlaunch.sh` verifies the `mqlaunch agent ...` bridge without
a live interactive session or OpenAI API call.

| Smoke check | Command path |
|---|---|
| doctor | `mqlaunch agent doctor` |
| score | `mqlaunch agent score .` |
| repo-summary | `mqlaunch agent repo-summary .` |
| mcp-status | `mqlaunch agent mcp-status` |

`release-check` is excluded from the smoke suite — it calls the AI planner and
requires `OPENAI_API_KEY`. `mq-mcp` does not need to be running for the
`mcp-status` smoke check; the command reports reachability cleanly.
