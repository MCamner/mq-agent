---
name: mq-subagent-driven-development
description: Executes MQ implementation plans task-by-task using isolated implementer/reviewer roles, spec-compliance review, code-quality review, and strict approval gates. Use after an MQ plan exists.
---

# MQ Subagent-Driven Development

Use this skill when an implementation plan exists and tasks can be completed one at a time.

## MQ principle

Fresh task context beats polluted context. Every task gets implementation, spec review, quality review, and explicit human approval before irreversible actions.

## Inputs

Required:

- Plan path
- Owner repo
- Current branch/worktree
- Test gates

Optional:

- Related issue/PR
- MQ context contract path
- Previous review notes

## Process

### 1. Read the plan once

Extract:

- task list
- owner repo
- touched files
- gates
- rollback
- approval points

Do not make subagents rediscover the whole plan. Give each role the exact task text and required context.

### 2. For each task

#### A. Implementer role

Give the implementer:

```md
You are implementing Task N only.
Stay inside owner repo boundary.
Do not change unrelated files.
Run the listed gate.
Return changed files, commands run, result, and unresolved questions.
```

The implementer must:

- read files first
- change only listed files unless justified
- run the smallest reliable test
- self-review the diff
- avoid committing unless the user explicitly approved commit for this task

#### B. Spec compliance review

Reviewer checks:

- Did the implementation satisfy the task?
- Did it add unrequested behavior?
- Did it respect repo ownership?
- Did it preserve public-safe path rules?
- Were exact gates run?

Result format:

```md
Spec review: pass/fail
Required fixes:
- <fix>
```

No code-quality review until spec review passes.

#### C. Code-quality review

Reviewer checks:

- simplicity
- test coverage
- maintainability
- error handling
- naming
- duplication
- security footguns

Result format:

```md
Quality review: pass/fail
Issues:
- Severity: blocker/high/medium/low
- File: path
- Fix: exact recommendation
```

### 3. Final review

After all tasks pass:

```bash
git status --short
git diff --stat
git diff
```

Summarize:

- completed tasks
- changed files
- tests run
- open risks
- recommended commit split

Ask before committing, pushing, merging, deleting branches, or pruning worktrees.

## Output format

```md
## MQ execution summary

| Task | Spec | Quality | Tests | Status |
|---|---|---|---|---|
| 1 | pass | pass | pass | ready |

## Changed files
- `path/file`

## Recommended commits
1. `type(scope): message`

## Approval needed
- Commit? yes/no
- Push? yes/no
```

## Guardrails

Never:

- run multiple implementers on the same files in parallel
- skip spec review
- skip quality review
- accept “close enough” on repo-boundary violations
- commit, push, merge, delete, or change settings without explicit approval
