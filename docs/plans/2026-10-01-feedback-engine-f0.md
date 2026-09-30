# Feedback Engine F0 Implementation Plan

## Goal

Build the v1.30 feedback foundation so mq-agent can persist bounded,
schema-validated experiment evidence outside Git without changing production
execution.

## Owner repo

`mq-agent`

## Secondary repos

None in F0.

## Architecture boundary

- `mq-agent` owns feedback experiment records and runtime storage.
- `mq-mcp` remains the execution/MCP runtime; integration starts in F5.
- `mqobsidian` remains the durable-memory and promotion authority.
- `mq-hal` remains a read-only presentation consumer.
- `mqlaunch` / `macos-scripts` remain thin entrypoints.
- Atlas Core may evaluate bounded evidence later; it owns no feedback state.

## Non-goals

- No feedback CLI in F0.
- No active-versus-shadow execution.
- No comparison verdicts or candidate generation.
- No policy activation, routing changes or durable-memory promotion.
- No cross-repo implementation.

## Approval gates

- Before file writes: approved by the operator for this implementation.
- Before commit/push: changes stay on a feature branch and go through a PR.
- Before merge: required CI/check surface must be green.
- Before deletion/settings changes: not part of this plan.

## Test gates

- Focused feedback schema/store tests.
- Full pytest suite.
- Ruff and mypy through the repo test workflow.
- Install smoke and stack gate through PR CI.
- Markdownlint for this plan and roadmap changes.

## Rollback

Revert the F0 PR. The new store is additive and has no production consumer in
F0, so reverting code leaves existing execution, routing and memory behavior
unchanged. Runtime feedback state is disposable and can be purged separately.

## Trust boundary

| Source | Trust / egress rule | F0 treatment |
| --- | --- | --- |
| Local Git/repo state | Local runtime truth; may contain private paths or source bodies | Store IDs/ref/commit only; never source bodies |
| `mq.execution-outcome.v1` | Existing mq-agent execution evidence | Correlate by `execution_run_id`; do not duplicate outcome payload |
| OpenAI/vector retrieval | External backend when configured | Backend name may be recorded; query/prompt/content may not |
| NotebookLM/Drive corpus | External research material with existing provenance rules | Record source identity only; no copied corpus content |
| CodeGraph | Local derived structural evidence | Record source identity only |
| repo-signal | Read-only repo intelligence | Record source identity only |
| mq-mcp review | Runtime/review evidence | Record reference only; no raw tool output |
| Atlas Core | Optional evaluator later | No F0 calls; future findings must resolve to stored evidence |

F0 storage is local runtime evidence under `~/.mq/feedback` by default. It is
not Git truth and not mqobsidian durable memory.

## Initial metric inventory

F0 records experiment identity/provenance only. Metrics become comparison data
in F3; the inventory below prevents F0 from inventing values early.

| Signal | Current availability | Classification |
| --- | --- | --- |
| Execution run id/result/latency | `mq.execution-outcome.v1` | measured when emitted |
| Primary model | execution outcome when a model ran | measured/optional |
| Tool/retry/fallback counts | runtime-dependent | measured/optional; absent is unknown |
| Context source IDs | existing context/retrieval surfaces | measured when producer reports them |
| Context bytes/lines | producer-dependent | measured when explicitly counted |
| Context tokens | tokenizer/provider-dependent | optional; never estimated as measured |
| Retrieval latency | not one canonical metric yet | unavailable to F0 |
| Relevance/recall | requires labelled fixture or deterministic verifier | unavailable by default |
| Stale/contradicted rate | source-specific deterministic checks | optional future metric |
| External API/backend use | known from selected adapter | recordable as backend identity |

## Initial task class

The first experimental task class is `repo-review`. F0 does not claim that
its storage contract or later results prove behavior for release, CI, docs,
image, NotebookLM or other task classes.

## Task 1 — Contract and bounded builder

#### Files

- Create: `schemas/feedback_experiment.schema.json`
- Create: `mq_agent/feedback/models.py`
- Create: `mq_agent/feedback/__init__.py`
- Modify: `pyproject.toml`
- Modify: `.mq/repo-contract.json`

#### Requirements

- Stable id: `mq.feedback-experiment.v1`.
- Required experiment id, task class, repository identity, active/shadow
  strategy IDs, pinned Git ref+commit, evidence source IDs, state and timestamp.
- Optional correlation to the existing execution run.
- `additionalProperties: false`; no prompt, diff, source body or tool output.
- Bounded strings/arrays.
- Schema is force-included in the wheel.

## Task 2 — Append-only runtime store

#### Files

- Create: `mq_agent/feedback/store.py`

#### Requirements

- Default root `~/.mq/feedback`; override with `MQ_AGENT_FEEDBACK_DIR`.
- Serialize append/rotation with an OS file lock.
- Append with `O_APPEND`, flush and `fsync`.
- Rotate at a configurable bound; retain three prior generations.
- Redact known secret/token forms and private home paths before validation/write.
- Reject forbidden payload channels such as prompt/diff/stdout/source body.
- Read valid records while reporting corrupt/truncated lines.
- Provide bounded purge behavior for known feedback artifacts only.

## Task 3 — Test isolation and negative coverage

#### Files

- Create: `tests/test_feedback_store.py`
- Modify: `tests/conftest.py`

#### Requirements

- Tests always redirect `MQ_AGENT_FEEDBACK_DIR` away from the operator store.
- Validate schema and packaging.
- Prove append/rotation/concurrency.
- Prove a truncated line is reported without hiding valid history.
- Prove secrets/private paths are not persisted.
- Prove prompt/diff/source-body style fields are rejected.
- Prove purge leaves unrelated files untouched.

## Task 4 — Documentation/release surfaces

#### Files

- Modify: `CHANGELOG.md`
- Modify: `ROADMAP.md` only for F0 items actually proven by tests/CI.

#### Expected result

F0 is complete when one experiment can be built, correlated, sanitized,
validated, appended, read, rotated and safely purged without touching a Git
working tree or mqobsidian durable memory.
