# PR review

`mq-agent pr review <number>` writes an advisory review of one pull request.
It is read-only: nothing from the PR is executed, and nothing is posted unless
`--post` is given.

```bash
mq-agent pr review 453                 # Markdown report to stdout
mq-agent pr review 453 --json          # mq.pr-review.v1 report
mq-agent pr review 453 --post          # also post the report as one PR comment
mq-agent pr review 12 --repo ../mq-mcp # a PR in another checkout
```

## What it does

1. Reads the PR with `gh pr view`, then fetches `refs/pull/<n>/head` and the
   base branch from `origin`. If the fetched head differs from the head GitHub
   reported, the review stops: a report always describes the commit it names.
2. Checks the head out in a temporary detached worktree, computes the merge
   base, and plans the repository's own `verify-changes` selection against it.
   The worktree and the temporary refs are removed afterwards.
3. Classifies each changed file by path and size and reports the highest level
   as the PR's risk.

| Risk | Paths |
| --- | --- |
| high | `.github/workflows/`, `schemas/`, `*.schema.json`, `.mq/`, release scripts, `VERSION`, dependency and packaging files, agent settings and git hooks |
| medium | other source; a low-risk file with more than 400 changed lines; a deleted test |
| low | tests and documentation |

Findings name what a reviewer should look at: a PR that changes its own
`.mq/verification.json`, source changed without test changes, files no check
covers, and changes over 1000 lines.

## What it does not do

- It does not run the recommended checks. They come from configuration the PR
  can change, so running them would run the PR's code under the PR's rules.
  Run them yourself in a checkout you trust.
- It does not review the diff with a model. mq-mcp's diff review reads only
  mq-mcp's own working tree; reviewing another repo's PR needs an mq-mcp change
  first.
- The risk level is a heuristic for where to look first, not a judgment of the
  change.

Exit 0 when the report was produced, 2 on error.
