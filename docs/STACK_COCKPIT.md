# Stack Cockpit

`mq-agent stack cockpit` is the one-table view of the whole mq-stack.

It merges what the stack suite already knows — git state (`status`), the
contract gate (`contract-check`), the release gate (`release-check`),
unreleased work (`release-notes`) and the latest mqobsidian truth note
(`truth-export`) — into a single read-only snapshot with one recommended
next action per repo. Later the input to `mq-hal`.

---

## Command

```bash
mq-agent stack cockpit          # rendered table
mq-agent stack cockpit --json   # machine-readable snapshot
```

Read-only — the cockpit never mutates any repo.

---

## Columns

| Column | Source |
| --- | --- |
| Repo | `MQ_STACK_REPOS` |
| Version | `VERSION` / `version.txt` / `pyproject.toml` |
| Branch | `git branch --show-current` |
| Dirty | `git status --short` |
| Contract | Contract gate: READY / REVIEW / DRIFT / BLOCKED |
| Gate | Release gate: GO / NO-GO (`—` for gate-excluded repos) |
| Next action | Highest-severity recommendation (see below) |

Below the table: overall release gate, overall contract verdict, and the
freshness of the latest stack-truth note in mqobsidian
(`fresh` ≤ 1 day, `aging` ≤ 7 days, `stale` beyond that, `none` if missing).

---

## Next action

One recommendation per repo, highest severity first:

1. Repo missing locally → `clone repo locally`
2. Contract BLOCKED or DRIFT → `fix contract: <reason>`
3. Release blocker → `fix blocker: <first blocker>`
4. Dirty tree → `commit or stash uncommitted changes`
5. Off main → `switch to main (on <branch>)`
6. Unpushed commits → `push N commit(s)`
7. Unreleased commits since last tag → `stack release --repo <name>`
8. Otherwise → `up to date`

Gate-excluded repos (the mqobsidian vault) only surface local hygiene:
dirty tree or `—`.

The stack-level `next_action` is the first repo that is not up to date; when
every repo is clean it falls back to truth-note freshness (`run stack
truth-export` when stale or missing), and finally `all green`.

---

## JSON output

```bash
mq-agent stack cockpit --json | jq '{overall_gate, overall_contract, next_action}'
mq-agent stack cockpit --json | jq '.repos[] | {repo, version, gate, next_action}'
```

Exit code is always 0 — the cockpit is a dashboard, not a gate. Use
`stack release-check` / `stack contract-check` for CI-enforced verdicts.

---

## Tool registry

Registered as `stack_cockpit` in `TOOL_REGISTRY` — returns the JSON snapshot.
