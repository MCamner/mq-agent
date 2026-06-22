---
name: mq-writing-plans
description: Writes MQ implementation plans with exact files, repo ownership, gates, tests, rollback notes, and small executable tasks. Use before multi-step MQ changes, cross-repo work, roadmap implementation, or agent handoff.
---

# MQ Writing Plans

Use this skill before touching code when the task has more than one step or affects more than one MQ repo.

## MQ principle

A plan is a contract: repo owner, files, gates, tests, rollback, and why the change exists.

## Save location

Prefer:

```text
docs/plans/YYYY-MM-DD-<short-name>.md
```

For mqobsidian-managed context plans:

```text
$MQ_OBSIDIAN_DIR/execution/plans/YYYY-MM-DD-<short-name>.md
```

Use `$MQ_OBSIDIAN_DIR` literally. Do not expand it into a private home path.

## Plan header

Every plan starts with:

```md
# <Feature or Fix> Implementation Plan

## Goal
<one sentence>

## Owner repo
<repo name>

## Secondary repos
<repo names or none>

## Architecture boundary
- mqobsidian owns context contracts, templates, generators, and published context surfaces.
- mq-agent owns planning, workflow routing, task decomposition, and agent handoff.
- mq-mcp owns execution tools, tool safety, and runtime boundaries.
- mq-hal owns status, operator summaries, release/runbook views.
- repo-signal owns publish readiness, security/readiness scoring, and repo health checks.

## Non-goals
- <what this plan will not change>

## Approval gates
- Before file writes: yes/no
- Before commit: yes/no
- Before push/merge: yes/no
- Before deletion/settings changes: yes/no

## Test gates
- <exact commands>

## Rollback
- <exact rollback or revert strategy>
```

## Task format

Each task must be small enough to review independently.

```md
### Task N: <name>

**Purpose:** <why this task exists>

**Files:**
- Create: `path/file.ext`
- Modify: `path/file.ext`
- Read-only reference: `path/file.ext`

**Steps:**
1. Read current file state.
2. Make the minimal change.
3. Run exact gate.
4. Summarize diff.
5. Ask before commit.

**Commands:**
```bash
<exact command>
```

**Expected result:**
<what should pass or change>

**Commit suggestion:**
`type(scope): imperative summary`

```

## Task sizing

Good task:

```text
Update mqobsidian generator to emit `$MQ_OBSIDIAN_DIR` in AGENTS.md templates.
```

Bad task:

```text
Fix context system.
```

## Required checks before finalizing plan

- Are repo boundaries explicit?
- Are all paths exact and portable?
- Does the plan avoid personal absolute paths?
- Are tests/gates executable?
- Is there a rollback path?
- Are write/commit/push approvals separated?

## Output format

```md
## Plan ready

- File: `docs/plans/YYYY-MM-DD-<name>.md`
- Owner repo: <repo>
- Tasks: <count>
- Gates: <summary>
- Recommended first task: <task>
```

## Guardrails

Never start implementation from the plan without explicit user approval.
