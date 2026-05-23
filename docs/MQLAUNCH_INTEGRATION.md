# mqlaunch Integration

`mq-agent` is accessible from `mqlaunch` without typing the full command path.
The integration is split between two files in the `macos-scripts` repo:

- `terminal/menus/mq-agent-menu.sh` — the 12-item agent menu module
- `terminal/menus/mq-main-menu.sh` — direct prompt commands at the top-level prompt

---

## How the bridge works

```
mqlaunch (sourced from mqlaunch.sh)
  └── sources mq-agent-menu.sh
        └── _run_agent() { (cd "$MQ_AGENT_BIN" && uv run mq-agent "$@") }
```

`MQ_AGENT_BIN` defaults to `$HOME/mq-agent`. Override via environment:

```bash
export MQ_AGENT_BIN=/path/to/mq-agent
```

---

## Agent menu (12 options)

Press `g` or type `agent` at the mqlaunch prompt to open the agent menu.

```
╔═══════════════════════════════════════════════╗
║  AI Agent Orchestrator  [mq-agent]            ║
╠═══════════════════════════════════════════════╣
║  REPO ANALYSIS  (no API key required)         ║
║  1. Score repository   2. Full signal         ║
║  3. Repo summary       4. List tools          ║
╠═══════════════════════════════════════════════╣
║  AI COMMANDS  (requires OPENAI_API_KEY)       ║
║  5. Audit repository   6. Signal + AI plan    ║
║  7. Release check      8. Diagnose CI         ║
╠═══════════════════════════════════════════════╣
║  ENVIRONMENT                                  ║
║  9. Doctor             10. TUI dashboard      ║
╠═══════════════════════════════════════════════╣
║  MCP LOCAL TOOLS  (requires mq-mcp on :8765)  ║
║  11. MCP status        12. MCP tools list     ║
╠═══════════════════════════════════════════════╣
║  b. Back                                      ║
╚═══════════════════════════════════════════════╝
```

| Option | Runs |
|--------|------|
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

---

## Direct prompt commands

Type these at the mqlaunch main prompt — no menu navigation needed:

| Prompt input | Runs |
|---|---|
| `agent score` | `mq-agent score .` |
| `agent audit` | `mq-agent audit .` |
| `agent doctor` | `mq-agent doctor` |
| `agent release-check` | `mq-agent release-check` |
| `agent mcp-status` | `mq-agent mcp status` |
| `agent mcp-tools` | `mq-agent mcp tools` |

---

## Smoke test

`scripts/smoke-mqlaunch.sh` verifies all mqlaunch-callable commands without a
live mqlaunch session or `OPENAI_API_KEY`:

```bash
bash scripts/smoke-mqlaunch.sh
```

Expected output:

```
=== mq-agent mqlaunch bridge smoke test ===

--- REPO ANALYSIS (no API key) ---
OK:   score .
OK:   repo-summary .
OK:   tools
OK:   tools --json

--- ENVIRONMENT ---
OK:   doctor

--- MCP LOCAL TOOLS (mq-mcp not required) ---
OK:   mcp status --json
OK:   tools --describe read_repo_file --json
OK:   run-tool read_repo_file --dry-run

=== All mqlaunch bridge checks passed ===
```

---

## Requirements

| Requirement | Needed for |
|---|---|
| `uv` on `$PATH` | All menu options |
| `mq-agent` installed in `$MQ_AGENT_BIN` | All menu options |
| `OPENAI_API_KEY` in environment | Options 5–8 (AI commands) |
| `mq-mcp` running on `:8765` | Options 11–12 (live MCP) |

Options 1–4, 9 and the smoke test run without an API key or mq-mcp.
