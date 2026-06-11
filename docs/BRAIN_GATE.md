# Brain Release Gate — `mq-agent stack brain-gate`

The pre-release checklist for the brain-integrated stack. Before a release,
the whole memory loop must be green — not just the repo gates. The gate runs
five checks, all read-only: nothing is written, no review is executed.

## Command

```bash
mq-agent stack brain-gate          # checklist view, exit 1 on NO-GO
mq-agent stack brain-gate --json   # machine-readable result
```

## The five checks

| Check | Green means | Fix hint on failure |
|---|---|---|
| `contract-check` | Stack contract gate overall `READY` | `mq-agent stack contract-check` |
| `release-check` | Stack release gate overall `GO` | `mq-agent stack release-check` |
| `truth-export` | The stack truth note renders in dry-run and has a target path | `mq-agent stack truth-export --dry-run` |
| `vault-structure` | The standard mqobsidian export structure is complete | `mq-agent brain structure --init --approve` |
| `brain-review` | mq-mcp reachable with `review_repo` + `brain_record_review` — `review repo --brain` has a working path | `mq-agent mcp start` |

`overall` is `GO` only when every check passes; `next_action` carries the
first failing check's fix hint.

## When to run it

Before `mq-agent stack release --repo <name> --execute`. The release command
keeps its own release-check pre-gate; `brain-gate` is the wider ritual that
also proves the memory side (truth note, vault, brain write path) is ready,
so the release actually lands in mqobsidian.

## JSON output

```json
{
  "overall": "GO",
  "checks": [
    {"name": "contract-check", "status": "PASS", "detail": "READY"},
    {"name": "release-check", "status": "PASS", "detail": "GO"},
    {"name": "truth-export", "status": "PASS", "detail": "dry-run ok — would write ..."},
    {"name": "vault-structure", "status": "PASS", "detail": "OK"},
    {"name": "brain-review", "status": "PASS", "detail": "review repo --brain path wired (...)"}
  ],
  "next_action": "all green — release away",
  "checked_at": "2026-06-11T12:00:00+00:00"
}
```

Failing checks carry a `hint` field with the fix command.

## Tool registry

Registered as `brain_release_gate` in the mq-agent tool registry
(`mq_agent/tools/brain_gate.py`). Safety class A — read-only.
