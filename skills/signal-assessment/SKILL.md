---
name: signal-assessment
description: Use when scoring a repository's README quality, publish readiness, and generating an AI-backed improvement plan via repo-signal.
---

# Signal Assessment

Goal:
Run a full repo-signal assessment and generate an actionable AI improvement plan.

## When to use

- Scoring a repository's README quality and publish readiness via repo-signal
- Generating an AI-backed improvement plan for README, docs, or publish checklist
- Checking repo-signal focus areas before a release or product launch

## When not to use

- General code review or architecture audit — use `repo-audit`
- Diagnosing CI failures — use `ci-diagnosis`
- Security or risk analysis
- Repos without repo-signal installed

## Evals

### Should trigger

* "run a repo-signal assessment"
* "what's the signal score for this repo?"
* "export the repo signal pack"
* "score the README quality and generate an improvement plan"

### Should not trigger

* "is this repo ready to release?" → use `release-readiness`
* "audit this repo for code quality" → use `repo-audit`
* "review this diff for security issues" → use `mq-mcp-review-orchestration`
* "why is CI failing?" → use `ci-diagnosis`

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

Safety Class: read-only (analysis and scoring only — no repo mutations)
