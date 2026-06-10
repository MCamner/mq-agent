# MQ Stack Contract Gate

Validates that every repo in the MQ stack declares and maintains a contract manifest.
No API key required. Exits 1 if any repo is BLOCKED or DRIFT.

## Quick start

```bash
mq-agent stack contract-check
mq-agent stack contract-check --json
```

## How it works

For each repo (excluding `mqobsidian`), the gate checks:

| Check | Failure status |
| --- | --- |
| Repo exists locally | BLOCKED |
| `VERSION` file present | BLOCKED |
| `README.md` present | BLOCKED |
| `.mq/repo-contract.json` exists | DRIFT |
| Contract JSON is valid | BLOCKED |
| All required fields present | BLOCKED |
| `contract.version` == `VERSION` file | DRIFT |
| Uncommitted changes or non-main branch | REVIEW |

Status precedence: **BLOCKED > DRIFT > REVIEW > READY**

The command exits 1 if any repo is BLOCKED or DRIFT. REVIEW does not fail the gate.

## Status meanings

* **READY** — contract manifest present, version synced, clean working tree on main.
* **REVIEW** — contract valid but has warnings (uncommitted changes, non-main branch). Does not fail the gate.
* **DRIFT** — contract missing or version not synced with `VERSION` file. Fails the gate.
* **BLOCKED** — hard error: repo not found, no VERSION, no README, invalid JSON, or missing required fields. Fails the gate.

## Contract file

Each MQ repo must have `.mq/repo-contract.json`:

```json
{
  "repo": "mq-agent",
  "role": "orchestrator",
  "version": "1.11.0",
  "status": "active",
  "contracts": ["stack_sweep.v1", "contract_gate.v1"],
  "next_focus": ""
}
```

Required fields: `repo`, `role`, `version`, `status`, `contracts`.

**`version` must be kept in sync with the root `VERSION` file.** When you bump VERSION, also update `.mq/repo-contract.json`.

Schema: [`schemas/mq_stack_repo_contract.schema.json`](../schemas/mq_stack_repo_contract.schema.json)

## Example output

```text
MQ Stack Contract Gate

  macos-scripts        READY
  mq-agent             READY
  mq-mcp               READY
  repo-signal          READY
  mq-hal               DRIFT  missing .mq/repo-contract.json
  mq-image-analyze     READY
  mq-ums               READY
  atlas-one            READY

✗ Stack contract: NOT READY
  → mq-hal: missing .mq/repo-contract.json
```

## JSON output

```bash
mq-agent stack contract-check --json
```

```json
{
  "overall": "NOT READY",
  "reasons": ["mq-hal: missing .mq/repo-contract.json"],
  "repos": [
    {"name": "mq-agent", "status": "READY", "reason": ""},
    {"name": "mq-hal",   "status": "DRIFT", "reason": "missing .mq/repo-contract.json"}
  ],
  "checked_at": "2026-06-10T10:00:00+00:00"
}
```

## Typical workflow

When releasing a new version of any MQ repo:

```bash
# 1. Bump VERSION
echo "1.12.0" > VERSION

# 2. Update the contract version to match
jq '.version = "1.12.0"' .mq/repo-contract.json > /tmp/c.json && mv /tmp/c.json .mq/repo-contract.json

# 3. Run the gate
mq-agent stack contract-check
```

## Companion commands

```bash
mq-agent stack sweep          # score every repo
mq-agent stack report         # score + trend + ready
mq-agent stack release-check  # VERSION/CHANGELOG/branch gate
mq-agent stack release-notes  # commits since last tag
mq-agent stack contract-check # contract manifest gate  ← this command
```
