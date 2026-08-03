# Model Routing Shadow Implementation Plan

## Goal

Add deterministic route inspection, advisory Ollama shadow evaluation, and
read-only outcome reporting for the v2.3.0 model-routing contract.

## Owner repo

mq-agent

## Secondary repos

None.

## Architecture boundary

- mq-agent owns task classification, routing policy, and escalation decisions.
- mq-mcp execution tools and mqobsidian persistence remain outside this PR.
- Ollama output is advisory and never becomes authoritative automatically.
- No command in this PR writes routing history or repository content.

## Non-goals

- MCP tools, HAL surfaces, mqlaunch entrypoints, or durable outcome storage.
- Automatic execution, automatic local approval, or model-generated commands.

## Approval gates

- Before file writes: approved by the request to run the next scope.
- Before commit: yes.
- Before push/merge: yes.
- Before deletion/settings changes: yes.

## Test gates

- `.venv/bin/pytest -q -p no:cacheprovider tests/test_model_routing.py`
- `.venv/bin/pytest -q -p no:cacheprovider`
- `.venv/bin/ruff check --no-cache .`
- `git diff --check`

## Rollback

Revert the PR; the Phase 0 schemas remain independently usable.

### Task 1: Define policy and inspection

**Files:**

- Create: `mq_agent/tools/model_routing.py`
- Create: `tests/test_model_routing.py`

Implement closed, deterministic classification and return a schema-valid route
decision without model calls or writes.

### Task 2: Add advisory shadow mode

**Files:**

- Modify: `mq_agent/tools/model_routing.py`
- Modify: `tests/test_model_routing.py`

Call the configured local model, validate its structured candidate, preserve the
authoritative agent, and return structured degraded/escalated outcomes.

### Task 3: Add read-only reporting and CLI

**Files:**

- Modify: `mq_agent/main.py`
- Modify: `mq_agent/tools/model_routing.py`
- Modify: `tests/test_model_routing.py`
- Modify: `docs/COMMAND_SURFACE.md`

Aggregate supplied verified outcomes without persisting them and expose
`mq-agent route inspect`, `shadow`, and `report` with human/JSON parity.

**Commit suggestion:**

`feat(routing): add advisory shadow routing commands`
