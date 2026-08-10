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
* **SKIPPED** (CI mode only) — repo not present in the CI workspace. Never fails the gate.

## Contract file

Each MQ repo must have `.mq/repo-contract.json`:

```json
{
  "repo": "mq-agent",
  "role": "orchestrator",
  "version": "1.12.0",
  "status": "active",
  "contracts": ["stack_sweep.v1", "contract_gate.v1"],
  "next_focus": ""
}
```

Required fields: `repo`, `role`, `version`, `status`, `contracts`.

**`version` must be kept in sync with the root `VERSION` file.** When you bump VERSION, also update `.mq/repo-contract.json`.

Schema: [`schemas/mq_stack_repo_contract.schema.json`](../schemas/mq_stack_repo_contract.schema.json)

## Optional: `compatibility`

A repo may declare its machine-readable compatibility boundary. The field is
optional and existing contracts stay valid without it.

```json
{
  "compatibility": {
    "protocols": { "mcp_api": "1.x-fastmcp" },
    "dependencies": { "mcp": ">=1.27.1,<2" },
    "produces": ["mq-mcp.tools.v1"],
    "consumes": ["mq.feedback.v1"]
  }
}
```

`mq-agent stack compatibility` reads it and distinguishes two states:

| State | Finding | Blocks release |
|---|---|---|
| No `compatibility` block | `MQC009_COMPATIBILITY_METADATA_MISSING` (WARN) | No |
| Block contradicts `pyproject.toml` | `MQC011_DECLARED_DEPENDENCY_MISMATCH` (FAIL) | Yes |
| Range allows a major the protocol track excludes | `MQC012_PROTOCOL_CONTRADICTS_RANGE` (FAIL) | Yes |

Missing metadata is expected during rollout and never blocks. Metadata that
disagrees with the repo's own dependency declaration does block — a contract
that lies is worse than no contract.

`dependencies` is compared as a normalised specifier set, so `>=1.27.1,<2` and
`<2,>=1.27.1` are treated as the same boundary.

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

## CI mode

In GitHub Actions only the repo under test is checked out — the sibling repos
in `~/` do not exist. Running the gate plainly there would report every sibling
as BLOCKED. The `--ci` flag fixes this:

```bash
mq-agent stack contract-check --ci --json
mq-agent stack release-check --ci --json
```

In CI mode:

* A repo missing from the workspace is reported as **SKIPPED** and never fails the gate.
* The CI checkout itself is detected via its directory name (the checkout
  directory equals the repo name) and is **fully validated** — version sync,
  required fields, README. A DRIFT or BLOCKED in the checked-out repo still
  exits 1.
* The JSON output gains a `mode` field (`"ci"` or `"local"`).

The repo ships `.github/workflows/mq-stack-gate.yml` with two jobs:

* **`pr-gate`** (pull requests) — fast, isolated: runs both gates with `--ci`
  so the PR is judged only on the mq-agent checkout. Unrelated drift in a
  sibling repo cannot fail an mq-agent PR.
* **`full-stack-gate`** (push to `main`, nightly cron, manual dispatch) —
  checks out every MQ stack repo, links them into the expected home layout,
  and runs both gates without `--ci`, validating the whole stack.

```yaml
- name: Stack contract gate
  run: mq-agent stack contract-check --ci --json

- name: Stack release gate
  run: mq-agent stack release-check --ci --json
```

This means a version bump that forgets to update `.mq/repo-contract.json`
fails the PR before it can merge, while stack-wide drift is still caught on
`main` and in the nightly run.

## Companion commands

```bash
mq-agent stack sweep          # score every repo
mq-agent stack report         # score + trend + ready
mq-agent stack release-check  # VERSION/CHANGELOG/branch gate
mq-agent stack release-notes  # commits since last tag
mq-agent stack contract-check # contract manifest gate  ← this command
```
