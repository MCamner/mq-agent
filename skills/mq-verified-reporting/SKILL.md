---
name: mq-verified-reporting
description: Use when writing a PR description, commit message, status report or gate summary in an MQ repo. Every number, status and claim must come from tool output in this session; covers known traps in shell loops, lint scope, merge permissions and branch state.
---

# MQ Verified Reporting

Reports are read as evidence. A wrong number in a PR body is a false record, and
it is just as bad as a failing test that was reported as passing.

## When to use

- Writing a PR body, commit message or final status report
- Summarising the results of gates, tests or CI
- Reporting what was verified "for real"

## When not to use

- Deciding whether evidence is valid in the first place → use `mq-evidence-integrity`
- Diagnosing a red CI job → use `ci-diagnosis`

## Evals

### Should trigger

- "write the PR body with the gate results"
- "summarise what passed"
- "open the PR and list the verification"

### Should not trigger

- "is this outcome valid evidence?" → use `mq-evidence-integrity`
- "why is CI red?" → use `ci-diagnosis`

## Rules

1. **Copy numbers, don't compute them.** Take counts from the command that
   prints them: tests passed, contracts declared, records written. Incident: a
   PR body said "15 contracts" when the release gate printed 13. Re-read the gate
   output after writing the body, and edit the PR if they differ.
2. **One command per check when the result matters.** Running commands through
   `for c in "a b" ...; do $c; done` executes `"a b"` as a single word, and the
   failure looks like a red gate. Use a bash array (`"${cmd[@]}"`) or separate
   calls. Re-run any FAIL on its own before reporting it. zsh (the default
   shell here) does not word-split an unquoted `$var` at all, so
   `set -- $spec` hands over one argument. That came up while writing this
   skill.
3. **Scope lint to your own files.** markdownlint's repo glob also picks up
   gitignored local working files (for example under `.mq/`). Filter them out
   before concluding that your change is clean or dirty.
4. **Check that a test asserts the intended invariant.** `all(checks.values())`
   fails on a VALID status when some checks are negative flags (`revoked`,
   `expired`). Assert the exact expected dict instead.
5. **Merging is the operator's call.** The auto-mode classifier denies
   `gh pr merge` as "Merge Without Review". Report that the PR is green and
   mergeable, and give the command. Do not retry or work around the denial.
   `git pull` inside a chained command can be denied for the same reason. When
   the branch is already current, use `git switch`/`git fetch` without pulling.
6. **Stage and commit separately.** The secret-gate PreToolUse hook evaluates
   the state before the command runs, so `git add … && git commit` in one call
   is refused.
7. **Say what was not verified.** If a step was skipped, blocked or only run
   against a redirected store, say so explicitly. "Ran for real against mq-mcp,
   stores redirected" is a different claim from "ran in production".
8. **Flag dependent PRs.** When a consumer PR waits on an owner PR, write in the
   body that its vendoring gate is red until the owner merges, and why. Then the
   red check is not mistaken for a defect.
