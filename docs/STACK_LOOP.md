# Stack Loop

`mq-agent stack loop` is the first v1.20 autonomous-stack surface.

It is intentionally read-only: the command observes the operator dashboard,
chooses the highest-priority next action, and returns a bounded loop plan. It
does not mutate repos, write brain notes, run release commands or switch model
profiles.

## Commands

```bash
mq-agent stack loop          # render the loop plan
mq-agent stack loop --json   # machine-readable plan
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

* `execution` is `read-only`
* `writes_enabled` is always `false`
* writes require explicit future approval
* rollback behaviour must exist before execution is enabled

## Rollback behaviour

The v1.20 preview uses a preflight-only rollback strategy: no repository,
brain, model-profile or process mutation is attempted, so there is nothing to
roll back after the plan is rendered.

Non-dry-run mode remains blocked. Future v1.20 work can add approved execution
only after command-specific rollback behaviour is implemented and tested.
