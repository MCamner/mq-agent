---
name: ci-diagnosis
description: Use when CI is failing. Diagnoses test, lint, and type check failures and generates fix steps.
---

# CI Diagnosis

Goal:
Identify the root cause of CI failures and generate concrete, safe fix steps.

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
