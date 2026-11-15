# PR review

`mq-agent pr review <number>` writes an advisory review of one pull request.
It is read-only: nothing from the PR is executed, and nothing is posted unless
`--post` is given.

```bash
mq-agent pr review 453                 # Markdown report to stdout
mq-agent pr review 453 --json          # mq.pr-review.v1 report
mq-agent pr review 453 --post          # also post the report as one PR comment
mq-agent pr review 12 --repo ../mq-mcp # a PR in another checkout
mq-agent pr review 453 --model-review  # add an advisory model review of the diff
mq-agent pr review 453 --model-review --review-mode security
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
- It does not review the diff with a model unless `--model-review` is given.
- The risk level is a heuristic for where to look first, not a judgment of the
  change.

## Model review

`--model-review` sends the PR's diff against the merge base, as text, to
mq-mcp's `review_patch` tool under the contract chosen with `--review-mode`
(`risk` by default, or `security`, `architecture`, `comment`). mq-mcp uses its
configured review provider; set `MQ_MCP_REVIEW_PROVIDER=ollama` on the mq-mcp
side to keep the diff local. The findings appear under "Model review
(advisory)" in the report and as `model_review` in the JSON.

- The model sees only the diff, not the files around it, so a finding can be a
  false positive that the rest of the repository would rule out.
- Its findings never change the path-based risk level.
- A diff over 200 KB is not sent, and the report says `SKIPPED` with the size.
  A refused or unreachable review is `ERROR`. Neither is reported as a review
  that found nothing.

Exit 0 when the report was produced, 2 on error.
