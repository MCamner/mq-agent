# Stack Truth Export

`mq-agent stack truth-export` writes a durable MQ stack truth note to mqobsidian.
`mq-agent stack export` is a backwards-compatible alias — both run the same export.

v1.13.0 upgrades the old stack export from a simple status table into a combined
truth snapshot built from two gates:

```bash
mq-agent stack contract-check --json
mq-agent stack release-check --json
```

The exported note is intended as long-term architecture memory, not a transient
CI log.

---

## Command

```bash
mq-agent stack truth-export
mq-agent stack export        # alias, same export
```

Default output:

```text
~/mqobsidian/memory/stack-truth/YYYY-MM-DD-mq-stack-truth.md
```

Custom output:

```bash
mq-agent stack truth-export --output ~/mqobsidian/memory/stack-truth/manual-stack-truth.md
```

Preview target path only:

```bash
mq-agent stack truth-export --dry-run
```

---

## What gets captured

The generated Markdown note includes:

- overall stack truth status
- contract gate result
- release gate result
- per-repo version
- per-repo contract status
- per-repo release status
- blockers
- warnings
- next action

Example structure:

```markdown
# MQ Stack Truth — 2026-06-11

## Result

Status: **READY**
Contract gate: `READY`
Release gate: `GO`

## Stack summary

| Repo | Version | Contract | Release | Notes |
|---|---:|---|---|---|
| mq-agent | 1.13.0 | READY | GO | — |

## Blockers

None.

## Warnings

None.

## Decisions

- Stack truth is derived from contract-check plus release-check.
- This note is a durable mqobsidian memory record, not a transient CI log.

## Next action

Keep stack gates green.
```

---

## Status model

| Contract gate | Release gate | Truth status |
|---|---|---|
| READY | GO | READY |
| NOT READY | GO | NOT READY |
| READY | NO-GO | NOT READY |
| NOT READY | NO-GO | NOT READY |

`READY` means the MQ stack contracts are valid and release blockers are absent.
Warnings may still be present and are written into the note.

---

## Why this exists

Before v1.13.0, stack gates answered:

```text
Is the stack OK right now?
```

Stack truth export answers:

```text
What did the stack know at this point in time, and what should we do next?
```

That makes the MQ stack more useful as an operating system for architecture work:
CI gives fast enforcement, while mqobsidian keeps durable memory.

---

## Related commands

```bash
mq-agent stack sweep
mq-agent stack report
mq-agent stack alert
mq-agent stack contract-check
mq-agent stack release-check
mq-agent stack truth-export   # alias: stack export
```
