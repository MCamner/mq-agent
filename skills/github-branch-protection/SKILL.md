---
name: github-branch-protection
description: Inspect or configure GitHub default-branch protection with pull-request enforcement, repository-specific status checks, and explicit mutation approval. Use when GitHub reports that main or the default branch is unprotected.
---

# GitHub Branch Protection

Use the repository tool to inspect and configure classic GitHub branch protection:

```bash
python -m mq_agent.tools.github_branch_protection OWNER/REPO
```

The default mode is read-only and reports the current rule for the repository's
actual default branch.

## Apply

Applying protection changes repository settings. Confirm that the user asked for
the change, then run:

```bash
python -m mq_agent.tools.github_branch_protection OWNER/REPO --apply --approve
```

Automatic check discovery uses check runs from the latest merged pull request.
This avoids requiring Pages or push-only jobs that would make future pull
requests impossible to merge.

Use explicit contexts when the latest merged pull request is not representative:

```bash
python -m mq_agent.tools.github_branch_protection OWNER/REPO \
  --apply --approve --checks "Tests,packaging,markdownlint"
```

For a repository with no CI, require the user to choose the explicit fallback:

```bash
python -m mq_agent.tools.github_branch_protection OWNER/REPO \
  --apply --approve --no-required-checks
```

## Result

The applied rule requires pull requests, current-base status checks when
configured, resolved conversations, and administrator enforcement. It blocks
force-pushes and deletion of the default branch. Required approving reviews stay
at zero so a single-maintainer repository does not deadlock itself.

Read the rule back after mutation and report the exact branch, checks, and
enforcement settings. Do not claim success from the write response alone.

If protection already exists, the tool stops instead of overwriting it. Inspect
the current rule and use `--replace-existing` only when the user explicitly asks
to replace or update that rule.

## Evals

### Should trigger

- "fix Your main branch isn't protected"
- "protect the default branch on this GitHub repo"
- "check whether main has branch protection"

### Should not trigger

- "fix failing GitHub Actions"
- "merge this pull request"
- "create a release"

## Guardrails

- Never apply without explicit user authorization and the `--approve` flag.
- Never guess required check names.
- Never require deployment-only checks for pull requests.
- Never set an approval count that the repository cannot satisfy.
- Do not weaken an existing stricter rule without explicit user direction.
