---
name: release-readiness
description: Use when preparing an mq-agent release. Validates git state, version alignment, changelog, tests, CI, the stack contract gate, and release-notes draft.
---

# Release Readiness

Validate whether mq-agent is safe and complete for a release.

## When to use

- Before tagging, publishing, or announcing an mq-agent release
- After a milestone to verify version alignment, tests, and gate status
- When the release checklist needs a structured pass

## When not to use

- Releasing another MQ repo or orchestrating cross-repo releases — use `stack-operations` (`mq-agent stack release`)
- Diagnosing why CI fails — use `ci-diagnosis`
- General repo quality audit — use `repo-audit`

## Evals

### Should trigger

- "is mq-agent ready to release?"
- "run the release check before tagging"
- "what's blocking the next mq-agent release?"
- "verify version and changelog alignment"

### Should not trigger

- "release mq-hal through the stack pipeline" → use `stack-operations`
- "CI is red, find out why" → use `ci-diagnosis`
- "audit the repo structure" → use `repo-audit`
- "score the README" → use `signal-assessment`

## Always inspect

- `git status` and unpushed commits
- `VERSION` vs `pyproject.toml` vs git tags
- `.mq/repo-contract.json` — `version` must match `VERSION` (contract gate DRIFTs otherwise)
- `CHANGELOG.md` for a matching entry
- README accuracy
- test suite result
- CI workflow status on latest push

## Verification

The release flow is gated by commands, not checklists:

```bash
./release-check.sh                   # repo-local release gate
mq-agent release-check               # same gate via the CLI
mq-agent stack contract-check        # stack contract gate (READY required)
mq-agent stack release-notes         # draft of unreleased work since last tag
python -m pytest -q
```

For the orchestrated pipeline (version bump, contract sync, notes, tag):

```bash
mq-agent stack release --repo mq-agent             # dry-run plan
mq-agent stack release --repo mq-agent --execute   # apply
```

## Block release on

- version mismatch between `VERSION`, `pyproject.toml`, `.mq/repo-contract.json`, and changelog
- failing tests or red CI on the release commit
- contract gate reporting DRIFT or BLOCKED
- missing or outdated CHANGELOG entry
- secrets or debug code left in
- unpushed commits

## Never

- tag a release with failing tests
- assume CI is green without checking
- publish with a version mismatch
- bump `VERSION` without syncing `.mq/repo-contract.json`

## Report format

Return: status (ready/blocked/uncertain), blockers, checks run, checks skipped and why, next concrete action.
