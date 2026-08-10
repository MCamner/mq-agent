# Release Cockpit

`mq-agent ship` is the read-only operator surface for release decisions.
`mq-agent stack release` remains the lower-level engine that plans, prepares,
and finalizes releases behind explicit approval gates.

## Commands

```bash
mq-agent ship status --repo . --target 1.25.0
mq-agent ship status --repo . --target 1.25.0 --json
mq-agent ship proof --repo . --target 1.25.0
mq-agent ship audit --repo . --target 1.25.0 --json
```

All three commands are non-mutating. They inspect local Git state, the
repository release and contract checks, the existing stack-release plan, the
release pull request, main CI, the annotated tag, and the GitHub Release.
Unavailable evidence is reported as a blocker; it is never converted to a
green result.

`ship audit` exits with status 1 unless the current snapshot resolves to
`AUDITED`. `status` and `proof` report their state without using the process
exit code as a release decision. Consumers should read `state`,
`safe_to_release`, `blockers`, and `next_action` from
`mq_release_cockpit.v1`.

## State precedence

The resolver applies the following precedence, from completed release back to
an idle repository, after safety blockers have been evaluated:

| State | Meaning |
| --- | --- |
| `BLOCKED` | A safety prerequisite failed or evidence is unavailable |
| `AUDITED` | The current post-release audit passes |
| `PUBLISHED` | Verified tag and GitHub Release align |
| `FINALIZED` | Annotated tag targets the verified merge commit |
| `MERGED` | Release PR is merged but not finalized |
| `PR_GREEN` | Release PR is approved and CI is green |
| `PREPARED_PR` | Release PR exists and awaits review or CI |
| `PREFLIGHT_READY` | An explicit target exists and prepare gates pass |
| `IDLE` | No active target release was detected |

Each state returns exactly one next action. Review, merge, finalize, and
publication remain explicit human decisions. Copy-pasteable commands are only
included for bounded local actions.

## Evidence limits

The cockpit reads the configured MQ stack repository path. A checkout outside
that inventory cannot claim stack-preflight readiness. GitHub CLI failures,
missing main CI history, invalid JSON, and unreachable services are preserved
under `checks.unavailable` and force `BLOCKED`.
