# MQ Stack Status v2

`mq-agent stack status` and `mqlaunch stack status` report verification
evidence for the exact commit checked out in each MQ repository.

## Contract

A repo is **VERIFIED** only when all of these are true:

1. the local repository exists and has a HEAD commit;
2. its working tree is clean;
3. every required GitHub Actions context declared in
   `mq_agent/data/branch_protection.yaml` reported `success` for that exact
   HEAD SHA;
4. the complete set of required checks has completion timestamps; and
5. the final required check completed within the freshness window.

The default freshness window is 24 hours. Override it for an operator session
with `MQ_STACK_VERIFY_MAX_AGE_SECONDS`.

Status meanings:

| Status | Meaning |
| --- | --- |
| `VERIFIED` | Exact HEAD has complete, fresh, successful required-check evidence and the worktree is clean. |
| `STALE` | Exact HEAD has complete successful evidence, but it is older than the freshness window. |
| `UNVERIFIED` | Evidence is missing/in progress/unavailable, the repo is absent, or the worktree differs from HEAD. |
| `FAIL` | At least one required check completed with a non-success conclusion for exact HEAD. |

No result is inherited from another commit. A green run for the previous SHA
does not verify the current SHA.

## Usage

```bash
mq-agent stack status
mq-agent stack status --json

# Through the terminal entrypoint
mqlaunch stack status
mqlaunch stack status --json
```

The command is read-only. GitHub access is performed with GET requests through
the `gh` CLI. If GitHub cannot be read, the repo becomes `UNVERIFIED`; the
command does not invent a verdict.

## JSON

The machine contract is `mq.stack-status.v2` and is defined by
`schemas/mq_stack_status_v2.schema.json`.

Each repo includes its local branch, exact commit SHA, dirty state and a
`verification` object with:

- expected and verified scopes;
- per-scope `PASS`, `FAIL`, `PENDING` or `MISSING`;
- the time at which the final required check completed;
- evidence age in seconds; and
- a machine-readable reason.

This document is intended to be consumable by HAL and later evidence-gated
activation workflows without parsing terminal text.
