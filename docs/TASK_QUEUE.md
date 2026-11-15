# Shared task queue

`mq-agent queue` coordinates local Codex and Claude tasks. Each task records a
goal, source repository and base commit, owner, status, advisory time budget,
worktree, verification and handoff history. Queue state belongs to mq-agent;
existing workflow runs and `verify-changes` receipts remain authoritative for
their own results.

The queue never starts an agent, runs a workflow or grants execution approval.

## Start and resume work

```bash
mq-agent queue add "Fix the CI failure" --repo . --budget-minutes 60 --json
mq-agent queue claim TASK_ID --owner codex --json
mq-agent queue show TASK_ID --json
```

Replace `TASK_ID` with the id returned by `add`. `claim` creates a separate linked
Git worktree and branch at the task's base commit. Use the returned `worktree`
path for edits and checks. Uncommitted changes in the source checkout are not
copied. `--worktree PATH` can select an existing separate linked worktree of the
same repository; the queue validates it before assigning ownership.

The reservation is cooperative: commands using this shared queue cannot assign
one worktree to two active tasks, but the queue cannot stop an editor or agent
that bypasses it. Use one shared queue state directory for collaborating agents.

```bash
mq-agent queue pause TASK_ID --owner codex
mq-agent queue claim TASK_ID --owner codex
mq-agent queue list
```

Pausing retains the owner and worktree reservation. State survives process exit;
resume claims the same task and worktree. The time budget is an operator-facing
planning limit, not a timer or automatic termination rule.

## Link workflow results and complete

Run any relevant workflow separately against the task worktree. An optional
reference connects its saved state to the task without rerunning it:

```bash
mq-agent queue link-run TASK_ID RUN_ID --owner codex
mq-agent verify-changes WORKTREE --base BASE_COMMIT
mq-agent queue complete TASK_ID --owner codex --json
```

Use `worktree` and `base_commit` from `queue show`. The linked workflow must target
that worktree. Completion requires a current `PASS` receipt from `verify-changes`
against the task's base commit; missing, failed, incomplete or stale verification
cannot complete the task. Re-run verification after edits. `--plan` previews
checks and does not create a passing receipt. The worktree needs its own committed
`.mq/verification.json` with checks covering the task's changes.

## Hand work to another agent

```bash
mq-agent queue handoff TASK_ID --owner codex --to claude \
  --summary "Implemented the parser; inspect the recorded change overview" \
  --remaining "Review the edge cases and run the selected checks" --json
mq-agent queue show TASK_ID --json
mq-agent queue claim TASK_ID --owner claude --json
```

A handoff records completed and remaining work, the actual source worktree's
change identity, verification state and workflow reference. It grants no new
approval. Only the named receiving agent can accept it, in its own separate
worktree, starting at the sender's recorded HEAD. The sender's worktree
reservation remains until acceptance. Acceptance does not copy uncommitted edits
or merge branches: inspect the recorded source
worktree and deliberately transfer any changes needed in the receiving worktree.
The old worktree and handoff history remain available for review.
An existing receiving worktree must also start at the recorded HEAD. If the
sender changes its worktree after offering the handoff, acceptance is refused;
the sender can repeat `handoff` with an updated summary and remaining work.

An end-to-end Claude-to-Codex handoff is recorded in
[queue-handoff-acceptance-evidence.md](queue-handoff-acceptance-evidence.md).

## Cancel and recover

```bash
mq-agent queue cancel TASK_ID --owner codex
```

A queued, unowned task can be cancelled without `--owner`. Cancelling an owned
task requires its current owner label. Completion and cancellation release the
reservation; they never delete branches or worktrees. Inspect them and clean them
up separately when appropriate. Do not clear a reservation while its agent is
still writing.
If Git created a worktree but queue persistence failed, inspect the retained
worktree and branch. Retry with `claim --worktree PATH` to reserve it explicitly;
the queue does not delete it or silently reuse an existing default path.

The queue is local state under `${XDG_STATE_HOME:-$HOME/.local/state}/mq-agent/queue`,
next to existing workflow state. Owner labels coordinate callers; they are not
user authentication. SQLite transactions serialize ownership changes between
processes. No queue record is routing evidence, Feedback Engine evidence or a
durable-memory learning.

Commands return nonzero on invalid transitions, ownership conflicts or failed
verification. `--json` emits task data as JSON on success; errors go to stderr.
