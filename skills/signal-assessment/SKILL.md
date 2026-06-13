---
name: signal-assessment
description: Use when scoring a repository's README quality, publish readiness, and generating an AI-backed improvement plan via repo-signal.
---

# Signal Assessment

Run a full repo-signal assessment and generate an actionable AI improvement plan.

## When to use

- Scoring a repository's README quality or publish readiness
- Generating a prioritized improvement plan backed by repo-signal
- Verifying score improvements after README/docs changes

## When not to use

- General structural audit without scoring — use `repo-audit`
- Multi-repo health sweeps — use `stack-operations` (`mq-agent stack sweep`)
- Release validation — use `release-readiness`

## Evals

### Should trigger

- "score this repo's README"
- "how publish-ready is this repo?"
- "generate an improvement plan from repo-signal"
- "did the README score improve after my changes?"

### Should not trigger

- "audit the repo structure" → use `repo-audit`
- "sweep all MQ repos" → use `stack-operations`
- "is it ready to tag?" → use `release-readiness`

Always inspect:

- repo-signal scan (project type, languages, tooling, entry points)
- README score (0–100) and missing sections
- publish checklist (0–16) and failing checks
- focus areas from static analysis
- recent git activity

Check for:

- README score below 80
- publish checklist below 12/16
- missing quick start, examples, roadmap, or demo sections
- no VERSION file
- missing issue templates
- no GitHub Pages or docs site

Prefer:

- static analysis first (no API key needed)
- specific actionable fixes over general advice
- verified score improvements after changes

Never:

- modify README without showing the diff first
- report a passing score without running the actual check
