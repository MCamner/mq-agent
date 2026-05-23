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

## Next — v0.2.4 (in progress)

- `docs/index.html` version sync (was stuck at v0.2.1)
- `scripts/check-docs-consistency.sh` — catch version drift before release
- `release-check.sh` pre-release gate
- ROADMAP aligned with reality

## Next — v0.3.0 (mqlaunch integration)

- `mqlaunch agent` bridge commands: `doctor`, `score`, `audit`, `release-check`
- `docs/MQLAUNCH_INTEGRATION.md`
- Smoke test: mqlaunch can invoke mq-agent commands

## Later

- Autonomous loop mode (explicit opt-in, strict safety gates)
- Browser control (Playwright bridge)
- Multi-agent workflows
- Semantic repository memory (OpenAI vector stores)
- Local model fallback (when OpenAI is unavailable)
- Hybrid planner (local first, cloud on escalation)
- Shell completion (Typer built-in)
- TUI async command execution
