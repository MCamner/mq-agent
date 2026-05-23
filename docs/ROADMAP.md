# Roadmap

## Done

- Planner (OpenAI gpt-4o, structured JSON output)
- Executor (tool registry, dry-run, safety gate)
- Verifier (per-step result checking with gpt-4o-mini)
- Memory (session + persistent JSON)
- Safety modes (read-only / suggest / execute / dangerous)
- Git tools, shell tools, repo tools
- MCP bridge (mq-mcp over HTTP)
- Audit agent, Release agent, CI agent, Docs agent
- Signal agent (repo-signal + AI improvement plan)
- `mq-agent score` — instant README + publish score (no API key)
- `mq-agent doctor` — full environment check
- `mq-agent signal` — scored repo assessment with AI plan
- `mq-agent tui` — Textual dashboard
- JSON output and `--dry-run` on all commands
- Skills definitions (`SKILLS.md` + `skills/`)
- Command reference, safety contract, ecosystem docs
- GitHub Pages landing
- Install smoke test CI (no API key required)
- `python-dotenv` auto-load from `.env`
- 37 tests pass without OpenAI calls

## Done — v0.2.4 (docs sync)

- `docs/index.html` version badge corrected from v0.2.1 to v0.2.4
- `scripts/check-docs-consistency.sh` — version sync gate
- `release-check.sh` pre-release gate (tests + lint + docs consistency)
- CI docs-consistency step added to `tests.yml`

## Done — v0.3.0 (local tool orchestration)

- `mq_agent/tools/mcp_registry.py` — `MCPToolSpec` dataclass + name-prefix safety classification
- `mq-agent mcp status` — mq-mcp reachability + tool count by safety class
- `mq-agent mcp tools` — list discovered MCP tools with safety classes
- `mq-agent tools --describe <name>` — show tool metadata, schema and examples
- `mq-agent tools --mcp` — include MCP tools in built-in listing
- `mq-agent run-tool <tool>` — run an MCP tool through mq-agent safety gates
- MCP safety classes: read-only / write-capable / subprocess / dangerous / unknown
- Fail-closed: unknown blocked, write/subprocess require `--approve`, dangerous requires `--dangerous`
- Helpful "not reachable" error with startup instructions
- 70 tests (was 37) — all without OpenAI or mq-mcp required
- `docs/MCP_INTEGRATION.md` and `docs/TOOL_ROUTING.md`

## Done — v0.4.0 (mqlaunch integration)

- `mq-agent-menu.sh` — 12-item agent menu in mqlaunch (4 sections: repo analysis, AI commands, environment, MCP local tools)
- 3 prompt commands: `agent release-check`, `agent mcp-status`, `agent mcp-tools`
- `scripts/smoke-mqlaunch.sh` — smoke test: 8 commands verified without API key or live session
- `docs/MQLAUNCH_INTEGRATION.md` — bridge architecture and usage

## Next — v0.5.0 (autonomous loop mode)

- Opt-in autonomous loop with strict safety gates
- Loop supervisor: max steps, budget, kill switch
- `mq-agent loop "goal"` — runs until goal is met or limit hit
- `docs/AUTONOMOUS_MODE.md`

## Later

- Autonomous loop mode (explicit opt-in, strict safety gates)
- Browser control (Playwright bridge)
- Multi-agent workflows
- Semantic repository memory (OpenAI vector stores)
- Local model fallback (when OpenAI is unavailable)
- Hybrid planner (local first, cloud on escalation)
- Shell completion (Typer built-in)
- TUI async command execution
