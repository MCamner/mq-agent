---
name: mq-worktree-safe
description: Creates an isolated Git worktree for MQ repo work with ignored-directory verification, clean-baseline checks, and approval gates. Use before implementation, refactors, dependency updates, risky experiments, or cross-repo MQ changes.
---

# MQ Worktree Safe

Use this skill when work should not disturb the current checkout.

## MQ principle

Isolate first, verify baseline, then work. Never let temporary worktree folders become tracked repo content.

## Repo boundary

- `mq-agent`: use for planning branches and workflow experiments.
- `mq-mcp`: use for execution/runtime/tool changes.
- `mqobsidian`: use for context contract, generator, and published surface work.
- `repo-signal`: use for readiness/security checks.
- `mq-hal`: use for status, runbook, and operator-summary changes.

## Workflow

### 1. Inspect current repo

```bash
git rev-parse --show-toplevel
git status --short --branch
git branch --show-current
```

If the tree is dirty, summarize changed files and ask whether to proceed, stash, or use a separate worktree from the current state.

### 2. Choose worktree directory

Use this priority:

1. Existing `.worktrees/`
2. Existing `worktrees/`
3. Repo guidance in `CLAUDE.md`, `AGENTS.md`, or `.mq/context/*`
4. Ask the user

Preferred MQ default:

```text
.worktrees/<branch-name>
```

### 3. Verify local worktree folder is ignored

For project-local worktrees:

```bash
git check-ignore -q .worktrees || git check-ignore -q worktrees
```

If not ignored:

1. Show the required `.gitignore` addition.
2. Ask for approval before editing `.gitignore`.
3. Commit the `.gitignore` fix only after explicit approval.

### 4. Create worktree

```bash
project="$(basename "$(git rev-parse --show-toplevel)")"
branch="feature/<short-purpose>"
git worktree add ".worktrees/${branch#feature/}" -b "$branch"
cd ".worktrees/${branch#feature/}"
```

Use repo-specific branch names, for example:

```text
feature/mq-context-export
fix/public-safe-paths
chore/dependabot-review
```

### 5. Bootstrap project

Auto-detect, do not assume:

```bash
[ -f package.json ] && npm install
[ -f pyproject.toml ] && python -m pip install -e .
[ -f requirements.txt ] && python -m pip install -r requirements.txt
[ -f Cargo.toml ] && cargo build
[ -f go.mod ] && go mod download
```

### 6. Verify clean baseline

Run the repo’s lightest reliable gate first:

```bash
git status --short
```

Then choose relevant checks:

```bash
npm test
pytest
cargo test
go test ./...
python -m compileall .
```

If checks fail before work starts, report this as **pre-existing baseline failure** and ask before continuing.

## Output format

```md
## Worktree ready

- Repo: <repo-name>
- Branch: <branch>
- Path: <path>
- Baseline: pass/fail/not available
- Notes: <important constraints>
```

## Guardrails

Never:

- create a local worktree folder without ignore verification
- hide baseline failures
- delete or prune worktrees without explicit approval
- merge, push, or commit without explicit approval
- hardcode `/Users/...` paths

Always:

- keep paths repo-relative or use `$MQ_OBSIDIAN_DIR`
- report dirty state before work
- use one logical branch per logical change
