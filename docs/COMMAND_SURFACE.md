# Command Surface

This file is the canonical command-count reference for `mq-agent` v1.0.0.
README, release notes, GitHub Pages and integration docs should link here
instead of redefining command counts in prose.

## System Layers

```text
mqlaunch -> mq-agent -> mq-mcp / mq-hal / repo-signal
```

| Layer | Role |
|---|---|
| `mqlaunch` | Human terminal entrypoint — menus and shortcuts only |
| `mq-agent` | Orchestration: planning, safety gates, tool routing, verification |
| `mq-mcp` | Execution runtime: review engine, architecture memory, 66 MCP tools |
| `repo-signal` | Repository intelligence: quality, publish-readiness, symbol exports |
| `mq-hal` | Observability: runtime health, model health, status summaries |

`mq-agent mcp *` commands must respect mq-mcp safety classes (A/B/C/D) and
profiles. Class C/D tools always require explicit `--approve`. mq-agent must
not reimplement mq-mcp review logic or architecture reasoning locally.

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

## Review Commands

Review commands are orchestration-only. mq-agent calls mq-mcp review tools and
renders the returned findings without changing severity labels or implementing
local review heuristics.

| Command | Needs mq-mcp | Notes |
|---|---:|---|
| `mq-agent review file <path>` | yes | Calls mq-mcp `review_file` |
| `mq-agent review file <path> --json` | yes | Raw mq-mcp JSON result |
| `mq-agent review diff` | yes | Calls mq-mcp `review_diff` |
| `mq-agent review repo [path]` | yes | Calls mq-mcp `review_repo` |
| `mq-agent review * --security` | yes | Passes `security=true` to mq-mcp |
| `mq-agent review * --architecture` | yes | Passes `architecture=true` to mq-mcp |
| `mq-agent review * --architecture-image <path>` | mq-image-analyze + mq-mcp | Observes image, then passes visual context to architecture review |
| `mq-agent review * --visual <path>` | mq-image-analyze + mq-mcp | Alias for `--architecture-image` |
| `mq-agent review * --risk` | yes | Requires installed mq-mcp `risk_review_*` tools |
| `mq-agent review * --fast` | yes | Prefer Class A tools; mq-mcp handles routing |
| `mq-agent review * --dry-run` | no | Show what would be called, no execution |
| `mq-agent learn status` | yes | Check mq-mcp learn system availability |
| `mq-agent learn search <query>` | yes | Search mq-mcp learned review patterns |
| `mq-agent learn explain <pattern-id>` | yes | Fetch pattern explanation from mq-mcp |

## Memory Commands

| Command | Needs vector store | Notes |
|---|---:|---|
| `mq-agent memory status` | no | Reports vector store ID and repo-signal availability |
| `mq-agent memory status --json` | no | Machine-readable status output |
| `mq-agent memory doctor` | no | Diagnose environment with actionable fixes |
| `mq-agent memory doctor --json` | no | Machine-readable diagnostics |
| `mq-agent memory build .` | no | Dry-run preview of semantic upload (safe default) |
| `mq-agent memory build . --no-dry-run` | yes | Upload semantic memory |
| `mq-agent memory refresh . --approve` | yes | Upload with explicit approval gate |
| `mq-agent memory search <query>` | yes | Search mq-mcp semantic memory (requires mq-mcp v1.4.0+) |
| `mq-agent memory search <query> --json` | yes | Raw mq-mcp JSON result |
| `mq-agent memory store <key> <value> --approve` | yes | Store item in mq-mcp semantic memory (Class C write) |
| `mq-agent memory store <key> <value> --dry-run` | no | Preview without writing |

## MCP Commands

| Command | Needs MCP server | Notes |
|---|---:|---|
| `mq-agent mcp status` | no | Reachability, tool counts, contract freshness, semantic memory count |
| `mq-agent mcp tools` | no | List MCP tools with safety classes |
| `mq-agent run-tool <name>` | yes | Execute a local MCP tool through safety gates |
| `mq-agent run-tool <name> --dry-run` | no | Preview without contacting mq-mcp |
| `mq-agent run-tool <name> --arg k=v` | yes | Pass tool arguments |
| `mq-agent run-tool <name> --approve` | yes | Allow write-capable or subprocess tools |
| `mq-agent run-tool <name> --dangerous` | yes | Allow dangerous delete/remove class tools |
| `mq-agent run-tool observe_architecture --arg image_path=...` | mq-image-analyze | Visual architecture observation context |
| `mq-agent run-tool image_ocr --arg image_path=...` | mq-image-analyze | OCR context from image-derived text |

## Browser Commands

All browser commands are read-only (GET requests only). No credentials, no form submission.

| Command | Needs network | Notes |
|---|---:|---|
| `mq-agent browser inspect <url>` | yes | Structured URL metadata: title, h1/h2, links, word count |
| `mq-agent browser inspect <url> --json` | yes | Machine-readable metadata |
| `mq-agent browser summarize <url>` | yes | Plain-text content summary |
| `mq-agent browser summarize <url> --json` | yes | Machine-readable summary |
| `mq-agent browser verify-release <url>` | yes | Verify release page fields |
| `mq-agent browser verify-release <url> --tag v0.7.0` | yes | Also check expected version tag |
| `mq-agent browser verify-release <url> --json` | yes | Machine-readable verification result |

## Task Commands

| Command | Notes |
|---|---|
| `mq-agent task list` | List available YAML task workflow files |
| `mq-agent task list --json` | Machine-readable task list |
| `mq-agent task run <name>` | Execute a declarative YAML workflow |
| `mq-agent task run <name> --dry-run` | Preview steps without execution |
| `mq-agent task run <name> --json` | Machine-readable step results |

## Skill Commands

| Command | Needs API key | Notes |
|---|---:|---|
| `mq-agent skill list [path]` | no | Discover repo-local `SKILLS.md` metadata; read-only |
| `mq-agent skill list [path] --json` | no | Machine-readable `mq.skill_index.v1` discovery output |

## Swarm Commands

Each swarm runs multiple agents in sequence with declared safety contracts.

| Command | Needs API key | Notes |
|---|---:|---|
| `mq-agent swarm list` | no | List swarm configs with agents and safety classes |
| `mq-agent swarm list --json` | no | Machine-readable |
| `mq-agent swarm plan <config>` | no | Show agents that would run — no execution |
| `mq-agent swarm plan <config> --json` | no | Machine-readable plan |
| `mq-agent swarm run <config> [path]` | yes | Execute swarm, unified report |
| `mq-agent swarm run <config> [path] --dry-run` | no | Preview without execution |
| `mq-agent swarm run <config> [path] --approve` | yes | Allow write-capable agents |
| `mq-agent swarm run <config> [path] --json` | yes | Machine-readable results |
| `mq-agent swarm audit [path]` | yes | Shorthand: audit + signal + docs |
| `mq-agent swarm audit [path] --dry-run` | no | Preview |
| `mq-agent swarm release-check [path]` | yes | Shorthand: CI + audit + release |
| `mq-agent swarm release-check [path] --approve` | yes | Enable release agent |

### Built-in swarm configs

| Config | Agents | Approve needed? |
|---|---|---|
| `audit` | audit + signal + docs | no |
| `release-check` | ci + audit + release | yes (for release agent) |
| `ci` | ci + audit | no |

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
