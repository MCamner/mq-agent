# Execution Efficiency Implementation Plan

## Goal

Expose measured runtime quality, resource use and measurement coverage separately,
and record actual tool invocations and model-reported usage where observable.

## Owner repo

mq-agent

## Secondary repos

None; mqlaunch/mq-hal integration remains a consumer follow-up.

## Architecture boundary

- mqobsidian owns context contracts, templates and durable knowledge.
- mq-agent owns execution telemetry, descriptive reports and workflow orchestration.
- mq-mcp owns tools, safety and backend execution.
- mq-hal owns operator summaries; repo-signal owns readiness scoring.
- Reuse `mq.execution-outcome.v1` and `mq.model-route-outcome.v1` unchanged.
- Reports cannot grant routing, policy, approval or memory-promotion rights.

## Non-goals

Model-price estimates, inferred rework, automatic routing, synthetic production
samples, external-agent telemetry import, release/version bumps or publishing.

## Approval gates

- Before file writes: authorized by the user's implementation request.
- Before commit: separate approval.
- Before push/merge: separate approval.
- Before deletion/settings changes: separate approval; none planned.

## Test gates

- `python -m pytest tests/test_execution_efficiency.py tests/test_execution_metrics.py -q`
- `python -m pytest tests/test_execution_outcome.py tests/test_execution_completeness.py tests/test_model_routing.py tests/test_core.py tests/test_workflow_observation.py tests/test_command_reference.py -q`
- Ruff and mypy on changed Python files.
- `python tools/generate_command_reference.py --check`
- `bash scripts/check-docs-consistency.sh`
- Read-only report against actual local stores; test producers use scratch stores.

## Rollback

Leave the isolated uncommitted feature worktree unused. No evidence migration,
policy activation or production-store writes are needed.

### Task 1: Runtime measurements

Create `mq_agent/core/execution_metrics.py` and `tests/test_execution_metrics.py`.
Modify planner/verifier model-call boundaries, executor and YAML task dispatch,
Ollama usage projection, standalone CLI outcome emission and swarm outcome emission.
Modify `mq_agent/tools/model_runtime.py` to invalidate known unobserved model calls;
workflow Runner/observer may report current actual dispatches.
Use scoped collectors, never emit nested execution records. A tool counter counts
actual dispatch attempts, including failures, not planned/skipped calls. Model
usage is emitted per field only when every observed call reports that field.
Unsupported/partially observed paths omit fields rather than inventing zero.
Keep absent cost and rework absent. Preserve exceptions and runtime behavior.

Exact runtime files: `mq_agent/core/planner.py`, `mq_agent/core/verification.py`,
`mq_agent/core/executor.py`, `mq_agent/core/task_runner.py`,
`mq_agent/core/local_llm.py`, `mq_agent/core/swarm.py`,
`mq_agent/workflows/runner.py`, `mq_agent/workflows/cli.py`,
`mq_agent/tools/model_runtime.py` and `mq_agent/main.py`.

### Task 2: Read-only efficiency report

Create `mq_agent/tools/execution_efficiency.py`, `tests/test_execution_efficiency.py`.
Read validated current/rotated execution history and existing routing records.
Handle malformed/duplicate/conflicting data explicitly and keep routing and
execution vocabularies/populations separate. Group execution summaries by task,
runtime, model and producer commit. Show measured counts/missing counts for each
resource metric, measured subtotals and full totals only with full coverage.
Keep declared PASS separate from measured complete successful executions; do not
claim model-answer quality or infer rework from retries. Missing data is null.

### Task 3: CLI, docs and review

Add `execution efficiency` to `mq_agent/main.py` and renderer
`mq_agent/cli/execution_efficiency.py`, including JSON and readable
quality/resource/coverage sections, time windows and separate source flags.
Update README, changelog, `docs/EXECUTION_EFFICIENCY.md`, generated command reference
and `.mq/verification.json`. New report shapes are derived mq-agent output; do
not alter shared schemas. Validate both local fixtures and read-only real stores.
Run spec review then code-quality review and resolve required findings.
