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

Non-dry-run mode is blocked in this preview. Future v1.20 work can add
approved execution once contracts and rollback behaviour are explicit.
