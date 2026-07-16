# Stack Loop

`mq-agent stack loop` is the v1.20 autonomous-stack surface.

It is dry-run by default: the command observes the operator dashboard, chooses
the highest-priority next action, and returns a bounded loop plan. Approved
execution is limited to allowlisted actions with explicit rollback behaviour.

## Commands

```bash
mq-agent stack loop          # render the loop plan
mq-agent stack loop --json   # machine-readable plan
mq-agent stack loop --execute --approve
```

## Decisions

| Decision | Meaning |
| --- | --- |
| `idle` | Dashboard is ready; no action needed |
| `preview` | A safe preview command can be shown |
| `manual` | The next action needs operator judgement |

## Contract

Every loop plan includes a `contract` object using
`mq_stack_loop_plan.v1`. The schema is tracked at
`schemas/mq_stack_loop_plan.schema.json`.

Current contract rules:

* `execution` is `controlled`
* writes require both `--execute` and `--approve`
* only `truth-export` and `stack-release` are allowlisted
* rollback behaviour is required for every executable action

## Rollback behaviour

The v1.20 loop has command-specific rollback:

| Action | Execution | Rollback |
| --- | --- | --- |
| `truth-export` | writes the stack truth note | restores the previous file or deletes the created file on failure |
| `stack-release` | delegates to `mq-agent stack release --execute` | uses the existing stack-release rollback before commit and aborts on failed steps |

Execution is blocked unless `--approve` is present. Manual next actions remain
blocked even with approval.

## Audit history

Every approved execution attempt appends exactly one record to a local
append-only JSONL file. Failed executions are recorded too — the audit trail
covers attempts, not just successes.

| Property | Value |
| --- | --- |
| Location | `$MQ_AGENT_STATE_DIR/stack-loop-history.jsonl`, default `~/.mq-agent/` |
| Schema | `mq_stack_loop_audit.v1`, tracked at `schemas/mq_stack_loop_audit.schema.json` |
| Written by | `mq-agent` only |
| Read by | `mq-hal history` (read-only) |

What is never written:

* dry-run, preview, idle, and unapproved blocked calls write nothing
* records only exist for `approved: true` with `decision: preview`, because that
  is the only path that reaches execution

Retention and privacy:

* the file is local operator state, outside the repo, and is never committed
* records hold the action, outcome, repo name, and rollback status — no
  credentials, tokens, or file contents
* nothing rotates or expires the file automatically; deleting it is safe and
  loses only history. `mq-hal` renders the most recent entries.

Recovery:

* audit persistence never overwrites the execution result. If the append fails,
  the loop still reports what actually happened and returns
  `audit.recorded: false` with the error.
