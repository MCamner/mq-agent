# Roadmap

## v0.1.x — Foundation hardening

Stabilise and polish the initial terminal-native agent foundation.

- [ ] Improve CLI reliability and error messages
- [ ] Expand test coverage (target: 50+ tests)
- [ ] Improve JSON output schema consistency
- [ ] Harden safety checks and blocked pattern list
- [ ] Add `mq-agent version` and structured version file
- [ ] Shell completion (Typer built-in)
- [ ] TUI: async command execution so UI doesn't freeze

## v0.2.0 — Repo intelligence

Integrate repository awareness via repo-signal.

- [ ] repo-signal integration: pull repo health scores into audit output
- [ ] Repository audit scoring (0–100 health score)
- [ ] Release readiness scoring with blocking criteria
- [ ] Semantic repository memory via OpenAI vector stores
- [ ] `mq-agent audit --score` — output structured audit score

## v0.3.0 — Local tool orchestration

Expand local tool routing via mq-mcp.

- [ ] mq-mcp full integration (tool discovery, routing, result handling)
- [ ] Local MCP tool bridge with auto-discovery
- [ ] Richer tool metadata (description, schema, examples)
- [ ] `mq-agent tools --describe <tool>` — show tool schema and examples
- [ ] Safer shell execution with sandboxing options

## v0.4.0 — HAL integration

Connect to mq-hal for local reasoning.

- [ ] mq-hal reasoning layer integration
- [ ] Local model fallback (when OpenAI is unavailable)
- [ ] Hybrid planner: local first, cloud on escalation
- [ ] mqlaunch as unified command surface

## Later

- Autonomous loop mode (explicit opt-in, strict safety)
- Browser control (Playwright bridge)
- Multi-agent workflows
- Deeper mqlaunch integration
- Distributed execution
