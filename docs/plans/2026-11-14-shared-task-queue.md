# Shared Task Queue Implementation Plan

## Goal

Coordinate Codex and Claude tasks with durable ownership, isolated worktrees,
verified completion and explicit handoffs.

## Owner repo

mq-agent

## Secondary repos

None.

## Architecture boundary

- mqobsidian owns context contracts, templates and durable knowledge.
- mq-agent owns this local queue, workflow references and agent handoff.
- mq-mcp owns execution tools, tool safety and runtime boundaries.
- mq-hal owns operator summaries; repo-signal owns readiness scoring.
- Reuse WorkflowStore and verify-changes receipts; emit no routing/feedback evidence.

## Non-goals

Automatic agent execution, routing activation, merge, release, shared external
schemas, enforced filesystem permissions or automatic worktree deletion.

## Approval gates

- Before file writes: authorized by the user's implementation request.
- Before commit: yes, separate approval required.
- Before push/merge: yes, separate approval required.
- Before deletion/settings changes: yes; no such operations planned.

## Test gates

- `python -m pytest tests/test_task_queue.py tests/test_task_queue_cli.py -q`
- `python -m pytest tests/test_workflow_storage.py tests/test_workflow_checkpoint.py tests/test_verify_changes.py tests/test_command_reference.py -q`
- `python -m ruff check mq_agent/task_queue.py mq_agent/queue_cli.py tests/test_task_queue.py tests/test_task_queue_cli.py`
- `python tools/generate_command_reference.py --check`
- `bash scripts/check-docs-consistency.sh`

## Rollback

Leave this uncommitted feature worktree unused. No existing workflow state is
migrated. Runtime cancellation releases queue reservations but retains worktrees
and branches for deliberate inspection and cleanup.

### Task 1: Durable queue and worktree ownership

**Files:** Create `mq_agent/task_queue.py`, `tests/test_task_queue.py`.

1. Test persistence, real Git worktree creation, concurrent claims and conflicts.
2. Implement a SQLite transaction around ownership transitions; reject shared
   worktrees, wrong repositories and invalid state transitions.
3. Keep paused/handoff reservations until completion, cancellation or acceptance.
4. Record base commit, owner, status and an advisory time budget.

**Expected result:** independent processes cannot claim one task or worktree twice;
restart retains ownership. Never delete a worktree to recover a failed claim.

### Task 2: Verification and structured handoff

**Files:** Modify `mq_agent/task_queue.py`, `tests/test_task_queue.py`.
Read-only references: `mq_agent/workflows/storage.py`, `mq_agent/verify_changes.py`.

1. Link only workflow runs targeting the task worktree.
2. Save bounded handoff summaries, actual diff identity and current receipt status.
3. Require the named receiving agent and its own worktree when accepting handoff.
4. Complete only with a current PASS receipt against the task base commit.

**Expected result:** no arbitrary success claim, inherited approval or automatic
workflow execution; stale verification cannot complete a task.

### Task 3: CLI and discoverability

**Files:** Create `mq_agent/queue_cli.py`, `tests/test_task_queue_cli.py`,
`docs/TASK_QUEUE.md`. Modify `mq_agent/main.py`, `README.md`, `CHANGELOG.md`,
`tests/test_command_reference.py`, `docs/generated/Command-Reference.md`.
Modify `.mq/verification.json` so changed queue files select their regression tests.

1. Expose add/list/show/claim/pause/handoff/link-run/complete/cancel commands.
2. Test JSON, errors, ownership checks and help through the real Typer app.
3. Document command sequence, cooperative locking, budget semantics and recovery.
4. Regenerate the command reference and run the gates above.
5. Perform spec-compliance review, then code-quality review; fix required findings.

**Expected result:** a reviewable local CLI feature, with no commits or publication.
