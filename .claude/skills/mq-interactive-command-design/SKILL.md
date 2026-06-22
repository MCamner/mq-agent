---
name: mq-interactive-command-design
description: Designs MQ interactive commands and launcher flows with clear choices, safe defaults, validation loops, and approval gates. Use for mqlaunch, mq-agent command flows, or guided repo operations.
---

# MQ Interactive Command Design

Use this skill when designing commands that need user choices instead of simple arguments.

## MQ principle

Interactive flows should reduce ambiguity, not create menus for everything.

## Use interaction when

- the user must choose between real trade-offs
- action changes repo state
- setup depends on environment
- the command can affect credentials, publishing, CI, or generated files
- multiple repos or modes are possible

Use simple arguments when:

- the input is a known path/name/flag
- the workflow should be scriptable
- no explanation is needed

## MQ command question shape

Use 2–4 options per question.

```md
Question: "Which MQ repo should own this change?"
Header: "Owner repo"
Options:
- mqobsidian — context contracts, generators, published context surfaces
- mq-agent — planning, routing, workflow orchestration
- mq-mcp — runtime tools, safety metadata, execution boundaries
- repo-signal — readiness, security and public-safe scoring
```

## Common MQ patterns

### Pattern 1: Owner repo selection

Ask when a task could land in multiple repos.

```md
Question: "Where should this change live?"
Header: "Repo"
Options:
- mqobsidian — source of context and generators
- mq-agent — planner/router behavior
- mq-mcp — executable tool/runtime behavior
- mq-hal — operator status/runbook surface
```

### Pattern 2: Approval gate

Use before irreversible actions.

```md
Question: "Approve this action?"
Header: "Approve"
Options:
- Yes — run the exact command shown
- No — stop without changes
- Modify — adjust the command or scope first
```

### Pattern 3: Public boundary

Use before publishing generated files.

```md
Question: "Where will this output be published?"
Header: "Boundary"
Options:
- Private only — local/private repo output
- Public repo — must pass public-safe scan
- Website/blog — sanitize paths and secrets, check tone/docs
```

### Pattern 4: Execution mode

```md
Question: "How should MQ execute this plan?"
Header: "Mode"
Options:
- Dry run — inspect and report only
- Guided — ask before each write
- Approved batch — execute approved file writes only
```

## Validation loop

After collecting choices:

1. Show summary.
2. Validate compatibility.
3. Show exact files/commands affected.
4. Ask for final approval before action.

```md
## Planned action

- Repo: <repo>
- Mode: <dry-run/guided/batch>
- Files: <files>
- Commands: <commands>
- Risk: <low/medium/high>

Proceed? Yes/No/Modify
```

## Good defaults

- default to dry-run for security/dependency/publication commands
- default to `.worktrees/` for isolated work
- default to no push/merge
- default to `$MQ_OBSIDIAN_DIR` for Obsidian paths

## Guardrails

Never:

- ask more than four questions at once
- hide the exact command that will run
- use interaction to bypass approval
- make destructive action the default
- mix repo ownership in one vague option
