---
name: ci-diagnosis
description: Use when CI is failing. Diagnoses test, lint, and type check failures and generates fix steps.
---

# CI Diagnosis

Goal:
Identify the root cause of CI failures and generate concrete, safe fix steps.

## When to use

- CI is actively failing or a recent push broke tests, lint, or type checks
- Identifying the root cause of pytest, ruff, mypy, or workflow failures
- Generating concrete fix steps for CI regressions

## When not to use

- Pre-emptive quality checks when CI is passing — use `repo-audit`
- Release validation — use `release-readiness`
- Local test failures unrelated to CI configuration

## Evals

### Should trigger

* "why is CI failing?"
* "diagnose the failing GitHub Actions run"
* "which test is blocking the pipeline?"
* "pytest is failing on main — find the root cause"

### Should not trigger

* "run the tests locally to see if they pass" → local test run, not CI diagnosis
* "check if the repo is ready to release" → use `release-readiness`
* "review this code for security" → use `mq-mcp-review-orchestration`
* "audit the repo for quality issues" → use `repo-audit`

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
