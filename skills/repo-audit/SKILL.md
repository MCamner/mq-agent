---
name: repo-audit
description: Use when auditing a repository for code quality, git state, structure, and test coverage. Read-only, safe to run anywhere.
---

# Repo Audit

Goal:
Produce a structured read-only audit of a repository using the Planner→Executor→Verifier loop.

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
