---
name: ci-diagnosis
description: Use when CI is failing. Diagnoses test, lint, and type check failures and generates fix steps.
---

# CI Diagnosis

Identify the root cause of CI failures and generate concrete, safe fix steps.

## When to use

- A GitHub Actions run is red and the cause is unknown
- Tests, lint, or type checks pass locally but fail in CI
- A workflow change broke the pipeline

## When not to use

- Pre-release validation when CI is green — use `release-readiness`
- Stack-wide CI gates (`stack contract-check` failures) — use `stack-operations`
- General code quality questions — use `repo-audit`

## Evals

### Should trigger

- "CI is failing on main, find out why"
- "pytest passes locally but fails in Actions"
- "the workflow broke after the dependency bump"
- "fix the red pipeline"

### Should not trigger

- "is the repo ready to release?" → use `release-readiness`
- "the stack contract gate is failing" → use `stack-operations`
- "audit test coverage" → use `repo-audit`

Always inspect:

- pytest output and failing tests
- ruff lint errors
- mypy type errors
- GitHub Actions workflow configuration
- recent commits that may have introduced the failure

Check for:

- import errors or missing dependencies
- syntax errors caught by ruff
- type annotation mismatches
- workflow misconfiguration (wrong install flags, missing extras)
- test environment differences vs local

Prefer:

- smallest fix that resolves the failure
- verifying the fix locally before pushing
- one commit per logical fix

Never:

- skip hooks or bypass type checking to force a pass
- suppress errors without understanding them
- push without running the full gate locally
