---
name: repo-audit
description: Use when auditing a repository for code quality, git state, structure, and test coverage. Read-only, safe to run anywhere.
---

# Repo Audit

Goal:
Produce a structured read-only audit of a repository using the Planner→Executor→Verifier loop.

## When to use

- Auditing a repository for overall health, code quality, git state, or structure
- Getting a read-only overview before planning or implementing changes
- Checking test coverage, CI config, and documentation presence
- Pre-PR quality scan or onboarding context for an unfamiliar repo

## When not to use

- Making changes to a repo — use `repo-aware` for planning and implementation context
- Validating release readiness — use `release-readiness`
- Diagnosing CI failures — use `ci-diagnosis`
- Scoring README quality or publish readiness — use `signal-assessment`

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
