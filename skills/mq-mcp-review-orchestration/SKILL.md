---
name: mq-mcp-review-orchestration
description: Use when adding or changing mq-agent workflows that route review, risk, security, architecture, or repo-aware cognition work through mq-mcp.
---

# mq-mcp Review Orchestration

Use this skill when mq-agent coordinates review workflows backed by mq-mcp.

## When to use

- Adding or changing mq-agent workflows that route review, risk, security, or architecture requests to mq-mcp
- Maintaining the orchestration boundary between mq-agent and mq-mcp review tools
- Debugging why a review pipeline is not calling the right mq-mcp tool
- Adding dry-run, JSON output, or model-selection behavior to review commands

## When not to use

- Implementing review logic, severity scoring, or architecture reasoning — those belong in mq-mcp
- General mq-agent CLI changes unrelated to review orchestration
- Debugging mq-mcp tool behavior — use the mq-mcp `review-runtime-maintainer` skill

## Evals

### Should trigger

* "review this file for security issues"
* "what's the risk in this diff?"
* "run an architecture review on this PR"
* "route this review through mq-mcp and show me the findings"

### Should not trigger

* "audit the whole repo for health" → use `repo-audit`
* "is this release-ready?" → use `release-readiness`
* "analyze this screenshot" → use `visual-analysis`
* "diagnose a CI failure" → use `ci-diagnosis`

## Boundary

mq-agent owns orchestration, session state, CLI/TUI presentation, dry-run planning, model-selection policy and execution pipelines.

mq-agent must not implement its own review engine, semantic retrieval runtime, architecture reasoner, severity engine, or review-memory store.

## Files To Inspect

- `mq_agent/core/`
- `mq_agent/tools/`
- `mq_agent/cli/`
- `tasks/`
- `docs/ARCHITECTURE.md`
- `docs/COMMAND_SURFACE.md`
- `docs/ROADMAP.md`
- `tests/test_orchestration_contract.py`
- tests covering MCP bridge or task runner behavior

## Workflow Rules

- Route `review`, `risk`, `security` and `architecture` modes to mq-mcp review tools.
- Preserve mq-mcp severity labels and finding text; do not reinterpret findings in mq-agent.
- Keep dry-run support for review pipelines before execution.
- Keep JSON output stable when review results are intended for downstream tools.
- Show missing mq-mcp or failed tool calls as clear orchestration failures.

## Verification

```bash
python -m pytest tests/test_orchestration_contract.py -q
python -m pytest -q
./release-check.sh
```

For integration changes, add a smoke test that proves mq-agent can call the expected mq-mcp review tool or can fail safely when mq-mcp is unavailable.
