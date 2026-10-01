# Feedback Engine F1 Operator Surface Implementation Plan

## Goal

Make F0 feedback evidence inspectable through a stable, read-only CLI without
starting shadow experiments or deriving comparison verdicts.

## Owner repo

`mq-agent`

## Secondary repos

None in F1.

## Architecture boundary

- `mq-agent` owns feedback runtime state, report contracts and CLI views.
- `mq-mcp` integration remains F5.
- `mqobsidian` remains the durable-memory and promotion authority.
- `mq-hal` remains a later read-only consumer.
- F1 must not execute tasks, retrieve candidate context, compare strategies or
  activate policy.

## Non-goals

- No `feedback run`.
- No `mq.feedback-comparison.v1` or `mq.feedback-candidate.v1`.
- No candidate-better/worse verdict.
- No purge command in this read-only phase.
- No cross-repo changes.

## Approval gates

- File writes are approved by the operator's request to build the next step.
- Work stays on `feat/feedback-engine-f1` and is reviewed through a PR.
- Merge only after the full repository gate is green.
- No deletion or settings changes.

## Test gates

- Focused feedback view/CLI tests.
- Full pytest.
- Ruff and mypy.
- Docs consistency and generated command-reference parity.
- Wheel/install smoke.
- Stack contract/release gates.
- macOS canonical release gate.

## Rollback

Revert the F1 PR. F1 reads F0 evidence only and adds no new production write
path, so rollback does not mutate or invalidate stored feedback history.

## Read-only invariant

Every F1 command must be observational. Reading an absent store must not create
`~/.mq/feedback`, `runs/`, or a lock file. Existing writers keep the
exclusive lock; readers take a shared lock only when the lock file already
exists.

## Report contract

F1 introduces `mq.feedback-report.v1` as the stable aggregate surface. It
reports measured record counts and coverage, while metrics not produced until
F2/F3 are explicit `unavailable` values rather than invented zeroes.

### Task 1 — Read-only history access

#### Files

- Modify: `mq_agent/feedback/store.py`
- Modify: `mq_agent/feedback/__init__.py`

#### Requirements

- Add shared locking with no filesystem creation.
- Read current + rotated generations in append order.
- Preserve source file and line reference for each valid record and issue.
- Keep the existing current-generation `read_experiments` API compatible.

### Task 2 — F1 views and report contract

#### Files

- Create: `mq_agent/feedback/views.py`
- Create: `schemas/feedback_report.schema.json`
- Modify: `pyproject.toml`
- Modify: `.mq/repo-contract.json`

#### Requirements

- `status`: health, valid/invalid counts, newest timestamp, task classes,
  state coverage and degraded reasons.
- `inspect`: one immutable experiment chain with exact store reference;
  duplicate IDs are explicit degradation.
- `recent`: bounded newest-first history with deterministic ordering.
- `report`: task-class and day-window filtering under
  `mq.feedback-report.v1`.
- Missing F2/F3 metrics are `status=unavailable, value=null`, never zero.
- No derived winner/verdict in F1.

### Task 3 — CLI

#### Files

- Create: `mq_agent/feedback/cli.py`
- Modify: `mq_agent/main.py`
- Update generated command reference.

#### Commands

```bash
mq-agent feedback status
mq-agent feedback status --json
mq-agent feedback inspect <feedback-run-id>
mq-agent feedback recent
mq-agent feedback report --task-class repo-review --since 30d
```

All commands are read-only and human output is rendered directly from the same
payload returned by JSON mode.

### Task 4 — Tests and release surfaces

#### Files

- Create: `tests/test_feedback_views.py`
- Create: `tests/test_feedback_cli.py`
- Modify: `CHANGELOG.md`
- Modify: `ROADMAP.md` only after full CI proves the exit gate.

#### Exit gate

An operator can inspect storage health, list stable recent evidence, explain one
experiment's provenance, and produce a schema-valid aggregate report without
opening JSONL files or causing any filesystem write.
