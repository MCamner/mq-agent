# Bounded task workflows and execution receipts

`mqlaunch do "granska ändringarna" --repo <repo> --plan --json` selects
`review-and-test` without executing tools or persisting a run. Supported exact
intents also include `felsök repot` (the existing `repo-preflight` prerequisites
chain) and `förbered release` (`release-ready`). Unknown or composite requests
fail before execution. These are fixed templates, not learned routing.

Remove `--plan` to run through the existing workflow policy and plan approval.
Use `--yes` only for a plan already authorized by the operator. JSON mode without
`--yes` never blocks waiting for interactive input. Launcher targets are resolved
before its working-directory change. mq-agent binds the Git root and HEAD and
checks that tools confirm the same identity. Changed HEAD or missing target
confirmation fails closed; old runs without identity require a fresh run.

The review workflow requires the target-aware mq-mcp implementation and the
server's review credential. Local context cards, CodeGraph for indexed code
diffs, and repo-signal are bounded optional context sources. Source availability
is reported from actual reads and tool calls. Missing optional sources do not
block the workflow. No visual analysis runs without visual material.

Workflow state is persisted locally. Completed runs can emit an existing
`workflow-observation.v1` to the local mqobsidian inbox and a measured execution
outcome. `MQ_WORKFLOW_OBSERVE=0` disables both emissions. These observations never
promote routing or activation policy. Only source references, commit, status tags
and tool metrics enter the observation; raw prompts and tool output do not.
Tests and delegated review tools may write their normal caches or audit logs.

Read the local receipt with:

```sh
mq-agent workflow receipt RUN_ID --json
mq-agent workflow receipt RUN_ID --json | mq-hal workflow-receipt -
```

The mq-agent-owned receipt reports step coverage separately from verification.
A completed tool chain is not overall PASS when verification is unknown, a step
was skipped, a review was limited, or workflow storage failed. Missing execution
ids and unconfirmed recording stay unknown. HAL renders these facts without
recalculating a verdict or writing a session log.

Resume only after correcting the cause with `mqlaunch flow resume RUN_ID`.
Passed steps are preserved and target HEAD is checked again. Interrupted or
partial work must never be relabelled complete. The existing thread-backed
executor cannot forcibly terminate an already running Python call; transport and
producer timeouts remain necessary. The MCP pytest adapter currently runs the
server's Python with a 120-second limit, not the target's virtual environment.
Tracked HEAD diff excludes untracked files. Live model/API execution has not been
verified by the local regression tests.
