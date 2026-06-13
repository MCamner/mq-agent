---
name: mq-mcp-review-orchestration
description: Use when adding or changing mq-agent workflows that route review, risk, security, architecture, or repo-aware cognition work through mq-mcp.
---

# mq-mcp Review Orchestration

Use this skill when mq-agent coordinates review workflows backed by mq-mcp.

## When to use

- Adding or changing `mq-agent review` (file/diff/repo) workflows
- Routing risk, security, or architecture cognition to mq-mcp tools
- Debugging orchestration failures between mq-agent and mq-mcp

## When not to use

- Changing the review engine itself (contracts, severity, memory) — mq-mcp's `review-runtime-maintainer`
- Stack gates and sweeps — use `stack-operations`
- CI failure diagnosis — use `ci-diagnosis`

## Evals

### Should trigger

- "mq-agent review diff should support --json"
- "route the security pass through mq-mcp"
- "review orchestration fails when mq-mcp is down"
- "add dry-run to the review pipeline"

### Should not trigger

- "severity parsing is wrong" → mq-mcp's `review-runtime-maintainer`
- "stack sweep scoring is off" → use `stack-operations`
- "CI is red" → use `ci-diagnosis`

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
