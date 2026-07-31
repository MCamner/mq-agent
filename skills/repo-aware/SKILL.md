---
name: repo-aware
description: Use when inspecting, explaining, planning, reviewing, or changing an existing repository. Combine local files, repo signals, conventions, Git state, docs, tests, release flow, and AI-readiness evidence before acting.
---

# Repo Aware

Use this skill to make AI work repo-first instead of prompt-first.

The goal is to ground every answer or change in the repository's actual structure, conventions, risks, and current state.

## When to use

Use this skill when the user asks to:

- understand a repo
- inspect or explain code
- plan changes in an existing repo
- implement a feature or fix
- review repo quality or readiness
- prepare release, docs, README, Wiki, or GitHub Pages updates
- use repo-signal report output as context for AI work
- decide what Codex should inspect before acting

## When not to use

- Structured read-only audit with a verifier loop — use `repo-audit`
- README/publish scoring — use `signal-assessment`
- Multi-repo stack health or gates — use `stack-operations`
- Release validation — use `release-readiness`

## Evals

### Should trigger

- "explain how this repo is structured before I change it"
- "ground your plan in this repo's conventions"
- "what should I inspect before implementing this feature?"
- "work repo-first on this task"

### Should not trigger

- "give me a structured audit of this repo" → use `repo-audit`
- "score the README" → use `signal-assessment`
- "check health across all MQ repos" → use `stack-operations`
- "is it ready to release?" → use `release-readiness`

## Core rule

Always let the repo teach you how to work.

Prefer evidence from:

1. README and docs
2. package/build metadata
3. scripts, tools, and CLI entrypoints
4. tests and CI
5. Git status
6. recent or relevant files
7. repo-signal reports, when available

Do not invent structure, commands, release flow, or project goals when the repo can answer them.

## Fast workflow

Start with a small inspection pass:

```bash
repo-signal doctor
repo-signal analyze
git status --short
```

If the task is about a specific area, build focused context:

```bash
repo-signal repoaware --mode explain "question"
repo-signal repoaware --mode debug "error or failing behavior"
repo-signal repoaware --mode review "change or risk"
repo-signal repoaware --mode architect "structure or coupling"
```

If `repo-signal` is unavailable, inspect manually with `rg --files`, README, package metadata, scripts, tests, and Git status.

## Inspection checklist

Check only what is relevant, but default to this order:

- `README.md`
- `AGENTS.md` or local instructions
- `pyproject.toml`, `package.json`, `requirements.txt`, or equivalent metadata
- `bin/`, `scripts/`, `tools/`, `Makefile`
- `tests/`
- `.github/workflows/`
- `docs/`
- main package or app directory
- `git status --short`

## How to think

Classify the repo before acting:

- project type
- main user workflow
- command surface
- docs surface
- release maturity
- test maturity
- AI readiness
- likely highest-risk area

Then choose the smallest useful action that improves correctness, clarity, or momentum.

## Priority model

Prioritize in this order:

1. correctness and safety
2. preserving user changes
3. matching existing naming and structure
4. improving discoverability
5. keeping output and commands easy to verify
6. avoiding broad rewrites unless requested

## Output style

Be practical and grounded.

For analysis, include:

- what the repo appears to be
- what evidence supports that
- highest-risk gaps
- recommended next action

For implementation, include:

- files changed
- behavior added or fixed
- verification run
- anything not verified

## Repo-signal integration

Use `repo-signal doctor` as the readiness summary.

Treat its suggested skills as routing hints:

- `repo-product-auditor` for README, launch, and product presentation
- `terminal-ui-polisher` for CLI and terminal UX
- architecture-oriented work when symbols and repo graph edges exist

Use `repo-signal repoaware` to generate compact task context for AI reasoning.

## Guardrails

Do not:

- assume the README is current without checking files
- assume tests exist or pass
- overwrite user changes
- recommend release work without checking Git state
- turn every task into a large audit
- add new abstractions before understanding local patterns

When uncertain, say what is known, what is inferred, and what should be checked next.
