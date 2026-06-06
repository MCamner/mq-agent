---
name: release-readiness
description: Use when preparing a release. Validates git state, version alignment, changelog, tests, CI, and publish checklist.
---

# Release Readiness

Goal:
Validate whether the repository is safe and complete for a release.

## When to use

- Before tagging, publishing, or announcing a release
- Verifying version alignment, changelog, and git state before pushing a release branch
- After finishing a milestone to confirm the repo is release-complete

## When not to use

- Regular development or feature work not bound for immediate release
- Exploratory or in-progress changes
- General code quality audit — use `repo-audit`
- Diagnosing CI failures — use `ci-diagnosis`

## Evals

### Should trigger

* "is this repo ready to release?"
* "check version alignment, changelog, and tests before tagging v2.0.0"
* "what's blocking the release?"
* "run the release checklist for mq-agent"

### Should not trigger

* "audit the entire repo for code quality" → use `repo-audit`
* "what's the repo-signal score?" → use `signal-assessment`
* "fix a failing test" → regular development, not a release gate
* "diagnose why CI is failing" → use `ci-diagnosis`

Always inspect:

- git status and uncommitted changes
- VERSION file vs pyproject.toml vs git tags
- CHANGELOG.md for matching entry
- README accuracy
- test suite result
- CI workflow status
- repo-signal publish checklist

Check for:

- version mismatch between files and tags
- missing or outdated CHANGELOG entry
- failing tests
- secrets or debug code left in
- unpushed commits
- CI failures on latest push

Prefer:

- concrete terminal verification steps
- minimal safe changes only
- human approval before tagging

Never:

- tag a release with failing tests
- assume CI is green without checking
- publish with a version mismatch

Safety Class: read-only (checks only — no repo mutations)
