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

## Evals

### Should trigger

* "audit this repo and give me a health report"
* "what's the overall code quality and safety risk here?"
* "run a full read-only audit of mq-mcp"
* "check this repo for drift, dead code, and missing tests"

### Should not trigger

* "is this repo ready to release?" → use `release-readiness`
* "review this diff for security issues" → use `mq-mcp-review-orchestration`
* "what's the repo signal score?" → use `signal-assessment`
* "diagnose a failing CI pipeline" → use `ci-diagnosis`

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
