---
name: release-readiness
description: Use when preparing a release. Validates git state, version alignment, changelog, tests, CI, and publish checklist.
---

# Release Readiness

Goal:
Validate whether the repository is safe and complete for a release.

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
