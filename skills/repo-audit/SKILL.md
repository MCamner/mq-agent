---
name: repo-audit
description: Use when auditing a repository for code quality, git state, structure, and test coverage. Read-only, safe to run anywhere.
---

# Repo Audit

Produce a structured read-only audit of a repository using the Planner→Executor→Verifier loop.

## When to use

- Asked to audit, assess, or summarize the state of a single repository
- Before planning work in an unfamiliar repo
- Verifying repo hygiene (tests, CI, docs presence) without changing anything

## When not to use

- Scoring README/publish readiness with repo-signal — use `signal-assessment`
- Multi-repo stack health — use `stack-operations` (`mq-agent stack sweep`)
- Release validation — use `release-readiness`
- Diagnosing a failing CI run — use `ci-diagnosis`

## Evals

### Should trigger

- "audit this repo"
- "what state is this codebase in?"
- "check repo hygiene before we start"
- "summarize structure, tests, and CI for this repo"

### Should not trigger

- "score the README" → use `signal-assessment`
- "health across all MQ repos" → use `stack-operations`
- "is it ready to release?" → use `release-readiness`
- "why is CI red?" → use `ci-diagnosis`

Always inspect:

- git status and recent log
- repo structure and entry points
- README and documentation presence
- test coverage
- CI configuration
- tool registry availability

Check for:

- uncommitted changes
- missing tests
- broken or missing README
- stale documentation
- no CI workflow
- large untracked files

Prefer:

- read-only tools only
- concise step descriptions
- verified results before reporting

Never:

- modify files
- run destructive commands
- assume test results without running them
